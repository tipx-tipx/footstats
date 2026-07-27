"use client";

import { useMemo, useState } from "react";

import { WierszTypu } from "./WierszTypu";
import { fmtDzien, fmtU } from "@/lib/format";
import type { SkutecznoscDnia } from "@/lib/types";

/**
 * PEŁNA LISTA TYPÓW wybranego produktu — „co konkretnie weszło, a co nie".
 *
 * Dotąd te dane były na stronie, ale schowane: trzeba było wybrać produkt,
 * wejść w zakładkę Kalendarz i kliknąć konkretny dzień. Kto nie wiedział, że
 * kafelki kalendarza są klikalne, nigdy nie zobaczył ani jednego typu
 * z Drabinek czy z Drużyn (zgłoszenie 2026-07-27). Teraz to osobna zakładka:
 * wszystko na jednej liście, pogrupowane po dniu, z filtrem wyniku.
 */

type Filtr = "wszystko" | "weszly" | "nie";

const FILTRY: { kod: Filtr; label: string }[] = [
  { kod: "wszystko", label: "Wszystkie" },
  { kod: "weszly", label: "Tylko te, które weszły" },
  { kod: "nie", label: "Tylko te, które nie weszły" },
];

/** Ile dni pokazujemy od razu — reszta po kliknięciu (lista bywa długa). */
const DNI_NA_START = 7;

export function ListaTypow({ dni }: { dni: SkutecznoscDnia[] }) {
  const [filtr, setFiltr] = useState<Filtr>("wszystko");
  const [wszystkieDni, setWszystkieDni] = useState(false);

  const widoczne = useMemo(() => {
    return dni
      .map((d) => ({
        ...d,
        widoczneTypy: (d.typy ?? []).filter((t) =>
          filtr === "weszly"
            ? t.wynik === "wygrany"
            : filtr === "nie"
              ? t.wynik === "przegrany"
              : true,
        ),
      }))
      .filter((d) => d.widoczneTypy.length > 0);
  }, [dni, filtr]);

  const pokazane = wszystkieDni ? widoczne : widoczne.slice(0, DNI_NA_START);
  const razem = widoczne.reduce((a, d) => a + d.widoczneTypy.length, 0);

  if (dni.length === 0) {
    return (
      <p className="rounded-(--radius-card) border border-hairline bg-card px-4 py-3.5 text-sm text-muted shadow-(--shadow-card)">
        Nic tu jeszcze nie ma — żaden typ tego rodzaju się nie rozliczył.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {FILTRY.map((f) => (
          <button
            key={f.kod}
            onClick={() => setFiltr(f.kod)}
            aria-pressed={f.kod === filtr}
            className={`rounded-(--radius-control) border px-3 py-1.5 text-xs transition-colors ${
              f.kod === filtr
                ? "border-brand bg-brand-wash font-semibold text-brand-deep"
                : "border-hairline bg-card text-muted hover:text-ink"
            }`}
          >
            {f.label}
          </button>
        ))}
        <span className="font-data ml-auto text-xs text-faint">
          {razem} {razem === 1 ? "typ" : razem < 5 ? "typy" : "typów"}
        </span>
      </div>

      {pokazane.map((d) => (
        <div key={d.dzien}>
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h4 className="font-display text-sm font-bold capitalize tracking-tight">
              {fmtDzien(d.dzien, true)}
            </h4>
            <p className="text-xs text-muted">
              <span className="font-data font-semibold text-ink">
                {d.trafione}/{d.rozliczone}
              </span>{" "}
              weszło · bilans{" "}
              <span
                className={`font-data font-semibold ${
                  d.roi_flat > 0
                    ? "text-data-green"
                    : d.roi_flat < 0
                      ? "text-data-red"
                      : "text-ink-soft"
                }`}
              >
                {fmtU(d.roi_flat)}
              </span>
            </p>
          </div>
          <ul className="space-y-1.5">
            {d.widoczneTypy.map((t, i) => (
              <WierszTypu
                key={`${t.podmiot}-${t.rynek_kod}-${t.linia}-${i}`}
                t={t}
              />
            ))}
          </ul>
        </div>
      ))}

      {!wszystkieDni && widoczne.length > DNI_NA_START && (
        <button
          onClick={() => setWszystkieDni(true)}
          className="w-full rounded-(--radius-control) border border-hairline bg-card px-4 py-2.5 text-sm text-muted transition-colors hover:text-ink"
        >
          Pokaż starsze dni ({widoczne.length - DNI_NA_START})
        </button>
      )}
    </div>
  );
}
