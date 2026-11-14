"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "Today", icon: "today" },
  { href: "/research", label: "Research", icon: "research" },
  { href: "/people", label: "People", icon: "people" },
] as const;

function TabIcon({ name }: { name: (typeof TABS)[number]["icon"] }) {
  if (name === "today") {
    return (
      <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
        <path d="M5 5.5h14v13H5zM8 3v5M16 3v5M5 10h14" fill="none" stroke="currentColor" strokeWidth="1.7" />
      </svg>
    );
  }
  if (name === "research") {
    return (
      <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
        <path d="M5 19V9m5 10V5m5 14v-7m4 7V3" fill="none" stroke="currentColor" strokeWidth="1.8" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      <circle cx="9" cy="8" r="3" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="17" cy="10" r="2.5" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M3.5 19c.6-3.4 2.4-5 5.5-5s4.9 1.6 5.5 5M14 15c3.7-.7 5.8.6 6.5 4" fill="none" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

export function TabBar() {
  const path = usePathname();
  return (
    <nav aria-label="Main" className="grid grid-cols-3">
      {TABS.map((t) => {
        const active = t.href === "/" ? path === "/" : path.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            aria-current={active ? "page" : undefined}
            className={`flex min-h-12 flex-col items-center justify-center gap-0.5 text-[12px] ${
              active ? "font-semibold text-ink" : "text-ink-3"
            }`}
          >
            <TabIcon name={t.icon} />
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
