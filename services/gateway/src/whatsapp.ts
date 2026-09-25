import baileys, {
  DisconnectReason,
  downloadMediaMessage,
  fetchLatestBaileysVersion,
  useMultiFileAuthState,
  type WASocket,
} from "baileys";

// Baileys 6.x es CommonJS: bajo ESM el default llega como el módulo entero, no
// como la función. Se toma .default si está.
const makeWASocket = ((baileys as unknown as { default?: unknown }).default ??
  baileys) as typeof import("baileys").default;
import { Boom } from "@hapi/boom";
import { wrapSocket } from "baileys-antiban";
import { access, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import qrcode from "qrcode-terminal";
import pino from "pino";
import { addressesBot, config, isAllowed, isGroup } from "./config.js";
import type { InboundMessage, OutboundMessage } from "./bus.js";
import { notifyTelegram } from "./telegram.js";

const log = pino({ level: process.env.LOG_LEVEL ?? "info" });

// WhatsApp envuelve el mensaje real en capas (efímero, ver una vez, etc.).
// Hay que desenvolver hasta el contenido para sacar el texto y el tipo.
type WAMessage = Record<string, any> | null | undefined;

function unwrap(msg: WAMessage): Record<string, any> {
  let m = msg ?? {};
  for (let i = 0; i < 5; i++) {
    const inner =
      m.ephemeralMessage?.message ??
      m.viewOnceMessage?.message ??
      m.viewOnceMessageV2?.message ??
      m.viewOnceMessageV2Extension?.message ??
      m.documentWithCaptionMessage?.message ??
      m.editedMessage?.message ??
      m.protocolMessage?.editedMessage;
    if (!inner) break;
    m = inner;
  }
  return m;
}

function extractText(content: Record<string, any>): string {
  // Los mensajes de Baileys son objetos protobuf: los campos string ausentes
  // llegan como "" (default de proto3), no como undefined. Por eso va || y no
  // ??, para saltear los vacíos y llegar al campo que sí trae el texto.
  return (
    content.conversation ||
    content.extendedTextMessage?.text ||
    content.imageMessage?.caption ||
    content.videoMessage?.caption ||
    content.buttonsResponseMessage?.selectedDisplayText ||
    content.listResponseMessage?.title ||
    ""
  );
}

// Se piden el código de vinculación y la reconexión una sola vez, para no
// abrir sockets en cascada cuando WhatsApp cierra la conexión.
let pairingAsked = false;
let reconnecting = false;

// Reintentos seguidos sin lograr abrir la conexión, y si ya se avisó de la
// caída. Un fallo transitorio (uno o dos reintentos) no avisa; una racha
// sostenida sí, y una sola vez, no en cada reintento.
let failuresInARow = 0;
let downtimeNotified = false;
const NOTIFY_AFTER_FAILURES = 3;

// Foto de perfil y "acerca de": se suben una sola vez por sesión vinculada,
// no en cada reconexión. El marcador vive junto a las credenciales, así que
// sobrevive un reinicio del gateway pero se vuelve a subir si se re-vincula.
async function setUpProfile(sock: WASocket): Promise<void> {
  const marker = join(config.authDir, ".profile-set");
  try {
    await access(marker);
    return; // ya está puesto
  } catch {
    // no existe, sigue de largo
  }
  try {
    const jid = sock.user?.id;
    if (!jid) return;
    const avatar = await readFile(config.avatarPath);
    await sock.updateProfilePicture(jid, avatar);
    await sock.updateProfileStatus(config.statusText);
    // El nombre que se ve en el chat de alguien que no te tiene agendado.
    await sock.updateProfileName(config.profileName);
    await writeFile(marker, new Date().toISOString());
    log.info("Foto de perfil, estado y nombre configurados");
  } catch (err) {
    log.warn({ err }, "No pude configurar la foto de perfil, el estado o el nombre");
  }
}

export async function startWhatsApp(
  onMessage: (msg: InboundMessage) => void,
): Promise<WASocket> {
  const { state, saveCreds } = await useMultiFileAuthState(config.authDir);

  // Usar la versión actual de WhatsApp Web. Con una vieja, WhatsApp cierra la
  // conexión con código 405 y no deja vincular.
  const { version } = await fetchLatestBaileysVersion();

  const raw = makeWASocket({
    version,
    auth: state,
    logger: log.child({ mod: "baileys" }),
    // Baileys marca en línea al número. Lo dejamos discreto.
    markOnlineOnConnect: false,
  });

  // El riesgo de que Meta banee el número es el más concreto del proyecto.
  // baileys-antiban mete jitter en los envíos, simula tipeo, hace warm-up de
  // siete días con un número nuevo y auto-pausa cuando detecta señales de ban.
  // baileys-antiban compila sus tipos contra otra versión de Baileys y el
  // WASocket no coincide. En runtime es el mismo socket con sendMessage
  // envuelto, así que lo casteamos.
  // baileys-antiban está compilado contra otra versión de Baileys y envuelve el
  // socket. Con ANTIBAN=off se usa el socket crudo, para descartarlo cuando la
  // vinculación falla.
  const sock =
    process.env.ANTIBAN === "off"
      ? raw
      : (wrapSocket(raw as never) as unknown as WASocket);

  // Vinculación por código: si el número está configurado y todavía no hay
  // sesión, se pide un código de 8 dígitos y se lo escribe en WhatsApp, en
  // Dispositivos vinculados > Vincular con número de teléfono. Es más simple que
  // el QR cuando el gateway corre en un servidor remoto.
  if (config.botNumber && !state.creds.registered && !pairingAsked) {
    pairingAsked = true;
    setTimeout(async () => {
      try {
        const code = await raw.requestPairingCode(config.botNumber);
        log.info(`Código de vinculación de WhatsApp: ${code}`);
      } catch (err) {
        pairingAsked = false; // que un próximo intento lo vuelva a pedir
        log.error({ err }, "No pude pedir el código de vinculación");
      }
    }, 3000);
  }

  raw.ev.on("creds.update", saveCreds);

  raw.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      log.info("Escaneá este QR con el WhatsApp del bot");
      qrcode.generate(qr, { small: true });
      // El string crudo, para regenerar el QR como imagen fuera del contenedor.
      log.info(`QR_RAW ${qr}`);
    }
    if (connection === "close") {
      const code = (lastDisconnect?.error as Boom)?.output?.statusCode;
      if (code === DisconnectReason.loggedOut) {
        log.error("La sesión se cerró desde el teléfono. Borrar authDir y vincular de nuevo.");
        void notifyTelegram(
          "OlivIA: la sesión de WhatsApp se cerró desde el teléfono. Hay que " +
            "escanear el QR de nuevo, no se reconecta sola.",
        );
        return;
      }
      // Reconexión con backoff y una sola cadena en vuelo, para no martillar a
      // WhatsApp (que puede terminar en ban del número).
      if (reconnecting) return;
      reconnecting = true;
      failuresInARow += 1;
      log.warn({ code, failuresInARow }, "Conexión cerrada, reconectando en 3s");
      if (failuresInARow >= NOTIFY_AFTER_FAILURES && !downtimeNotified) {
        downtimeNotified = true;
        void notifyTelegram(
          `OlivIA: lleva ${failuresInARow} intentos sin reconectar a WhatsApp. ` +
            "Puede necesitar un QR nuevo, revisá el servidor.",
        );
      }
      setTimeout(() => {
        reconnecting = false;
        startWhatsApp(onMessage);
      }, 3000);
    }
    if (connection === "open") {
      log.info("WhatsApp conectado");
      if (downtimeNotified) {
        downtimeNotified = false;
        void notifyTelegram("OlivIA: se reconectó a WhatsApp, ya está andando de nuevo.");
      }
      failuresInARow = 0;
      void setUpProfile(raw);
    }
  });

  raw.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;

    for (const m of messages) {
      const chat = m.key.remoteJid;
      if (!chat || m.key.fromMe) continue;

      // El participante importa en grupos; en chat directo es el chat mismo.
      const author = m.key.participant ?? chat;
      if (!isAllowed(author)) {
        log.warn({ author }, "Mensaje de un número fuera de la whitelist, descartado");
        continue;
      }

      // El doble tilde azul antes de contestar: da la sensación de que ya lo
      // vio, no solo que está tipeando.
      void raw.readMessages([m.key]).catch(() => {});

      const content = unwrap(m.message);
      const text = extractText(content);

      if (isGroup(chat)) {
        // contextInfo cuelga de cada tipo de mensaje, no solo del de texto.
        const ctx =
          content.extendedTextMessage?.contextInfo ??
          content.audioMessage?.contextInfo ??
          content.imageMessage?.contextInfo ??
          content.videoMessage?.contextInfo;

        // Un audio suelto llega con text vacío, así que en grupo hay que
        // mencionarla o citarla. Cuando haya transcripción (fase 2) se puede
        // transcribir primero y buscar el nombre ahí.
        const addressed = addressesBot(
          text,
          ctx?.mentionedJid ?? [],
          ctx?.participant === raw.user?.id,
          raw.user?.id,
        );
        if (!addressed) continue;
      }

      let kind: InboundMessage["kind"] = "text";
      let mediaPath: string | undefined;

      if (content.audioMessage) {
        kind = "audio";
        // TODO: el brain transcribe. Acá solo bajamos el archivo.
        const buf = (await downloadMediaMessage(m, "buffer", {})) as Buffer;
        mediaPath = join(config.mediaDir, `audio-${m.key.id}.ogg`);
        await writeFile(mediaPath, buf);
      } else if (content.imageMessage) {
        kind = "image";
        const buf = (await downloadMediaMessage(m, "buffer", {})) as Buffer;
        mediaPath = join(config.mediaDir, `img-${m.key.id}.jpg`);
        await writeFile(mediaPath, buf);
      }

      onMessage({
        id: m.key.id ?? "",
        chat,
        from: author,
        text,
        kind,
        mediaPath,
        timestamp: Number(m.messageTimestamp ?? Date.now() / 1000) * 1000,
      });
    }
  });

  return sock;
}

