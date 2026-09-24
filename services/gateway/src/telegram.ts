import pino from "pino";
import { config } from "./config.js";

const log = pino({ level: process.env.LOG_LEVEL ?? "info" });

/**
 * Avisos operativos por Telegram: si la sesión de WhatsApp se cae, WhatsApp
 * mismo no sirve para avisar. Sin token configurado, no hace nada (el bot
 * de Telegram es opcional).
 */
export async function notifyTelegram(text: string): Promise<void> {
  const { botToken, chatId } = config.telegram;
  if (!botToken || !chatId) return;
  try {
    const res = await fetch(`https://api.telegram.org/bot${botToken}/sendMessage`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text }),
    });
    if (!res.ok) {
      log.warn({ status: res.status, body: await res.text() }, "Telegram rechazó el aviso");
    }
  } catch (err) {
    // Un aviso que falla no puede tumbar el gateway: se loguea y se sigue.
    log.warn({ err }, "No pude mandar el aviso a Telegram");
  }
}
