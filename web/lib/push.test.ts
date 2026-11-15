import { describe, expect, it } from "vitest";
import { activePushRegistration, briefPushUrl } from "./push";

describe("web push deep links", () => {
  it("opens the related seven-day brief card", () => {
    expect(briefPushUrl("42")).toBe("/?w=7d&item=42#brief-42");
  });

  it("escapes an opaque item id", () => {
    expect(briefPushUrl("x/y")).toBe("/?w=7d&item=x%2Fy#brief-x%2Fy");
  });
});

describe("web push worker activation", () => {
  it("waits for the active registration instead of subscribing to an installing worker", async () => {
    const calls: string[] = [];
    const active = {} as ServiceWorkerRegistration;
    const container = {
      register: async (url: string) => {
        calls.push(`register:${url}`);
        return {} as ServiceWorkerRegistration;
      },
      get ready() {
        calls.push("ready");
        return Promise.resolve(active);
      },
    } as Pick<ServiceWorkerContainer, "register" | "ready">;

    await expect(activePushRegistration(container)).resolves.toBe(active);
    expect(calls).toEqual(["register:/sw.js", "ready"]);
  });
});
