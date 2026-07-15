"use client";

import Link from "next/link";
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

/** Wygląd chipa statusu (select stylizowany na pastylkę z etykietą). */
const WYNIK_STYL: Record<MojZaklad["wynik"], string> = {
  oczekuje: "border-hairline bg-card-soft text-muted",
  wygrany: "border-transparent bg-data-green-wash text-data-green-ink",
  przegrany: "border-transparent bg-data-red-wash text-data-red-ink",
  zwrot: "border-transparent bg-data-amber-wash text-data-amber-ink",
};

/** Pasek akcentu statusu przy lewej krawędzi wiersza (tylko rozliczone). */
const WYNIK_PASEK: Partial<Record<MojZaklad["wynik"], string>> = {
  wygrany: "bg-data-green",
  przegrany: "bg-data-red",
  zwrot: "bg-data-amber",
};

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
      <div className="mt-8 rounded-(--radius-card) border border-dashed border-hairline-strong bg-card px-8 py-14 text-center shadow-(--shadow-card)">
        <span
          aria-hidden
          className="font-data mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-brand-wash text-xl text-brand"
        >
          +
        </span>
        <p className="mt-4 font-semibold">Nie masz jeszcze żadnych zakładów</p>
        <p className="mx-auto mt-1 max-w-sm text-sm leading-relaxed text-muted">
          Rozwiń interesującą okazję i kliknij „Dodaj do moich zakładów” —
          wróci tutaj jako wpis do rozliczenia.
        </p>
        <Link
          href="/"
          className="mt-5 inline-block rounded-(--radius-control) bg-brand px-5 py-2.5 text-sm font-semibold text-on-brand shadow-(--shadow-card) transition-colors hover:bg-brand-strong"
        >
          Przeglądaj okazje
        </Link>
      </div>
    );
  }

  return (
    <>
      {/* podsumowanie — pasek statystyk z separatorami (wzór: hero) */}
      <div className="mt-7 max-w-3xl rounded-(--radius-card) border border-hairline bg-card px-5 py-4 shadow-(--shadow-card) sm:px-6 sm:py-5">
        <dl className="grid grid-cols-2 gap-y-5 sm:flex sm:items-stretch sm:gap-0">
          {[
            { label: "zakładów", value: String(podsumowanie.n), tone: "" },
            {
              label: "trafionych",
              value: `${podsumowanie.wygrane}/${podsumowanie.rozliczone}`,
              tone: "",
            },
            {
              label: "zysk (dla podanych stawek)",
              value: `${podsumowanie.zysk >= 0 ? "+" : ""}${podsumowanie.zysk
                .toFixed(2)
                .replace(".", ",")} zł`,
              tone:
                podsumowanie.zysk > 0
                  ? "text-data-green"
                  : podsumowanie.zysk < 0
                    ? "text-data-red"
                    : "",
            },
            {
              label: "średni CLV",
              value:
                podsumowanie.sredniCLV === null
                  ? "—"
                  : `${podsumowanie.sredniCLV > 0 ? "+" : ""}${podsumowanie.sredniCLV
                      .toFixed(1)
                      .replace(".", ",")}%`,
              tone:
                (podsumowanie.sredniCLV ?? 0) > 0
                  ? "text-data-green"
                  : (podsumowanie.sredniCLV ?? 0) < 0
                    ? "text-data-red"
                    : "",
              hint: "Czy Twój kurs był lepszy niż kurs tuż przed meczem. Dodatni = wyprzedzasz rynek.",
            },
          ].map((s, i) => (
            <div
              key={s.label}
              className={`min-w-0 ${
                i > 0
                  ? "sm:ml-6 sm:border-l sm:border-hairline-strong/60 sm:pl-6"
                  : ""
              }`}
              title={"hint" in s ? s.hint : undefined}
            >
              <dd
                className={`font-data text-[1.45rem] font-semibold leading-none ${s.tone}`}
              >
                {s.value}
              </dd>
              <dt className="mt-1.5 text-[11px] leading-tight text-faint">
                {s.label}
                {"hint" in s && " ⓘ"}
              </dt>
            </div>
          ))}
        </dl>
      </div>

      {/* lista — dziennik wpisów */}
      <div className="mt-6 space-y-2.5">
        {zaklady.map((z) => {
          const clv = clvPct(z);
          return (
            <div
              key={z.id}
              className="relative overflow-hidden rounded-(--radius-card) border border-hairline bg-card px-4 py-3 shadow-(--shadow-card) transition-shadow hover:shadow-(--shadow-card-hover)"
            >
              {/* akcent statusu przy krawędzi — czytelny przy przewijaniu */}
              {WYNIK_PASEK[z.wynik] && (
                <span
                  aria-hidden
                  className={`absolute inset-y-0 left-0 w-1 ${WYNIK_PASEK[z.wynik]}`}
                />
              )}
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">
                    {z.podmiot}
                    <span className="ml-2 font-normal text-muted">
                      {z.rynek.toLowerCase()} {STRONA_LABEL[z.strona]}{" "}
                      {fmtLinia(z.linia)}
                    </span>
                  </p>
                  <p className="mt-0.5 truncate text-xs text-faint">
                    {z.mecz} · {z.bukmacher} · kurs{" "}
                    <span className="font-data text-ink-soft">
                      {fmtKurs(z.kurs)}
                    </span>
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
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      updateZaklad(z.id, {
                        stawka:
                          e.target.value && Number.isFinite(v)
                            ? Math.max(0, v)
                            : null,
                      });
                    }}
                    className="font-data w-20 rounded-(--radius-control) border border-hairline bg-card-soft px-2 py-1 text-sm text-ink"
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
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      updateZaklad(z.id, {
                        kurs_zamkniecia:
                          e.target.value && Number.isFinite(v) ? v : null,
                      });
                    }}
                    className="font-data w-20 rounded-(--radius-control) border border-hairline bg-card-soft px-2 py-1 text-sm text-ink"
                  />
                </label>

                {clv !== null && (
                  <span
                    className={`font-data inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                      clv > 0
                        ? "bg-data-green-wash text-data-green-ink"
                        : "bg-data-red-wash text-data-red-ink"
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
                  className={`cursor-pointer rounded-full border px-2.5 py-1 text-xs font-semibold ${WYNIK_STYL[z.wynik]}`}
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
                  className="rounded-(--radius-control) p-2.5 text-faint transition-colors hover:bg-data-red-wash hover:text-data-red-ink"
                  aria-label={`Usuń zakład: ${z.podmiot} ${z.rynek}`}
                  title="Usuń"
                >
                  <svg width="16" height="16" viewBox="0 0 14 14" aria-hidden>
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
