import { Suspense } from "react";
import { ResearchView } from "@/components/Research";

export default function ResearchPage() {
  return (
    <Suspense fallback={<p className="text-[14px] text-ink-3">Loading research…</p>}>
      <ResearchView />
    </Suspense>
  );
}
