import { Suspense } from "react";
import { People } from "@/components/People";

export default function PeoplePage() {
  return (
    <Suspense fallback={<p className="text-[14px] text-ink-3">Loading people…</p>}>
      <People />
    </Suspense>
  );
}
