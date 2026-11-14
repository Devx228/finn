"use client";

import { useState } from "react";
import { API_BASE, postJson } from "@/lib/api";
import { base64UrlToUint8Array } from "@/lib/push";

const TOKEN_KEY = "finn.pushSubscription.v1";

type PushConfig = { available: boolean; public_key: string | null };
type ApiError = { detail?: { message?: string } };

function existingToken(): string {
  try {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function PushSettings() {
  const [token, setToken] = useState(existingToken);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const enable = async () => {
    setBusy(true);
    setMessage(null);
    try {
      if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
        setMessage("This browser does not support web push.");
        return;
      }
      const configResponse = await fetch(`${API_BASE}/api/push/config`, { cache: "no-store" });
      const config = (await configResponse.json()) as PushConfig;
      if (!configResponse.ok || !config.available || !config.public_key) {
        setMessage("Push delivery is not configured on the server yet.");
        return;
      }
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setMessage("Notifications remain off. You can enable them later in browser settings.");
        return;
      }
      const registration = await navigator.serviceWorker.register("/sw.js");
      const subscription =
        (await registration.pushManager.getSubscription()) ??
        (await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: base64UrlToUint8Array(config.public_key),
        }));
      const response = await postJson<{ subscription_id?: string } | ApiError>(
        "/api/push/subscribe",
        { subscription: subscription.toJSON() },
      );
      const id = (response.data as { subscription_id?: string }).subscription_id;
      if (!response.ok || !id) throw new Error((response.data as ApiError).detail?.message);
      window.localStorage.setItem(TOKEN_KEY, id);
      setToken(id);
      setMessage("Alerts are enabled on this device.");
    } catch (error) {
      setMessage(error instanceof Error && error.message ? error.message : "Could not enable alerts.");
    } finally {
      setBusy(false);
    }
  };

  const sendTest = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const response = await postJson<{ sent?: boolean } | ApiError>("/api/push/test", {
        subscription_id: token,
      });
      if (!response.ok || !(response.data as { sent?: boolean }).sent) {
        throw new Error((response.data as ApiError).detail?.message ?? "Could not send the test alert.");
      }
      setMessage("Test alert sent. Tap it to reopen the related brief card.");
    } catch (error) {
      setMessage(error instanceof Error && error.message ? error.message : "Could not send the test alert.");
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const registration = await navigator.serviceWorker.getRegistration();
      const subscription = await registration?.pushManager.getSubscription();
      await subscription?.unsubscribe();
      await postJson("/api/push/unsubscribe", { subscription_id: token });
      window.localStorage.removeItem(TOKEN_KEY);
      setToken("");
      setMessage("Alerts are off on this device.");
    } catch {
      setMessage("Could not turn alerts off. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mt-5 border-t border-line pt-4" aria-labelledby="notification-settings">
      <h3 id="notification-settings" className="text-[14px] font-semibold">
        Notifications
      </h3>
      <p className="mt-1 text-[13px] leading-snug text-ink-2">
        Get a browser alert when FINN has a card worth opening. Permission is requested only when you tap Enable.
      </p>
      <p className="mt-1 text-[12px] text-ink-3">On iPhone, add FINN to your Home Screen first.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {token ? (
          <>
            <button
              onClick={() => void sendTest()}
              disabled={busy}
              className="min-h-11 rounded-md bg-ink px-4 text-[13px] font-semibold text-bg disabled:opacity-50"
            >
              Send test alert
            </button>
            <button
              onClick={() => void disable()}
              disabled={busy}
              className="min-h-11 rounded-md border border-line px-4 text-[13px] text-ink-2 disabled:opacity-50"
            >
              Turn off
            </button>
          </>
        ) : (
          <button
            onClick={() => void enable()}
            disabled={busy}
            className="min-h-11 rounded-md bg-ink px-4 text-[13px] font-semibold text-bg disabled:opacity-50"
          >
            {busy ? "Enabling…" : "Enable alerts"}
          </button>
        )}
      </div>
      {message && <p className="mt-2 text-[12px] leading-snug text-ink-2">{message}</p>}
    </section>
  );
}
