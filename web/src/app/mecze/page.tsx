import Link from "next/link";

import { getMecze, getValueBets } from "@/lib/data";
import { fmtDataCzas, fmtMnoznik } from "@/lib/format";

export const metadata = { title: "Mecze — FootStats" };

export default async function MeczePage() {
  const [mecze, bets] = await Promise.all([getMecze(), getValueBets()]);
  const okazjeByMecz = new Map<number, number>();
  const sugestieByMecz = new Map<number, number>();
  const bestByMecz = new Map<number, number>();
  for (const b of bets) {
    if (b.sugestia) {
      sugestieByMecz.set(b.mecz_id, (sugestieByMecz.get(b.mecz_id) ?? 0) + 1);
      continue; // sugestie STS nie liczą się jako okazje z kursem
    }
    okazjeByMecz.set(b.mecz_id, (okazjeByMecz.get(b.mecz_id) ?? 0) + 1);
    if (b.ev_pct != null && (bestByMecz.get(b.mecz_id) ?? 0) < b.ev_pct)
      bestByMecz.set(b.mecz_id, b.ev_pct);
  }

  return (
    <div className="pt-10">
      <h1 className="text-2xl font-bold">Mecze w analizie</h1>
      <p className="mt-2 max-w-2xl text-sm text-muted">
        Każdy mecz przeskanowany przez model. Kliknij, żeby zobaczyć wszystkie
        okazje z tego spotkania.
      </p>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {mecze.map((m) => {
          const n = okazjeByMecz.get(m.id) ?? 0;
          const nSug = sugestieByMecz.get(m.id) ?? 0;
          const best = bestByMecz.get(m.id);
          return (
            <Link
              key={m.id}
              href={`/?mecz=${m.id}`}
              className="group rounded-(--radius-card) border border-hairline bg-card p-4 shadow-(--shadow-card) transition-all hover:-translate-y-0.5 hover:shadow-(--shadow-card-hover)"
            >
              <p className="text-xs text-faint">
                {m.liga} · kolejka {m.kolejka ?? "—"} · {fmtDataCzas(m.kickoff_ts)}
              </p>
              <h2 className="mt-1.5 font-semibold leading-snug">
                {m.gospodarz}
                <span className="mx-1.5 text-faint">–</span>
                {m.gosc}
              </h2>
              <p className="mt-2">
                {m.sklady_ogloszone ? (
                  <span
                    className="inline-flex items-center gap-1 rounded-md bg-data-green-wash px-2 py-0.5 text-xs font-medium text-brand-deep"
                    title="Oficjalne jedenastki są znane — model przeliczył minuty na pewnych składach"
                  >
                    ✓ składy ogłoszone
                  </span>
                ) : (
                  <span
                    className="inline-flex items-center gap-1 rounded-md bg-paper px-2 py-0.5 text-xs text-faint"
                    title="Oficjalne składy pojawiają się ok. godziny przed meczem — wtedy model przelicza wszystko od nowa"
                  >
                    składy ok. 1 h przed meczem
                  </span>
                )}
              </p>
              {m.sedzia && (
                <p className="mt-2 text-xs text-muted">
                  Sędzia: {m.sedzia}{" "}
                  {Math.abs(m.sedzia_mnoznik_fauli - 1) > 0.05 && (
                    <span
                      className={`font-data ml-1 rounded px-1 py-0.5 ${
                        m.sedzia_mnoznik_fauli > 1
                          ? "bg-data-red-wash text-data-red"
                          : "bg-data-green-wash text-brand-deep"
                      }`}
                      title="Ile fauli gwiżdże ten sędzia względem średniej ligi"
                    >
                      faule {fmtMnoznik(m.sedzia_mnoznik_fauli)}
                    </span>
                  )}
                </p>
              )}
              <div className="mt-3 flex items-center justify-between gap-2 border-t border-hairline pt-3 text-sm">
                <span className="text-muted">
                  {n === 0
                    ? "brak okazji z kursem"
                    : n === 1
                      ? "1 okazja"
                      : `${n} okazji`}
                  {nSug > 0 && (
                    <span className="text-faint"> · {nSug} sug. STS</span>
                  )}
                </span>
                {best !== undefined && (
                  <span
                    className="font-data font-semibold text-data-green"
                    title="Najlepsza wartość wśród okazji z tego meczu"
                  >
                    do +{best.toFixed(0)}%
                  </span>
                )}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
