/**
 * Stopka. Renderowana WYŁĄCZNIE w app/(app)/layout.tsx — /login żyje poza tą
 * grupą tras i tego nie widzi, więc nie trzeba już sprawdzać pathname
 * (server component, bez "use client").
 */
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
