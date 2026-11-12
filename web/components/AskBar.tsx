"use client";

// The Ask agent is a P1 item (spec §11.3). Until it works on real data the bar is shown
// disabled with an honest label rather than a fake response.
export function AskBar() {
  return (
    <form className="px-4 pt-2" onSubmit={(e) => e.preventDefault()}>
      <label htmlFor="ask" className="sr-only">
        Ask FINN
      </label>
      <input
        id="ask"
        disabled
        placeholder="Ask FINN — not available yet"
        className="h-11 w-full rounded-lg border border-line bg-surface px-3 text-[15px] placeholder:text-ink-3 disabled:opacity-70"
      />
    </form>
  );
}
