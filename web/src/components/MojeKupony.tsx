"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { fmtKurs, fmtLinia, fmtMnoznik } from "@/lib/format";
import {
  listKuponyZagrane,
  onKuponyZagraneChange,
  removeKuponZagrany,
  updateKuponZagrany,
  wynikZHistorii,
  zyskKuponu,
  type MojKupon,
} from "@/lib/kuponyTracker";
import type { KuponHistoria } from "@/lib/types";

const ZAKRES_LABEL: Record<string, string> = {
  dzienny: "na dziś",
  dlugoterminowy: "na kilka dni",
  value: "value",
};

const WYNIK_CHIP: Record<string, string> = {
  wygrany: "bg-data-green-wash text-data-green-ink",
  przegrany: "bg-data-red-wash text-data-red-ink",
  zwrot: "bg-data-amber-wash text-data-amber-ink",
  anulowany: "bg-card-soft text-muted",
};

const WYNIK_LABEL: Record<string, string> = {
  wygrany: "wygrany",
  przegrany: "przegrany",
  zwrot: "zwrot",
  anulowany: "anulowany",
};

/**
 * Zagrane kupony w Moich zakładach. W przeciwieństwie do pojedynczych
 * typów NIE wymagają ręcznego rozliczania: kupony modelu mają klucz,
 * a pipeline rozlicza każdy z nich — wynik dojeżdża sam z historii.
 */
export function MojeKupony({ historia }: { historia: KuponHistoria[] }) {
  const [kupony, setKupony] = useState<MojKupon[]>([]);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setKupony(listKuponyZagrane());
    setMounted(true);
    return onKuponyZagraneChange(() => setKupony(listKuponyZagrane()));
  }, []);

  const wiersze = useMemo(
    () =>
      kupony.map((w) => {
        const { wynik, kurs_rozliczony } = wynikZHistorii(w, historia);
        return { w, wynik, kurs_rozliczony, zysk: zyskKuponu(w, wynik, kurs_rozliczony) };
      }),
    [kupony, historia],
  );

  const bilans = useMemo(() => {
    const rozliczone = wiersze.filter((r) => r.zysk !== null);
    return {
      n: wiersze.length,
      rozliczone: rozliczone.length,
      wygrane: rozliczone.filter((r) => r.wynik === "wygrany").length,
      zysk: rozliczone.reduce((a, r) => a + (r.zysk ?? 0), 0),
    };
  }, [wiersze]);

  if (!mounted || kupony.length === 0) return null;

  return (
    <section aria-label="Moje kupony" className="mt-8">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-display flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-brand">
          <span aria-hidden className="h-px w-5 bg-brand-bright" />
          zagrane kupony
        </p>
        <p className="text-[11px] text-faint">
          rozliczają się same po meczach ·{" "}
          <span className="font-data text-muted">
            {bilans.wygrane}/{bilans.rozliczone}
          </span>{" "}
          trafionych
          {bilans.rozliczone > 0 && (
            <>
              {" "}
              ·{" "}
              <span
                className={`font-data font-semibold ${
                  bilans.zysk > 0
                    ? "text-data-green"
                    : bilans.zysk < 0
                      ? "text-data-red"
                      : "text-muted"
                }`}
              >
                {bilans.zysk >= 0 ? "+" : ""}
                {bilans.zysk.toFixed(2).replace(".", ",")} zł
              </span>
            </>
          )}
        </p>
      </div>

      <div className="mt-3 space-y-2.5">
        {wiersze.map(({ w, wynik, kurs_rozliczony, zysk }) => (
          <div
            key={w.id}
            className="relative overflow-hidden rounded-(--radius-card) border border-hairline bg-card px-4 py-3 shadow-(--shadow-card)"
          >
            {wynik && wynik !== "anulowany" && (
              <span
                aria-hidden
                className={`absolute inset-y-0 left-0 w-1 ${
                  wynik === "wygrany"
                    ? "bg-data-green"
                    : wynik === "przegrany"
                      ? "bg-data-red"
                      : "bg-data-amber"
                }`}
              />
            )}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  Kupon ×{w.cel_label ?? fmtKurs(w.kurs_laczny)}
                  <span className="ml-2 font-normal text-muted">
                    {ZAKRES_LABEL[w.horyzont ?? ""] ?? "własny"} · kurs{" "}
                    <span className="font-data text-ink-soft">
                      {fmtMnoznik(w.kurs_laczny)}
                    </span>
                    {kurs_rozliczony != null &&
                      kurs_rozliczony !== w.kurs_laczny && (
                        <>
                          {" "}
                          → po zwrotach{" "}
                          <span className="font-data text-ink-soft">
                            {fmtMnoznik(kurs_rozliczony)}
                          </span>
                        </>
                      )}
                  </span>
                </p>
                <p className="mt-0.5 truncate text-xs text-faint">
                  {w.legi
                    .map((l) => `${l.podmiot} ${l.rynek.toLowerCase()} ${fmtLinia(l.linia)}+`)
                    .join(" · ")}
                </p>
              </div>

              <label className="flex items-center gap-1.5 text-xs text-muted">
                stawka
                <input
                  type="number"
                  min={0}
                  step={5}
                  value={w.stawka}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    updateKuponZagrany(w.id, {
                      stawka: Number.isFinite(v) ? Math.max(0, v) : w.stawka,
                    });
                  }}
                  className="font-data w-20 rounded-(--radius-control) border border-hairline bg-card-soft px-2 py-1 text-sm text-ink"
                />
              </label>

              {zysk !== null && wynik && (
                <span
                  className={`font-data text-sm font-semibold ${
                    zysk > 0
                      ? "text-data-green"
                      : zysk < 0
                        ? "text-data-red"
                        : "text-muted"
                  }`}
                >
                  {zysk >= 0 ? "+" : ""}
                  {zysk.toFixed(2).replace(".", ",")} zł
                </span>
              )}

              <span
                className={`rounded-full border border-transparent px-2.5 py-1 text-xs font-semibold ${
                  wynik ? WYNIK_CHIP[wynik] : "border-hairline bg-card-soft text-muted"
                }`}
              >
                {wynik ? WYNIK_LABEL[wynik] : "w grze"}
              </span>

              <button
                onClick={() => removeKuponZagrany(w.id)}
                className="rounded-(--radius-control) p-2.5 text-faint transition-colors hover:bg-data-red-wash hover:text-data-red-ink"
                aria-label="Usuń kupon"
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
        ))}
      </div>

      <p className="mt-2 text-[11px] text-faint">
        Kupony bierzesz ze strony{" "}
        <Link href="/kupony" className="text-brand hover:underline">
          Kupony
        </Link>{" "}
        przyciskiem „gram ten kupon".
      </p>
    </section>
  );
}
