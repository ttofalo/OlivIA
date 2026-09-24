function required(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`Falta la variable de entorno ${name}`);
  return v;
}

// Whitelist vacía o "*" = le responde a cualquiera. Sin filtro por número.
const allowedRaw = (process.env.WSP_ALLOWED_NUMBERS ?? "").trim();
const allowAll = allowedRaw === "" || allowedRaw === "*";

export const config = {
  allowedNumbers: allowAll
    ? []
    : allowedRaw
        .split(",")
        .map((n) => n.trim())
        .filter(Boolean),
  allowAll,
  // Número del bot en formato internacional sin +, para el código de
  // vinculación (ej: 5493543316750). Si está, se vincula por código en vez de QR.
  botNumber: (process.env.WSP_BOT_NUMBER ?? "").replace(/[^0-9]/g, ""),
  alertChat: process.env.WSP_ALERT_CHAT ?? "",
  // Foto de perfil, "acerca de" y nombre del contacto en WhatsApp. Se suben
  // una sola vez por sesión vinculada, no en cada reconexión. El nombre es lo
  // que ve alguien que no te tiene agendado.
  avatarPath: process.env.WSP_AVATAR_PATH ?? "./assets/avatar.jpg",
  statusText: process.env.WSP_STATUS_TEXT ?? "Asistente de la casa",
  profileName: process.env.WSP_PROFILE_NAME ?? "OlivIA Asistente Personal",
  // Bot de Telegram para avisos operativos (la sesión de WhatsApp se cayó o
  // volvió). Sin estas dos variables, no manda nada.
  telegram: {
    botToken: process.env.TELEGRAM_BOT_TOKEN ?? "",
    chatId: process.env.TELEGRAM_CHAT_ID ?? "",
  },
  botName: (process.env.WSP_BOT_NAME ?? "olivia").toLowerCase(),
  authDir: process.env.WSP_AUTH_DIR ?? "./baileys_auth",
  mqtt: {
    host: required("MQTT_HOST"),
    port: Number(process.env.MQTT_PORT ?? 8883),
    tls: process.env.MQTT_TLS !== "false",
    username: required("MQTT_USER_GATEWAY"),
    password: required("MQTT_PASS_GATEWAY"),
    // Ruta al ca.crt del broker. El broker usa una CA propia; sin esto la
    // verificación TLS falla contra el almacén del sistema.
    caCert: process.env.MQTT_CA_CERT ?? "",
  },
  mediaDir: process.env.MEDIA_DIR ?? "/media",
};

/** El jid de WhatsApp trae sufijo. Lo sacamos para comparar con la whitelist. */
export function numberFromJid(jid: string): string {
  return jid.split("@")[0].split(":")[0];
}

export function isAllowed(jid: string): boolean {
  if (config.allowAll) return true;
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
