import { readFileSync } from "node:fs";
import mqtt, { type MqttClient } from "mqtt";
import { config } from "./config.js";

export const TOPIC_IN = "wsp/in";
export const TOPIC_OUT = "wsp/out";

/** Mensaje que el gateway publica cuando entra algo por WhatsApp. */
export interface InboundMessage {
  id: string;
  chat: string;
  from: string;
  /** Texto del mensaje, o la transcripción si vino como audio. */
  text: string;
  kind: "text" | "audio" | "image";
  /** Ruta al archivo en el volumen compartido, para audios e imágenes. */
  mediaPath?: string;
  timestamp: number;
}

/** Respuesta que el brain pide enviar. */
export interface OutboundMessage {
  chat: string;
  text?: string;
  /** Ruta a una imagen en el volumen compartido. */
  imagePath?: string;
  caption?: string;
  /** Si viene, el gateway responde citando ese mensaje. */
  replyTo?: string;
}

export function connectBus(): MqttClient {
  const proto = config.mqtt.tls ? "mqtts" : "mqtt";
  const ca = config.mqtt.tls && config.mqtt.caCert ? readFileSync(config.mqtt.caCert) : undefined;
  return mqtt.connect(`${proto}://${config.mqtt.host}:${config.mqtt.port}`, {
    username: config.mqtt.username,
    password: config.mqtt.password,
    reconnectPeriod: 2000,
    ca,
  });
}

export function publishInbound(client: MqttClient, msg: InboundMessage): void {
  client.publish(TOPIC_IN, JSON.stringify(msg), { qos: 1 });
}
