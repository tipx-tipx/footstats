"use client";

import { usePathname } from "next/navigation";

/** Stopka — ukryta na ekranie logowania. */
export function SiteFooter({
  zrodlo,
  liga,
  sezon,
  meczow,
  aktualizacja,
}: {
  zrodlo: string;
  liga: string;
  sezon: string;
  meczow: number;
  aktualizacja: string;
}) {
  const pathname = usePathname();
  if (pathname === "/login") return null;
  return (
    <footer className="border-t border-hairline bg-card">
      <div className="mx-auto flex max-w-6xl flex-col gap-1 px-4 py-6 text-xs text-faint sm:px-6">
        <p>
          FootStats · narzędzie analityczne — nie gwarantuje wygranych. Graj
          odpowiedzialnie, obstawiaj wyłącznie u legalnych bukmacherów.
        </p>
        <p>
          Dane: {zrodlo} · {liga} {sezon} · {meczow} meczów w bazie ·
          aktualizacja: {aktualizacja}
        </p>
      </div>
    </footer>
  );
}
