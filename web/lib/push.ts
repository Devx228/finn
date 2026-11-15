export function base64UrlToUint8Array(value: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

export function briefPushUrl(itemId: string): string {
  const id = encodeURIComponent(itemId);
  return `/?w=7d&item=${id}#brief-${id}`;
}

/** Register the push worker, then wait for the browser to expose an active registration. */
export async function activePushRegistration(
  container: Pick<ServiceWorkerContainer, "register" | "ready">,
): Promise<ServiceWorkerRegistration> {
  await container.register("/sw.js");
  return container.ready;
}
