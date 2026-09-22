import makeWASocket, {
  DisconnectReason,
  downloadMediaMessage,
  useMultiFileAuthState,
  type WASocket,
} from "@whiskeysockets/baileys";
import { Boom } from "@hapi/boom";
import { wrapSocket } from "baileys-antiban";
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import qrcode from "qrcode-terminal";
import pino from "pino";
import { addressesBot, config, isAllowed, isGroup } from "./config.js";
import type { InboundMessage, OutboundMessage } from "./bus.js";

const log = pino({ level: process.env.LOG_LEVEL ?? "info" });

export async function startWhatsApp(
  onMessage: (msg: InboundMessage) => void,
): Promise<WASocket> {
  const { state, saveCreds } = await useMultiFileAuthState(config.authDir);

  const raw = makeWASocket({
    auth: state,
    logger: log.child({ mod: "baileys" }),
    // Baileys marca en línea al número. Lo dejamos discreto.
    markOnlineOnConnect: false,
  });

  // El riesgo de que Meta banee el número es el más concreto del proyecto.
  // baileys-antiban mete jitter en los envíos, simula tipeo, hace warm-up de
  // siete días con un número nuevo y auto-pausa cuando detecta señales de ban.
  const sock = wrapSocket(raw);

  raw.ev.on("creds.update", saveCreds);

  raw.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      log.info("Escaneá este QR con el WhatsApp del bot");
      qrcode.generate(qr, { small: true });
    }
    if (connection === "close") {
      const code = (lastDisconnect?.error as Boom)?.output?.statusCode;
      if (code === DisconnectReason.loggedOut) {
        log.error("La sesión se cerró desde el teléfono. Borrar authDir y vincular de nuevo.");
        return;
      }
      log.warn({ code }, "Conexión cerrada, reconectando");
      startWhatsApp(onMessage);
    }
    if (connection === "open") log.info("WhatsApp conectado");
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

      const text =
        m.message?.conversation ??
        m.message?.extendedTextMessage?.text ??
        m.message?.imageMessage?.caption ??
        "";

      if (isGroup(chat)) {
        // contextInfo cuelga de cada tipo de mensaje, no solo del de texto.
        const msg = m.message ?? {};
        const ctx =
          msg.extendedTextMessage?.contextInfo ??
          msg.audioMessage?.contextInfo ??
          msg.imageMessage?.contextInfo ??
          msg.videoMessage?.contextInfo;

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

      if (m.message?.audioMessage) {
        kind = "audio";
        // TODO: el brain transcribe. Acá solo bajamos el archivo.
        const buf = (await downloadMediaMessage(m, "buffer", {})) as Buffer;
        mediaPath = join(config.mediaDir, `audio-${m.key.id}.ogg`);
        await writeFile(mediaPath, buf);
      } else if (m.message?.imageMessage) {
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

export async function send(sock: WASocket, out: OutboundMessage): Promise<void> {
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
