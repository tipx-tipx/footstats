"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Okazje" },
  { href: "/mecze", label: "Mecze" },
  { href: "/zaklady", label: "Moje zakłady" },
  { href: "/model", label: "Skuteczność modelu" },
  { href: "/jak-to-dziala", label: "Jak to działa" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-40 border-b border-hairline bg-card/90 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4 sm:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-2" aria-label="FootStats — strona główna">
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
          className="-mb-px flex h-full flex-1 items-stretch gap-1 overflow-x-auto"
        >
          {LINKS.map(({ href, label }) => {
            const active =
              href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`relative flex items-center whitespace-nowrap px-3 text-sm transition-colors ${
                  active
                    ? "font-semibold text-brand"
                    : "text-muted hover:text-ink"
                }`}
              >
                {label}
                {active && (
                  <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-brand" />
                )}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
