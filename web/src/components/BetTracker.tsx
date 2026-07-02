"use client";

import { useEffect, useMemo, useState } from "react";

import {
  clvPct,
  listZaklady,
  onZakladyChange,
  removeZaklad,
  updateZaklad,
} from "@/lib/tracker";
import { fmtKurs, fmtLinia, STRONA_LABEL } from "@/lib/format";
import type { MojZaklad } from "@/lib/types";

const WYNIKI: { kod: MojZaklad["wynik"]; label: string }[] = [
  { kod: "oczekuje", label: "oczekuje" },
  { kod: "wygrany", label: "wygrany" },
  { kod: "przegrany", label: "przegrany" },
  { kod: "zwrot", label: "zwrot" },
];

export function BetTracker() {
  const [zaklady, setZaklady] = useState<MojZaklad[]>([]);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setZaklady(listZaklady());
    setMounted(true);
    return onZakladyChange(() => setZaklady(listZaklady()));
  }, []);

  const podsumowanie = useMemo(() => {
    const rozliczone = zaklady.filter(
      (z) => z.wynik === "wygrany" || z.wynik === "przegrany",
    );
    const zeStawka = rozliczone.filter((z) => z.stawka);
    const obrot = zeStawka.reduce((a, z) => a + (z.stawka ?? 0), 0);
    const zysk = zeStawka.reduce(
      (a, z) =>
        a +
        (z.wynik === "wygrany"
          ? (z.stawka ?? 0) * (z.kurs - 1)
          : -(z.stawka ?? 0)),
      0,
    );
    const clvs = zaklady.map(clvPct).filter((v): v is number => v !== null);
    return {
      n: zaklady.length,
      rozliczone: rozliczone.length,
      wygrane: rozliczone.filter((z) => z.wynik === "wygrany").length,
      obrot,
      zysk,
      sredniCLV: clvs.length
        ? clvs.reduce((a, b) => a + b, 0) / clvs.length
        : null,
    };
  }, [zaklady]);

  if (!mounted) return <div className="mt-8 h-40" aria-hidden />;

  if (zaklady.length === 0) {
    return (
      <div className="mt-8 rounded-(--radius-card) border border-dashed border-hairline-strong bg-card p-10 text-center">
        <p className="font-semibold">Nie masz jeszcze żadnych zakładów</p>
        <p className="mt-1 text-sm text-muted">
          Wejdź w <a href="/" className="text-brand underline">Okazje</a>,
          rozwiń interesujący zakład i kliknij „Dodaj do moich zakładów".
        </p>
      </div>
    );
  }

  return (
    <>
      {/* podsumowanie */}
      <dl className="mt-6 flex flex-wrap gap-x-10 gap-y-3 rounded-(--radius-card) border border-hairline bg-card px-5 py-4 shadow-(--shadow-card)">
        <div>
          <dt className="text-xs text-faint">zakładów</dt>
          <dd className="font-data text-xl font-semibold">{podsumowanie.n}</dd>
        </div>
        <div>
          <dt className="text-xs text-faint">trafionych</dt>
          <dd className="font-data text-xl font-semibold">
            {podsumowanie.wygrane}/{podsumowanie.rozliczone}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-faint">zysk (dla podanych stawek)</dt>
          <dd
            className={`font-data text-xl font-semibold ${
              podsumowanie.zysk > 0
                ? "text-data-green"
                : podsumowanie.zysk < 0
                  ? "text-data-red"
                  : ""
            }`}
          >
            {podsumowanie.zysk >= 0 ? "+" : ""}
            {podsumowanie.zysk.toFixed(2).replace(".", ",")} zł
          </dd>
        </div>
        <div>
          <dt className="text-xs text-faint">
            średni CLV{" "}
            <span title="Czy Twój kurs był lepszy niż kurs tuż przed meczem. Dodatni = wyprzedzasz rynek.">
              ⓘ
            </span>
          </dt>
          <dd
            className={`font-data text-xl font-semibold ${
              (podsumowanie.sredniCLV ?? 0) > 0
                ? "text-data-green"
                : (podsumowanie.sredniCLV ?? 0) < 0
                  ? "text-data-red"
                  : ""
            }`}
          >
            {podsumowanie.sredniCLV === null
              ? "—"
              : `${podsumowanie.sredniCLV > 0 ? "+" : ""}${podsumowanie.sredniCLV
                  .toFixed(1)
                  .replace(".", ",")}%`}
          </dd>
        </div>
      </dl>

      {/* lista */}
      <div className="mt-6 space-y-2.5">
        {zaklady.map((z) => {
          const clv = clvPct(z);
          return (
            <div
              key={z.id}
              className="rounded-(--radius-card) border border-hairline bg-card px-4 py-3 shadow-(--shadow-card)"
            >
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">
                    {z.podmiot}
                    <span className="ml-2 font-normal text-muted">
                      {z.rynek.toLowerCase()} {STRONA_LABEL[z.strona]}{" "}
                      {fmtLinia(z.linia)}
                    </span>
                  </p>
                  <p className="truncate text-xs text-faint">
                    {z.mecz} · {z.bukmacher} · kurs{" "}
                    <span className="font-data">{fmtKurs(z.kurs)}</span>
                  </p>
                </div>

                <label className="flex items-center gap-1.5 text-xs text-muted">
                  stawka
                  <input
                    type="number"
                    min={0}
                    step={10}
                    value={z.stawka ?? ""}
                    placeholder="zł"
                    onChange={(e) =>
                      updateZaklad(z.id, {
                        stawka: e.target.value ? Number(e.target.value) : null,
                      })
                    }
                    className="font-data w-20 rounded-md border border-hairline bg-paper px-2 py-1 text-sm"
                  />
                </label>

                <label className="flex items-center gap-1.5 text-xs text-muted">
                  kurs zamkn.
                  <input
                    type="number"
                    min={1}
                    step={0.01}
                    value={z.kurs_zamkniecia ?? ""}
                    placeholder="—"
                    onChange={(e) =>
                      updateZaklad(z.id, {
                        kurs_zamkniecia: e.target.value
                          ? Number(e.target.value)
                          : null,
                      })
                    }
                    className="font-data w-20 rounded-md border border-hairline bg-paper px-2 py-1 text-sm"
                  />
                </label>

                {clv !== null && (
                  <span
                    className={`font-data text-sm font-semibold ${
                      clv > 0 ? "text-data-green" : "text-data-red"
                    }`}
                    title="Closing Line Value"
                  >
                    CLV {clv > 0 ? "+" : ""}
                    {clv.toFixed(1).replace(".", ",")}%
                  </span>
                )}

                <select
                  value={z.wynik}
                  onChange={(e) =>
                    updateZaklad(z.id, {
                      wynik: e.target.value as MojZaklad["wynik"],
                    })
                  }
                  className={`rounded-md border border-hairline px-2 py-1 text-sm ${
                    z.wynik === "wygrany"
                      ? "bg-data-green-wash text-brand-deep"
                      : z.wynik === "przegrany"
                        ? "bg-data-red-wash text-data-red"
                        : "bg-paper"
                  }`}
                  aria-label="Wynik zakładu"
                >
                  {WYNIKI.map((w) => (
                    <option key={w.kod} value={w.kod}>
                      {w.label}
                    </option>
                  ))}
                </select>

                <button
                  onClick={() => removeZaklad(z.id)}
                  className="rounded-md p-1.5 text-faint transition-colors hover:bg-data-red-wash hover:text-data-red"
                  aria-label={`Usuń zakład: ${z.podmiot} ${z.rynek}`}
                  title="Usuń"
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
                    <path
                      d="M3 3 L11 11 M11 3 L3 11"
                      stroke="currentColor"
                      strokeWidth="1.6"
                      strokeLinecap="round"
                    />
                  </svg>
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
