"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "Today" },
  { href: "/research", label: "Research" },
  { href: "/people", label: "People" },
] as const;

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
            className={`flex min-h-12 items-center justify-center text-[15px] ${
              active ? "font-semibold text-ink" : "text-ink-3"
            }`}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
