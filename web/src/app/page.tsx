import Link from "next/link";

import { ValueBoard } from "@/components/ValueBoard";
import { getMeta, getValueBets, getZawodnicy } from "@/lib/data";
import { fmtEV } from "@/lib/format";

export default async function OkazjePage({
  searchParams,
}: {
  searchParams: Promise<{ mecz?: string }>;
}) {
  const { mecz } = await searchParams;
  const [bets, zawodnicy, meta] = await Promise.all([
    getValueBets(),
    getZawodnicy(),
    getMeta(),
  ]);

  const okazje = bets.filter((b) => !b.sugestia);
  const naj = okazje.find((b) => b.ev_pct != null);
  const wysokaPewnosc = okazje.filter((b) => b.pewnosc === "wysoka").length;
  const aktualizacja = new Intl.DateTimeFormat("pl-PL", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  }).format(new Date(meta.wygenerowano_ts * 1000));

  return (
    <>
      {/* hero */}
      <section className="pitch-grid -mx-4 mb-8 border-b border-hairline bg-card px-4 pb-8 pt-10 sm:-mx-6 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <p className="mb-1 text-xs font-medium uppercase tracking-widest text-brand">
            Skan rynków · {meta.liga} {meta.sezon}
          </p>
          <h1 className="max-w-2xl text-3xl font-bold leading-tight sm:text-4xl">
            Gdzie kurs jest <span className="text-brand">zawyżony</span>{" "}
            względem matematyki
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">
            Model szacuje szansę każdego zdarzenia (strzały, faule, odbiory…)
            na podstawie historii, minut, rywala i sędziego — a potem porównuje
            ją z kursem bukmachera. Poniżej tylko te zakłady, gdzie kurs płaci
            lepiej, niż powinien.
          </p>

          <dl className="mt-6 flex flex-wrap gap-x-10 gap-y-4">
            <div>
              <dt className="text-xs text-faint">znalezione okazje</dt>
              <dd className="font-data text-2xl font-semibold text-ink">
                {okazje.length}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-faint">z wysoką pewnością</dt>
              <dd className="font-data text-2xl font-semibold text-ink">
                {wysokaPewnosc}
              </dd>
            </div>
            {naj?.ev_pct != null && (
              <div>
                <dt className="text-xs text-faint">najlepsza wartość</dt>
                <dd className="font-data text-2xl font-semibold text-data-green">
                  {fmtEV(naj.ev_pct)}
                </dd>
              </div>
            )}
            <div>
              <dt className="text-xs text-faint">meczów w analizie</dt>
              <dd className="font-data text-2xl font-semibold text-ink">
                {meta.meczow_demo}
              </dd>
            </div>
          </dl>

          <p className="mt-5 text-xs text-faint">
            Dane odświeżane automatycznie co ok. 30 minut · ostatnia
            aktualizacja:{" "}
            <span className="font-data font-medium text-ink-soft">
              {aktualizacja}
            </span>{" "}
            ·{" "}
            <Link
              href="/jak-to-dziala"
              className="font-medium text-brand underline-offset-2 hover:underline"
            >
              Jak to działa? →
            </Link>
          </p>

          {meta.tryb === "demo" && (
            <p className="mt-6 inline-flex items-center gap-2 rounded-lg border border-data-amber/40 bg-data-amber-wash px-3 py-2 text-xs text-[#8a5613]">
              <span aria-hidden>ⓘ</span>
              Tryb pokazowy: statystyki zawodników są prawdziwe ({meta.liga}{" "}
              {meta.sezon}), ale kursy są przykładowe — trwa przerwa między
              sezonami. Po starcie sezonu wpiszesz tu realne kursy.
            </p>
          )}
          {meta.tryb === "ms2026" && bets.length === 0 && (
            <div className="mt-6 max-w-2xl rounded-lg border border-data-amber/40 bg-data-amber-wash px-4 py-3 text-xs leading-relaxed text-[#8a5613]">
              <p className="font-semibold">
                Predykcje gotowe, ale nie znaleziono okazji z wartością.
              </p>
              <p className="mt-1">
                Kursy Superbetu pobierają się automatycznie. Jeśli chcesz
                sprawdzić też Betclic/STS, wpisz ich kursy w{" "}
                <code>pipeline\odds\ms2026_kursy.csv</code> (szablon:{" "}
                <code>ms2026_szablon.csv</code>) i uruchom ponownie{" "}
                <code>python -m footstats.jobs.build_wc</code>. Pełna ocena
                wszystkich sprawdzonych kursów: <code>ms2026_ocena.csv</code>.
              </p>
            </div>
          )}
          {meta.tryb === "ms2026" && bets.length > 0 && (
            <p className="mt-6 inline-flex items-center gap-2 rounded-lg border border-brand/30 bg-brand-wash px-3 py-2 text-xs text-brand-deep">
              <span aria-hidden>●</span>
              Tryb MŚ 2026: prawdziwe nadchodzące mecze i Twoje realne kursy.
              Uwaga: na turnieju próby są małe (4–6 meczów), więc pewność
              predykcji jest z natury niższa niż w lidze.
            </p>
          )}
        </div>
      </section>

      <ValueBoard
        bets={bets}
        zawodnicy={zawodnicy}
        initialMatchId={mecz ? Number(mecz) : undefined}
      />
    </>
  );
}
