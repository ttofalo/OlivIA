function required(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`Falta la variable de entorno ${name}`);
  return v;
}

export const config = {
  allowedNumbers: required("WSP_ALLOWED_NUMBERS")
    .split(",")
    .map((n) => n.trim())
    .filter(Boolean),
  alertChat: process.env.WSP_ALERT_CHAT ?? "",
  botName: (process.env.WSP_BOT_NAME ?? "olivia").toLowerCase(),
  authDir: process.env.WSP_AUTH_DIR ?? "./baileys_auth",
  mqtt: {
    host: required("MQTT_HOST"),
    port: Number(process.env.MQTT_PORT ?? 8883),
    tls: process.env.MQTT_TLS !== "false",
    username: required("MQTT_USER_GATEWAY"),
    password: required("MQTT_PASS_GATEWAY"),
  },
  mediaDir: process.env.MEDIA_DIR ?? "/media",
};

/** El jid de WhatsApp trae sufijo. Lo sacamos para comparar con la whitelist. */
export function numberFromJid(jid: string): string {
  return jid.split("@")[0].split(":")[0];
}

export function isAllowed(jid: string): boolean {
  return config.allowedNumbers.includes(numberFromJid(jid));
}

export function isGroup(jid: string): boolean {
  return jid.endsWith("@g.us");
}

/**
 * En un grupo familiar el bot no puede contestar todo. Responde cuando lo
 * nombran, la mencionan con arroba o le citan un mensaje suyo.
 */
export function addressesBot(text: string, mentions: string[], quotedFromBot: boolean, selfJid?: string): boolean {
  if (quotedFromBot) return true;
  if (selfJid && mentions.includes(selfJid)) return true;
  return text.toLowerCase().includes(config.botName);
}
