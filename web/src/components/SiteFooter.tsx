import { Logo } from "./Logo";

/**
 * Stopka produktu. Renderowana WYŁĄCZNIE w app/(app)/layout.tsx — /login żyje
 * poza tą grupą tras (server component, bez "use client").
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
  const dane: { label: string; value: string }[] = [
    { label: "Dane", value: zrodlo },
    { label: "Rozgrywki", value: `${liga} ${sezon}` },
    { label: "Meczów w bazie", value: String(meczow) },
    { label: "Aktualizacja", value: aktualizacja },
  ];
  return (
    <footer className="border-t border-hairline bg-card">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6 md:flex-row md:items-start md:justify-between">
        <div className="max-w-sm">
          <Logo className="h-9 w-auto" />
          <p className="mt-2.5 text-xs leading-relaxed text-faint">
            Narzędzie analityczne, nie gwarantuje wygranych. Graj
            odpowiedzialnie, obstawiaj wyłącznie u legalnych bukmacherów.
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-x-10 gap-y-4 sm:grid-cols-4 md:gap-x-12">
          {dane.map((d) => (
            <div key={d.label}>
              <dt className="text-[10px] font-semibold uppercase tracking-wider text-faint">
                {d.label}
              </dt>
              <dd className="mt-1 text-xs leading-relaxed text-ink-soft">
                {d.value}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </footer>
  );
}
