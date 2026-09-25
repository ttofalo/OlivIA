import { describe, expect, it, vi } from "vitest";

process.env.WSP_ALLOWED_NUMBERS = "";
process.env.MQTT_HOST = "localhost";
process.env.MQTT_USER_GATEWAY = "gateway";
process.env.MQTT_PASS_GATEWAY = "secreto";

const { send } = await import("./whatsapp.js");

function fakeSocket(sendMessage: (...args: unknown[]) => Promise<unknown>) {
  return { sendMessage } as unknown as Parameters<typeof send>[0];
}

describe("send", () => {
  it("manda una vez cuando sale bien de entrada", async () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    await send(fakeSocket(sendMessage), { chat: "c1", text: "hola" });
    expect(sendMessage).toHaveBeenCalledTimes(1);
  });

  it("reintenta si el primer envío falla, y no vuelve a fallar el segundo", async () => {
    vi.useFakeTimers();
    const sendMessage = vi
      .fn()
      .mockRejectedValueOnce(new Error("Connection Closed"))
      .mockResolvedValueOnce(undefined);

    const done = send(fakeSocket(sendMessage), { chat: "c1", text: "hola" });
    await vi.runAllTimersAsync();
    await done;

    expect(sendMessage).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });

  it("si fallan los tres intentos, propaga el último error", async () => {
    vi.useFakeTimers();
    const err = new Error("Connection Closed");
    const sendMessage = vi.fn().mockRejectedValue(err);

    const done = send(fakeSocket(sendMessage), { chat: "c1", text: "hola" });
    const assertion = expect(done).rejects.toThrow("Connection Closed");
    await vi.runAllTimersAsync();
    await assertion;

    expect(sendMessage).toHaveBeenCalledTimes(3);
    vi.useRealTimers();
  });

  it("la imagen usa el caption si viene, o el texto si no", async () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    await send(fakeSocket(sendMessage), {
      chat: "c1",
      imagePath: "/media/foto.jpg",
      caption: "Cochera",
    });
    expect(sendMessage).toHaveBeenCalledWith("c1", {
      image: { url: "/media/foto.jpg" },
      caption: "Cochera",
    });
  });
});
