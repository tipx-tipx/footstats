"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Logo } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";

/**
 * Nawigacja w trzech logicznych grupach:
 *   1. codzienna praca — Okazje, Kupony, Mecze
 *   2. Twoje rzeczy   — Moje zakłady
 *   3. zaufanie       — Skuteczność, Jak to działa
 * Desktop (md+): pasek z pastylką aktywnej strony, która PŁYNIE między
 * pozycjami (framer-motion layoutId). Mobile: hamburger + panel na scrimie.
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

function IkonaWyloguj() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" aria-hidden>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const reduced = useReducedMotion();

  // blokuj scroll tła, gdy panel mobilny otwarty (menu zamyka klik w link)
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  // zmiana trasy zamyka panel (np. wstecz w przeglądarce) — korekta stanu
  // w trakcie renderu zamiast effectu (bez kaskadowego renderu)
  const [prevPathname, setPrevPathname] = useState(pathname);
  if (prevPathname !== pathname) {
    setPrevPathname(pathname);
    setOpen(false);
  }

  return (
    <header className="sticky top-0 z-40 px-3 pt-3 sm:px-6">
      {/* scrim pod panelem mobilnym — poza szklanym kontenerem (backdrop-filter
          robi z niego containing block dla position:fixed) */}
      <AnimatePresence>
        {open && (
          <motion.button
            aria-label="Zamknij menu"
            tabIndex={-1}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            onClick={() => setOpen(false)}
            className="fixed inset-0 -z-10 cursor-default bg-scrim lg:hidden"
          />
        )}
      </AnimatePresence>
      <div className="mx-auto max-w-6xl overflow-hidden rounded-(--radius-card) border border-hairline bg-card/75 shadow-(--shadow-pop) backdrop-blur-2xl">
      <div className="flex h-14 items-center gap-4 px-4 sm:px-5">
        <Link
          href="/"
          className="shrink-0 rounded-lg transition-opacity hover:opacity-80"
          aria-label="FootStats, strona główna"
        >
          <Logo className="h-10 w-auto" />
        </Link>

        {/* pasek desktopowy */}
        <nav
          aria-label="Główna nawigacja"
          className="hidden h-full flex-1 items-center gap-1 lg:flex"
        >
          {GRUPY.map((grupa, gi) => (
            <div key={gi} className="flex items-center gap-0.5">
              {gi > 0 && (
                <span aria-hidden className="mx-2 h-5 w-px bg-hairline" />
              )}
              {grupa.map(({ href, label }) => {
                const active = jestAktywna(pathname, href);
                return (
                  <Link
                    key={href}
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={`relative whitespace-nowrap rounded-(--radius-control) px-3 py-2 text-sm transition-colors ${
                      active
                        ? "font-semibold text-brand-deep"
                        : "text-muted hover:bg-paper hover:text-ink"
                    }`}
                  >
                    {active && (
                      <motion.span
                        layoutId="nav-pastylka"
                        aria-hidden
                        transition={
                          reduced
                            ? { duration: 0 }
                            : { type: "spring", stiffness: 520, damping: 42 }
                        }
                        className="absolute inset-0 rounded-(--radius-control) bg-brand-wash"
                      />
                    )}
                    <span className="relative">{label}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-1 lg:ml-0">
          <ThemeToggle />
          <button
            onClick={wyloguj}
            title="Wyloguj"
            aria-label="Wyloguj"
            className="hidden shrink-0 rounded-(--radius-control) p-2.5 text-faint transition-colors hover:bg-paper hover:text-ink lg:block"
          >
            <IkonaWyloguj />
          </button>

          {/* hamburger — tylko mobile */}
          <button
            onClick={() => setOpen((v) => !v)}
            className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-(--radius-control) text-ink transition-colors hover:bg-paper lg:hidden"
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
      </div>

      {/* panel mobilny — płynne rozwijanie (grid 0fr -> 1fr) */}
      <div
        id="menu-mobilne"
        aria-hidden={!open}
        className={`grid overflow-hidden transition-[grid-template-rows] duration-300 ease-out lg:hidden ${
          open ? "grid-rows-[1fr] border-t border-hairline" : "grid-rows-[0fr]"
        }`}
      >
        <nav
          aria-label="Menu mobilne"
          className={`min-h-0 overflow-hidden bg-card transition-opacity duration-200 ${
            open ? "opacity-100" : "opacity-0"
          }`}
        >
          <div className="flex flex-col px-3 py-2 pb-3">
            {GRUPY.map((grupa, gi) => (
              <div
                key={gi}
                className={gi > 0 ? "mt-1.5 border-t border-hairline pt-1.5" : ""}
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
                      className={`flex items-center justify-between rounded-(--radius-control) px-3.5 py-3 text-[15px] transition-colors ${
                        active
                          ? "bg-brand-wash font-semibold text-brand-deep"
                          : "text-ink hover:bg-paper"
                      }`}
                    >
                      {label}
                      {active && (
                        <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-brand" />
                      )}
                    </Link>
                  );
                })}
              </div>
            ))}
            <button
              onClick={wyloguj}
              tabIndex={open ? undefined : -1}
              className="mt-1.5 flex items-center gap-2.5 border-t border-hairline px-3.5 py-3 pt-3.5 text-left text-[15px] text-faint transition-colors hover:text-ink"
            >
              <IkonaWyloguj />
              Wyloguj
            </button>
          </div>
        </nav>
      </div>
      </div>
    </header>
  );
}
