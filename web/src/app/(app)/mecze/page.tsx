import Link from "next/link";

import { PageHeader } from "@/components/PageHeader";
import { Reveal } from "@/components/Reveal";
import { getMecze, getValueBets } from "@/lib/data";
import { fmtMnoznik } from "@/lib/format";

export const metadata = { title: "Mecze — FootStats" };

/** "dziś 20:00" / "jutro 03:30" / "sob 21:00" — po ludzku, Europe/Warsaw. */
function kiedy(ts: number): { label: string; soon: boolean } {
  const d = new Date(ts * 1000);
  const czas = new Intl.DateTimeFormat("pl-PL", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  }).format(d);
  const dzien = (x: Date) =>
    new Intl.DateTimeFormat("pl-PL", { dateStyle: "short", timeZone: "Europe/Warsaw" }).format(x);
  const teraz = new Date();
  const jutro = new Date(teraz.getTime() + 86400_000);
  const hoursTo = (ts * 1000 - Date.now()) / 3_600_000;
  if (dzien(d) === dzien(teraz)) return { label: `dziś ${czas}`, soon: hoursTo < 3 };
  if (dzien(d) === dzien(jutro)) return { label: `jutro ${czas}`, soon: false };
  const dow = new Intl.DateTimeFormat("pl-PL", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "Europe/Warsaw",
  }).format(d);
  return { label: `${dow}, ${czas}`, soon: false };
}

export default async function MeczePage() {
  const [mecze, bets] = await Promise.all([getMecze(), getValueBets()]);
  const okazjeByMecz = new Map<number, number>();
  const sugestieByMecz = new Map<number, number>();
  const bestByMecz = new Map<number, number>();
  for (const b of bets) {
    if (b.sugestia) {
      sugestieByMecz.set(b.mecz_id, (sugestieByMecz.get(b.mecz_id) ?? 0) + 1);
      continue;
    }
    okazjeByMecz.set(b.mecz_id, (okazjeByMecz.get(b.mecz_id) ?? 0) + 1);
    if (b.ev_pct != null && (bestByMecz.get(b.mecz_id) ?? 0) < b.ev_pct)
      bestByMecz.set(b.mecz_id, b.ev_pct);
  }
  const posortowane = [...mecze].sort((a, b) => a.kickoff_ts - b.kickoff_ts);

  return (
    <div>
      <PageHeader
        eyebrow="terminarz skanu"
        title="Mecze w analizie"
        lead="Każdy mecz przeskanowany przez model — kliknij, żeby wejść na stronę meczu z TOP POKRYCIA (zawodnicy z najlepszym pokryciem linii) i okazjami."
      />

      <div className="mt-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {posortowane.map((m, i) => {
          const n = okazjeByMecz.get(m.id) ?? 0;
          const nSug = sugestieByMecz.get(m.id) ?? 0;
          const best = bestByMecz.get(m.id);
          const czas = kiedy(m.kickoff_ts);
          return (
            <Reveal key={m.id} delay={Math.min(i * 0.05, 0.3)}>
              <Link
                href={`/mecze/${m.id}`}
                className="group flex h-full flex-col rounded-(--radius-card) border border-hairline bg-card p-5 shadow-(--shadow-card) transition-all hover:-translate-y-0.5 hover:border-brand/30 hover:shadow-(--shadow-card-hover)"
              >
                {/* pasek górny: termin gry + status składów */}
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                      czas.soon
                        ? "bg-data-amber-wash text-data-amber-ink"
                        : "border border-hairline bg-card-soft text-ink-soft"
                    }`}
                  >
                    {czas.soon && (
                      <span
                        aria-hidden
                        className="live-dot h-1.5 w-1.5 rounded-full bg-data-amber"
                      />
                    )}
                    {czas.label}
                  </span>
                  {m.sklady_ogloszone ? (
                    <span
                      className="inline-flex items-center gap-1 rounded-full bg-data-green-wash px-2.5 py-1 text-[11px] font-medium text-data-green-ink"
                      title="Oficjalne jedenastki znane — model przeliczony na pewnych składach"
                    >
                      ✓ składy
                    </span>
                  ) : (
                    <span
                      className="inline-flex items-center rounded-full bg-card-soft px-2.5 py-1 text-[11px] text-faint"
                      title="Oficjalne składy ok. 1 h przed meczem — wtedy model przelicza wszystko od nowa"
                    >
                      składy ~1 h przed
                    </span>
                  )}
                </div>

                {/* drużyny */}
                <div className="mt-5 flex-1">
                  <p className="font-display text-lg font-bold leading-snug tracking-tight">
                    {m.gospodarz}
                  </p>
                  <p className="my-1 flex items-center gap-2 text-[10px] font-medium uppercase tracking-widest text-faint">
                    <span aria-hidden className="h-px w-4 bg-hairline-strong" />
                    kontra
                  </p>
                  <p className="font-display text-lg font-bold leading-snug tracking-tight">
                    {m.gosc}
                  </p>
                </div>

                {m.sedzia && (
                  <p className="mt-4 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                    <span className="inline-flex items-center rounded-full border border-hairline bg-card-soft px-2.5 py-1">
                      Sędzia: {m.sedzia}
                    </span>
                    {Math.abs(m.sedzia_mnoznik_fauli - 1) > 0.05 && (
                      <span
                        className={`font-data inline-flex items-center rounded-full px-2 py-1 font-semibold ${
                          m.sedzia_mnoznik_fauli > 1
                            ? "bg-data-red-wash text-data-red-ink"
                            : "bg-data-green-wash text-data-green-ink"
                        }`}
                        title="Ile fauli gwiżdże ten sędzia względem średniej ligi"
                      >
                        faule {fmtMnoznik(m.sedzia_mnoznik_fauli)}
                      </span>
                    )}
                  </p>
                )}

                <div className="mt-4 flex items-center justify-between gap-2 border-t border-hairline pt-3.5 text-sm">
                  <span className="flex items-center gap-2">
                    <span
                      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        n > 0
                          ? "bg-brand-wash text-brand-deep"
                          : "bg-card-soft text-faint"
                      }`}
                    >
                      {n === 0 ? "0 okazji" : n === 1 ? "1 okazja" : `${n} okazji`}
                    </span>
                    {nSug > 0 && (
                      <span className="inline-flex items-center rounded-full bg-data-amber-wash px-2.5 py-0.5 text-xs font-medium text-data-amber-ink">
                        {nSug} sug. STS
                      </span>
                    )}
                  </span>
                  {best !== undefined ? (
                    <span
                      className="font-data font-semibold text-data-green-ink"
                      title="Najlepsza wartość wśród okazji z tego meczu"
                    >
                      do +{best.toFixed(0)}%
                    </span>
                  ) : (
                    <span
                      aria-hidden
                      className="text-faint transition-transform group-hover:translate-x-0.5"
                    >
                      →
                    </span>
                  )}
                </div>
              </Link>
            </Reveal>
          );
        })}
      </div>
    </div>
  );
}
