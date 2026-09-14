"use client";

import { useMemo, useState } from "react";

import { Segmented } from "./Segmented";
import type { Rywal, ValueBet } from "@/lib/types";

/**
 * EKRAN „RYWALE" (2026-09-14) – szukanie od rywala do zawodnika, tak jak
 * robią to eksperci: „ta drużyna dopuszcza najwięcej fauli w lidze, więc
 * skrzydłowy przeciwnika…". Liczby to koncesje z 10 ostatnich meczów rywala
 * względem normy ligi, liczone na gwizdek – te same, które model ma w cesze
 * `rywal`. Ekran nie zmienia rachunku ani listy: jest narzędziem przeglądu.
 */

const RYNKI: { kod: string; label: string }[] = [
  { kod: "fouls_committed", label: "Faule" },
  { kod: "fouls_won", label: "Faule wywalczone" },
  { kod: "shots", label: "Strzały" },
  { kod: "sot", label: "Celne" },
  { kod: "tackles", label: "Odbiory" },
  { kod: "shots_outside_box", label: "Zza pola" },
  { kod: "headed_shots", label: "Głową" },
  { kod: "offsides", label: "Spalone" },
];

const GRUPY: { kod: "FWD" | "MID" | "DEF"; label: string }[] = [
  { kod: "FWD", label: "napastnicy" },
  { kod: "MID", label: "pomocnicy" },
  { kod: "DEF", label: "obrońcy" },
];

function pct(stosunek: number): string {
  const v = Math.round((stosunek - 1) * 100);
  return `${v > 0 ? "+" : ""}${v}%`;
}

function kolorProcentu(stosunek: number): string {
  if (stosunek >= 1.15) return "text-emerald-700 dark:text-emerald-400";
  if (stosunek <= 0.85) return "text-rose-700 dark:text-rose-400";
  return "text-ink-soft";
}

function kiedy(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleString("pl-PL", {
    weekday: "short", day: "numeric", month: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

export function RywaleTablica({ rywale, typy }: { rywale: Rywal[]; typy: ValueBet[] }) {
  const dostepne = useMemo(() => {
    const kody = new Set(rywale.map((r) => r.rynek_kod));
    return RYNKI.filter((r) => kody.has(r.kod));
  }, [rywale]);
  const [rynek, setRynek] = useState<string>(dostepne[0]?.kod ?? "fouls_committed");
  const [tylkoNadNorma, setTylkoNadNorma] = useState(true);

  const wiersze = useMemo(() => {
    const w = rywale.filter((r) => r.rynek_kod === rynek);
    return (tylkoNadNorma ? w.filter((r) => r.max_stosunek >= 1.1) : w).sort(
      (a, b) => b.max_stosunek - a.max_stosunek,
    );
  }, [rywale, rynek, tylkoNadNorma]);

  // nasze typy zawodnicze przeciwko temu rywalowi na tym rynku – żeby jednym
  // spojrzeniem widzieć, czy model już z tego skorzystał
  const typyPrzeciw = useMemo(() => {
    const m = new Map<string, number>();
    for (const b of typy) {
      if (b.podmiot_typ !== "zawodnik" || b.sugestia) continue;
      const k = `${b.mecz_id}:${b.przeciwnik}:${b.rynek_kod}`;
      m.set(k, (m.get(k) ?? 0) + 1);
    }
    return m;
  }, [typy]);

  if (!rywale.length) {
    return (
      <p className="text-sm text-ink-soft">
        Brak profili rywali na najbliższe trzy dni – pojawią się po najbliższym
        przeliczeniu.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented
          id="rywale-rynek"
          opcje={dostepne.map((r) => ({ kod: r.kod, label: r.label }))}
          wartosc={rynek}
          onChange={setRynek}
        />
        <label className="flex items-center gap-2 text-sm text-ink-soft">
          <input
            type="checkbox"
            checked={tylkoNadNorma}
            onChange={(e) => setTylkoNadNorma(e.target.checked)}
          />
          tylko wyraźnie ponad normę (+10% i więcej)
        </label>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[40rem] text-sm">
          <thead className="text-left text-ink-soft">
            <tr>
              <th className="pb-2 font-semibold">Rywal dopuszcza</th>
              <th className="pb-2 font-semibold">Komu (mecz)</th>
              {GRUPY.map((g) => (
                <th key={g.kod} className="pb-2 text-right font-semibold">
                  {g.label}
                </th>
              ))}
              <th className="pb-2 text-right font-semibold">Nasze typy</th>
            </tr>
          </thead>
          <tbody>
            {wiersze.map((r) => {
              const n = typyPrzeciw.get(`${r.mecz_id}:${r.rywal}:${r.rynek_kod}`) ?? 0;
              return (
                <tr key={`${r.mecz_id}:${r.rywal_id}:${r.rynek_kod}`} className="border-t border-hairline">
                  <td className="py-2 pr-3 font-semibold text-ink">{r.rywal}</td>
                  <td className="py-2 pr-3 text-ink-soft">
                    {r.przeciw}
                    <span className="block text-xs">{kiedy(r.kickoff_ts)}</span>
                  </td>
                  {GRUPY.map((g) => {
                    const p = r.grupy[g.kod];
                    return (
                      <td key={g.kod} className="py-2 pl-3 text-right font-data">
                        {p ? (
                          <span title={`${p.per90.toFixed(2)} na 90 min przy normie ${p.norma.toFixed(2)} (${p.n} meczów)`}>
                            <span className={kolorProcentu(p.stosunek)}>{pct(p.stosunek)}</span>
                            <span className="block text-xs text-ink-soft">{p.per90.toFixed(2)} / 90&apos;</span>
                          </span>
                        ) : (
                          <span className="text-ink-soft">–</span>
                        )}
                      </td>
                    );
                  })}
                  <td className="py-2 pl-3 text-right font-data">
                    {n > 0 ? (
                      <a href={`/mecze/${r.mecz_id}`} className="underline">{n}</a>
                    ) : (
                      <span className="text-ink-soft">0</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {wiersze.length === 0 && (
        <p className="text-sm text-ink-soft">
          Na tym rynku żaden rywal w najbliższych meczach nie odstaje od normy o
          10% lub więcej – odznacz filtr, żeby zobaczyć wszystkich.
        </p>
      )}
    </div>
  );
}
