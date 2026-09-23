import { describe, expect, it } from "vitest";

process.env.WSP_ALLOWED_NUMBERS = "5493511111111, 5493522222222";
process.env.MQTT_HOST = "localhost";
process.env.MQTT_USER_GATEWAY = "gateway";
process.env.MQTT_PASS_GATEWAY = "secreto";
process.env.WSP_BOT_NAME = "Olivia";

const { addressesBot, isAllowed, isGroup, numberFromJid } = await import("./config.js");

describe("config", () => {
  it("saca sufijo y dispositivo del jid", () => {
    expect(numberFromJid("5493511111111:7@s.whatsapp.net")).toBe("5493511111111");
  });

  it("acepta solamente números permitidos", () => {
    expect(isAllowed("5493511111111@s.whatsapp.net")).toBe(true);
    expect(isAllowed("5493533333333@s.whatsapp.net")).toBe(false);
  });

  it("reconoce grupos", () => {
    expect(isGroup("120363000000000000@g.us")).toBe(true);
    expect(isGroup("5493511111111@s.whatsapp.net")).toBe(false);
  });

  it("responde una cita a un mensaje propio", () => {
    expect(addressesBot("", [], true)).toBe(true);
  });

  it("responde una mención por jid", () => {
    const jid = "5493500000000@s.whatsapp.net";
    expect(addressesBot("hola", [jid], false, jid)).toBe(true);
  });

  it("reconoce el nombre sin importar mayúsculas", () => {
    expect(addressesBot("OLIVIA, mostrame la entrada", [], false)).toBe(true);
  });

  it("ignora texto grupal sin su nombre", () => {
    expect(addressesBot("¿cómo está la entrada?", [], false)).toBe(false);
  });
});
