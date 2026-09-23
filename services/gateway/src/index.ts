import pino from "pino";
import { connectBus, publishInbound, TOPIC_OUT, type OutboundMessage } from "./bus.js";
import { send, startWhatsApp } from "./whatsapp.js";

const log = pino({ level: process.env.LOG_LEVEL ?? "info" });

async function main() {
  const bus = connectBus();

  bus.on("connect", () => {
    log.info("MQTT conectado");
    bus.subscribe(TOPIC_OUT, { qos: 1 });
  });
  bus.on("error", (err) => log.error({ err }, "Error de MQTT"));

  const sock = await startWhatsApp((msg) => {
    log.info({ from: msg.from, kind: msg.kind }, "Mensaje entrante");
    // "Escribiendo..." al instante, antes de que el brain decida nada: es lo
    // que hace sentir la respuesta inmediata.
    void sock.sendPresenceUpdate("composing", msg.chat).catch(() => {});
    publishInbound(bus, msg);
  });

  bus.on("message", async (topic, payload) => {
    if (topic !== TOPIC_OUT) return;
    try {
      const out = JSON.parse(payload.toString()) as OutboundMessage;
      await send(sock, out);
    } catch (err) {
      log.error({ err }, "No se pudo enviar la respuesta");
    }
  });
}

main().catch((err) => {
  log.fatal({ err }, "El gateway se cayó al arrancar");
  process.exit(1);
});
