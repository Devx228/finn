// Display formatting. All times shown in IST (spec §11.4).

const IST = "Asia/Kolkata";

export function formatAsOf(iso: string): string {
  const d = new Date(iso);
  const date = d.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: IST });
  const time = d.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: IST,
  });
  return `${date}, ${time} IST`;
}

export function formatToday(now: Date = new Date()): string {
  return now.toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: IST,
  });
}
