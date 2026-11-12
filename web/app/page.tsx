import { Suspense } from "react";
import { Today } from "@/components/Today";

export default function Page() {
  return (
    <Suspense fallback={<p className="text-[14px] text-ink-3">Loading brief…</p>}>
      <Today />
    </Suspense>
  );
}
