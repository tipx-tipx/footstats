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
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xs font-medium uppercase tracking-widest text-brand">
              Skan rynków · {meta.liga} {meta.sezon}
            </p>
            <span
              className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-paper px-2.5 py-1 text-[11px] text-muted"
              title="Cykl w chmurze pobiera statystyki i kursy, przelicza model i odświeża tę stronę"
            >
              <span aria-hidden className="live-dot h-1.5 w-1.5 rounded-full bg-data-green" />
              aktualizacja co ~30 min · ostatnia{" "}
              <span className="font-data font-medium text-ink-soft">{aktualizacja}</span>
            </span>
          </div>

          <h1 className="mt-3 max-w-2xl text-3xl font-bold leading-tight sm:text-4xl">
            Gdzie kurs płaci{" "}
            <span className="text-brand">więcej, niż powinien</span>
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">
            Model liczy prawdziwe szanse na strzały, faule czy odbiory — z
            historii zawodnika, przewidywanych minut, rywala i sędziego. Potem
            porównuje je z kursami bukmachera i zostawia tylko zakłady, w
            których bukmacher się przelicza.{" "}
            <Link
              href="/jak-to-dziala"
              className="font-medium text-brand underline-offset-2 hover:underline"
            >
              Jak to działa? →
            </Link>
          </p>

          <dl className="mt-6 grid max-w-3xl grid-cols-2 gap-2.5 sm:grid-cols-4">
            {[
              { label: "okazje z kursem", value: String(okazje.length) },
              { label: "z wysoką pewnością", value: String(wysokaPewnosc) },
              ...(naj?.ev_pct != null
                ? [{ label: "najlepsza wartość", value: fmtEV(naj.ev_pct), green: true }]
                : []),
              { label: "meczów w analizie", value: String(meta.meczow_demo) },
            ].map((s) => (
              <div
                key={s.label}
                className="rounded-xl border border-hairline bg-card px-4 py-3 shadow-(--shadow-card)"
              >
                <dd
                  className={`font-data text-2xl font-semibold ${
                    "green" in s && s.green ? "text-data-green" : "text-ink"
                  }`}
                >
                  {s.value}
                </dd>
                <dt className="mt-0.5 text-[11px] leading-tight text-faint">
                  {s.label}
                </dt>
              </div>
            ))}
          </dl>

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