async function sendOnce(sock: WASocket, out: OutboundMessage): Promise<void> {
  if (out.imagePath) {
    await sock.sendMessage(out.chat, {
      image: { url: out.imagePath },
      caption: out.caption ?? out.text,
    });
    return;
  }
  if (out.text) {
    await sock.sendMessage(out.chat, { text: out.text });
  }
}

// La conexión tiene microcortes cada tanto (unos segundos, se reconecta sola).
// Si el envío pega justo en esa ventana, falla una vez y se pierde la
// respuesta para siempre si no se reintenta. Con estos reintentos, el segundo o
// tercer intento ya encuentra la conexión repuesta.
const SEND_RETRIES = 3;
const SEND_RETRY_DELAY_MS = 2500;

export async function send(sock: WASocket, out: OutboundMessage): Promise<void> {
  let lastErr: unknown;
  for (let intento = 1; intento <= SEND_RETRIES; intento++) {
    try {
      await sendOnce(sock, out);
      return;
    } catch (err) {
      lastErr = err;
      if (intento < SEND_RETRIES) {
        log.warn({ err, intento }, "No se pudo enviar, reintentando");
        await new Promise((r) => setTimeout(r, SEND_RETRY_DELAY_MS));
      }
    }
  }
  throw lastErr;
}
