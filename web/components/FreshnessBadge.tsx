import type { Source } from "@/lib/api";
import { formatAsOf } from "@/lib/format";

/** "Live · as of …" or, when the API couldn't be reached and the bundled copy is shown,
 * "Snapshot · as of …" in the caution colour. Same wording as Today's badge. */
export function FreshnessBadge({ source, asOf }: { source: Source; asOf?: string | null }) {
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-[12px] ${
        source === "snapshot" ? "bg-caution-bg text-caution" : "border border-line text-ink-2"
      }`}
    >
      {source === "snapshot" ? "Snapshot" : "Live"}
      {asOf ? ` · as of ${formatAsOf(asOf)}` : ""}
    </span>
  );
}
