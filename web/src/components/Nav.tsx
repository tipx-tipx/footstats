"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Nawigacja w trzech logicznych grupach:
 *   1. codzienna praca — Okazje, Mecze
 *   2. Twoje rzeczy   — Moje zakłady
 *   3. zaufanie       — Skuteczność, Jak to działa
 * Grupy oddziela cienka pionowa kreska; aktywna strona to zielona pastylka.
 */
const GRUPY: { href: string; label: string }[][] = [
  [
    { href: "/", label: "Okazje" },
    { href: "/mecze", label: "Mecze" },
  ],
  [{ href: "/zaklady", label: "Moje zakłady" }],
  [
    { href: "/model", label: "Skuteczność" },
    { href: "/jak-to-dziala", label: "Jak to działa" },
  ],
];

export function Nav() {
  const pathname = usePathname();
  if (pathname === "/login") return null;
  return (
    <header className="sticky top-0 z-40 border-b border-hairline bg-card/90 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-5 px-4 sm:px-6">
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2"
          aria-label="FootStats — strona główna"
        >
          <Image
            src="/logo.png"
            alt="FootStats"
            width={126}
            height={40}
            priority
            className="h-9 w-auto"
          />
        </Link>
        <nav
          aria-label="Główna nawigacja"
          className="flex h-full flex-1 items-center gap-2 overflow-x-auto"
        >
          {GRUPY.map((grupa, gi) => (
            <div key={gi} className="flex items-center gap-1">
              {gi > 0 && (
                <span
                  aria-hidden
                  className="mx-1.5 hidden h-5 w-px bg-hairline-strong sm:block"
                />
              )}
              {grupa.map(({ href, label }) => {
                const active =
                  href === "/" ? pathname === "/" : pathname.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm transition-colors ${
                      active
                        ? "bg-brand-wash font-semibold text-brand-deep"
                        : "text-muted hover:bg-paper hover:text-ink"
                    }`}
                  >
                    {label}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <button
          onClick={async () => {
            await fetch("/api/login", { method: "DELETE" });
            window.location.href = "/login";
          }}
          title="Wyloguj"
          aria-label="Wyloguj"
          className="shrink-0 rounded-lg p-2 text-faint transition-colors hover:bg-paper hover:text-ink"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </header>
  );
}
