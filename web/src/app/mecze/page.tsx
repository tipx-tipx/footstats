import Link from "next/link";

import { getMecze, getValueBets } from "@/lib/data";
import { fmtDataCzas, fmtMnoznik } from "@/lib/format";

export const metadata = { title: "Mecze — FootStats" };

export default async function MeczePage() {
  const [mecze, bets] = await Promise.all([getMecze(), getValueBets()]);
  const okazjeByMecz = new Map<number, number>();
  let bestByMecz = new Map<number, number>();
  for (const b of bets) {
    okazjeByMecz.set(b.mecz_id, (okazjeByMecz.get(b.mecz_id) ?? 0) + 1);
    if ((bestByMecz.get(b.mecz_id) ?? 0) < b.ev_pct)
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
              <div className="mt-3 flex items-center justify-between border-t border-hairline pt-3 text-sm">
                <span className="text-muted">
                  {n === 0
                    ? "brak okazji"
                    : n === 1
                      ? "1 okazja"
                      : `${n} okazji`}
                </span>
                {best !== undefined && (
                  <span className="font-data font-semibold text-data-green">
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
