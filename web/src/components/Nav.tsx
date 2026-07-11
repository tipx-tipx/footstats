"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * Nawigacja w trzech logicznych grupach:
 *   1. codzienna praca — Okazje, Kupony, Mecze
 *   2. Twoje rzeczy   — Moje zakłady
 *   3. zaufanie       — Skuteczność, Jak to działa
 * Desktop (sm+): jeden pasek z grupami oddzielonymi kreską; aktywna strona to
 * zielona pastylka. Mobile: logo + animowany hamburger rozwijający panel.
 */
const GRUPY: { href: string; label: string }[][] = [
  [
    { href: "/", label: "Okazje" },
    { href: "/kupony", label: "Kupony" },
    { href: "/mecze", label: "Mecze" },
  ],
  [{ href: "/zaklady", label: "Moje zakłady" }],
  [
    { href: "/model", label: "Skuteczność" },
    { href: "/jak-to-dziala", label: "Jak to działa" },
  ],
];

function jestAktywna(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

async function wyloguj() {
  await fetch("/api/login", { method: "DELETE" });
  window.location.href = "/login";
}

export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // blokuj scroll tła, gdy panel mobilny otwarty (menu zamyka klik w link)
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

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

        {/* pasek desktopowy */}
        <nav
          aria-label="Główna nawigacja"
          className="hidden h-full flex-1 items-center gap-2 overflow-x-auto sm:flex"
        >
          {GRUPY.map((grupa, gi) => (
            <div key={gi} className="flex items-center gap-1">
              {gi > 0 && (
                <span
                  aria-hidden
                  className="mx-1.5 h-5 w-px bg-hairline-strong"
                />
              )}
              {grupa.map(({ href, label }) => {
                const active = jestAktywna(pathname, href);
                return (
                  <Link
                    key={href}
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm transition-colors ${
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
          onClick={wyloguj}
          title="Wyloguj"
          aria-label="Wyloguj"
          className="hidden shrink-0 rounded-lg p-2.5 text-faint transition-colors hover:bg-paper hover:text-ink sm:block"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>

        {/* hamburger — tylko mobile */}
        <button
          onClick={() => setOpen((v) => !v)}
          className="relative ml-auto flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-ink transition-colors hover:bg-paper sm:hidden"
          aria-label={open ? "Zamknij menu" : "Otwórz menu"}
          aria-expanded={open}
          aria-controls="menu-mobilne"
        >
          <span aria-hidden className="relative block h-4 w-5">
            <span
              className={`absolute left-0 block h-0.5 w-5 rounded-full bg-current transition-all duration-300 ${
                open ? "top-1/2 -translate-y-1/2 rotate-45" : "top-0"
              }`}
            />
            <span
              className={`absolute left-0 top-1/2 block h-0.5 w-5 -translate-y-1/2 rounded-full bg-current transition-opacity duration-200 ${
                open ? "opacity-0" : "opacity-100"
              }`}
            />
            <span
              className={`absolute left-0 block h-0.5 w-5 rounded-full bg-current transition-all duration-300 ${
                open ? "bottom-1/2 translate-y-1/2 -rotate-45" : "bottom-0"
              }`}
            />
          </span>
        </button>
      </div>

      {/* panel mobilny — płynne rozwijanie (grid 0fr -> 1fr) */}
      <div
        id="menu-mobilne"
        aria-hidden={!open}
        className={`grid overflow-hidden transition-[grid-template-rows] duration-300 ease-out sm:hidden ${
          open ? "grid-rows-[1fr] border-t border-hairline" : "grid-rows-[0fr]"
        }`}
      >
        <nav
          aria-label="Menu mobilne"
          className={`min-h-0 overflow-hidden bg-card transition-opacity duration-200 ${
            open ? "opacity-100" : "opacity-0"
          }`}
        >
          <div className="flex flex-col px-3 py-2">
            {GRUPY.map((grupa, gi) => (
              <div
                key={gi}
                className={gi > 0 ? "mt-1 border-t border-hairline pt-1" : ""}
              >
                {grupa.map(({ href, label }) => {
                  const active = jestAktywna(pathname, href);
                  return (
                    <Link
                      key={href}
                      href={href}
                      onClick={() => setOpen(false)}
                      aria-current={active ? "page" : undefined}
                      tabIndex={open ? undefined : -1}
                      className={`flex items-center justify-between rounded-lg px-3 py-3 text-[15px] transition-colors ${
                        active
                          ? "bg-brand-wash font-semibold text-brand-deep"
                          : "text-ink hover:bg-paper"
                      }`}
                    >
                      {label}
                      {active && (
                        <span
                          aria-hidden
                          className="h-1.5 w-1.5 rounded-full bg-brand"
                        />
                      )}
                    </Link>
                  );
                })}
              </div>
            ))}
            <button
              onClick={wyloguj}
              tabIndex={open ? undefined : -1}
              className="mt-1 flex items-center gap-2 border-t border-hairline px-3 py-3 pt-3 text-left text-[15px] text-faint transition-colors hover:text-ink"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Wyloguj
            </button>
          </div>
        </nav>
      </div>
    </header>
  );
}
