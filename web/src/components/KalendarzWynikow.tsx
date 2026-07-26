"use client";

import { useMemo, useState } from "react";

import { Segmented } from "./Segmented";
import { fmtU } from "@/lib/format";
import type { SkutecznoscDnia, Strumien, TypyWyniki } from "@/lib/types";
import { OSTATNIA_ZMIANA, poZmianie } from "@/lib/zmiany";

/**
 * Kalendarz wyników — widok miesiąca dzień po dniu (wzorzec zaufania:
 * codzienny bilans w jednostkach, nic nie znika).
 *
 * ROI dnia = roi_flat (stawka 1 j. na okazję), kolor: zysk/strata/zero.
 * Dni bez rozliczonych typów są puste (nie mylić z zerem).
 *
 * DWIE RZECZY, KTÓRYCH TU BRAKOWAŁO (2026-07-26):
 * 1. Jeden wspólny bilans nie mówił, GDZIE jest strata. Typy zawodnicze,
 *    rynki drużynowe i drabinki to trzy produkty o różnym ryzyku — pomiar
 *    z tego dnia: −42,9 j. na zawodnikach wobec −0,3 j. na drużynach.
 *    Przełącznik strumieni pokazuje to wprost zamiast uśredniać.
 * 2. Dni sprzed zmiany zasad selekcji opisują kod, którego już nie ma.
 *    Zostają w kalendarzu (nic nie chowamy), ale są wyszarzone i podpisane,
 *    żeby nie czytać ich jako bieżącej formy.
 */

const DNI_TYGODNIA = ["pn", "wt", "śr", "cz", "pt", "so", "nd"];
const MIESIACE = [
  "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
  "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
];

const NAZWY_STRUMIENI: Record<Strumien, string> = {
  pewniaki: "Zawodnicy",
  druzyny: "Drużyny",
  drabinki: "Drabinki",
};

type Wybor = "wszystko" | Strumien;

/** "YYYY-MM-DD" → [rok, miesiąc 0-11, dzień] bez pułapek stref czasowych. */
function rozbijDate(dzien: string): [number, number, number] {
  const [r, m, d] = dzien.split("-").map(Number);
  return [r, m - 1, d];
}

function bilansDni(dni: SkutecznoscDnia[]): { roi: number; n: number } {
  return dni.reduce(
    (a, d) => ({ roi: a.roi + d.roi_flat, n: a.n + d.rozliczone }),
    { roi: 0, n: 0 },
  );
}

export function KalendarzWynikow({
  dni,
  strumienie,
}: {
  dni: SkutecznoscDnia[];
  strumienie?: TypyWyniki["skutecznosc_strumienie"];
}) {
  const dostepne = useMemo(
    () =>
      (["pewniaki", "druzyny", "drabinki"] as Strumien[]).filter(
        (k) => (strumienie?.[k]?.podsumowanie.rozliczone ?? 0) > 0,
      ),
    [strumienie],
  );
  const [wybor, setWybor] = useState<Wybor>("wszystko");
  const widoczne = wybor === "wszystko" ? dni : (strumienie?.[wybor]?.dni ?? []);

  // mapa dzień → dane + lista miesięcy (rok*12+m) obecnych w PEŁNYCH danych,
  // żeby przełączanie strumienia nie zabierało miesięcy z paska nawigacji
  const { mapa, miesiace } = useMemo(() => {
    const mapa = new Map<string, SkutecznoscDnia>();
    for (const d of widoczne) if (d.rozliczone > 0) mapa.set(d.dzien, d);
    const zbior = new Set<number>();
    for (const d of dni) {
      if (d.rozliczone > 0) {
        const [r, m] = rozbijDate(d.dzien);
        zbior.add(r * 12 + m);
      }
    }
    return { mapa, miesiace: [...zbior].sort((a, b) => a - b) };
  }, [widoczne, dni]);

  const [widok, setWidok] = useState<number | null>(
    () => miesiace[miesiace.length - 1] ?? null,
  );

  if (widok == null || miesiace.length === 0) return null;

  const rok = Math.floor(widok / 12);
  const mies = widok % 12;
  const dniWMiesiacu = new Date(rok, mies + 1, 0).getDate();
  // poniedziałek = 0 (getDay: niedziela = 0)
  const start = (new Date(rok, mies, 1).getDay() + 6) % 7;
  const wMiesiacu = (d: SkutecznoscDnia) => {
    const [r, m] = rozbijDate(d.dzien);
    return r === rok && m === mies;
  };

  const miesieczne = [...mapa.values()].filter(wMiesiacu);
  const { roi: bilans, n: rozliczonych } = bilansDni(miesieczne);
  const poNowemu = bilansDni(miesieczne.filter((d) => poZmianie(d.dzien)));

  const idx = miesiace.indexOf(widok);

  const komorki: (SkutecznoscDnia | null | "pusta")[] = [
    ...Array<"pusta">(start).fill("pusta"),
    ...Array.from({ length: dniWMiesiacu }, (_, i) => {
      const klucz = `${rok}-${String(mies + 1).padStart(2, "0")}-${String(i + 1).padStart(2, "0")}`;
      return mapa.get(klucz) ?? null;
    }),
  ];

  return (
    <div className="rounded-(--radius-card) border border-hairline bg-card p-4 shadow-(--shadow-card) sm:p-5">
      {dostepne.length > 1 && (
        <div className="mb-4">
          <Segmented
            id="kalendarz-strumien"
            opcje={[
              { kod: "wszystko" as Wybor, label: "Wszystko" },
              ...dostepne.map((k) => ({
                kod: k as Wybor,
                label: NAZWY_STRUMIENI[k],
                title: `Bilans całości: ${fmtU(
                  strumienie![k]!.podsumowanie.roi_flat,
                )} z ${strumienie![k]!.podsumowanie.rozliczone} rozliczeń`,
              })),
            ]}
            wartosc={wybor}
            onChange={(v) => setWybor(v as Wybor)}
          />
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => idx > 0 && setWidok(miesiace[idx - 1])}
            disabled={idx <= 0}
            aria-label="Poprzedni miesiąc"
            className="flex h-8 w-8 items-center justify-center rounded-(--radius-control) border border-hairline text-ink-soft transition-colors hover:border-brand hover:text-brand disabled:cursor-default disabled:opacity-35 disabled:hover:border-hairline disabled:hover:text-ink-soft"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
              <path d="M15 5l-7 7 7 7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <h3 className="font-display min-w-36 text-center text-base font-bold capitalize">
            {MIESIACE[mies]} {rok}
          </h3>
          <button
            onClick={() => idx < miesiace.length - 1 && setWidok(miesiace[idx + 1])}
            disabled={idx >= miesiace.length - 1}
            aria-label="Następny miesiąc"
            className="flex h-8 w-8 items-center justify-center rounded-(--radius-control) border border-hairline text-ink-soft transition-colors hover:border-brand hover:text-brand disabled:cursor-default disabled:opacity-35 disabled:hover:border-hairline disabled:hover:text-ink-soft"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
              <path d="M9 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
        <p className="text-xs text-faint">
          bilans miesiąca:{" "}
          <span
            className={`font-data text-sm font-semibold ${
              bilans > 0
                ? "text-data-green"
                : bilans < 0
                  ? "text-data-red-ink"
                  : "text-ink-soft"
            }`}
          >
            {fmtU(bilans)}
          </span>{" "}
          · {rozliczonych} rozliczonych (stawka 1 j. na typ)
        </p>
      </div>

      <div className="grid grid-cols-7 gap-1.5">
        {DNI_TYGODNIA.map((d) => (
          <span
            key={d}
            className="pb-1 text-center text-[10px] font-semibold uppercase tracking-wide text-faint"
          >
            {d}
          </span>
        ))}
        {komorki.map((k, i) => {
          if (k === "pusta") return <span key={`p-${i}`} aria-hidden />;
          const nrDnia = i - start + 1;
          if (k === null) {
            return (
              <span
                key={i}
                className="flex aspect-square flex-col items-center justify-center rounded-(--radius-control) border border-hairline/60 text-xs text-faint/60"
                title="Brak rozliczonych typów tego dnia"
              >
                {nrDnia}
              </span>
            );
          }
          const zysk = k.roi_flat > 0.005;
          const strata = k.roi_flat < -0.005;
          const swiezy = poZmianie(k.dzien);
          return (
            <span
              key={i}
              title={`${k.dzien}: ${k.trafione}/${k.rozliczone} trafionych · bilans ${fmtU(k.roi_flat)}${
                swiezy ? "" : " · stare zasady selekcji"
              }`}
              className={`relative flex aspect-square flex-col items-center justify-center gap-0.5 rounded-(--radius-control) border text-xs ${
                zysk
                  ? "border-data-green/30 bg-data-green-wash text-data-green-ink"
                  : strata
                    ? "border-data-red/25 bg-data-red-wash text-data-red-ink"
                    : "border-hairline bg-card-soft text-ink-soft"
              } ${swiezy ? "" : "opacity-55"}`}
            >
              <span className="text-[10px] opacity-70">{nrDnia}</span>
              <span className="font-data text-[11px] font-semibold leading-none">
                {fmtU(k.roi_flat)}
              </span>
              <span className="font-data text-[9px] opacity-70">
                {k.trafione}/{k.rozliczone}
              </span>
            </span>
          );
        })}
      </div>

      {/* SKĄD STRATA: bilans każdego strumienia w tym samym miesiącu — bez
          tego jeden czerwony kafelek nie mówi, czy zawiniły typy zawodnicze,
          drużynowe czy drabinki */}
      {dostepne.length > 1 && wybor === "wszystko" && (
        <div className="mt-4 border-t border-hairline pt-3">
          <p className="text-[10px] uppercase tracking-wide text-faint">
            skąd wynik tego miesiąca
          </p>
          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1.5">
            {dostepne.map((k) => {
              const { roi, n } = bilansDni(
                (strumienie![k]!.dni ?? []).filter(wMiesiacu),
              );
              if (!n) return null;
              return (
                <button
                  key={k}
                  onClick={() => setWybor(k)}
                  className="text-left text-xs transition-colors hover:text-ink"
                  title={`Pokaż w kalendarzu tylko: ${NAZWY_STRUMIENI[k]}`}
                >
                  <span className="text-faint">{NAZWY_STRUMIENI[k]}</span>{" "}
                  <span
                    className={`font-data font-semibold ${
                      roi > 0
                        ? "text-data-green"
                        : roi < 0
                          ? "text-data-red-ink"
                          : "text-ink-soft"
                    }`}
                  >
                    {fmtU(roi)}
                  </span>{" "}
                  <span className="text-faint">({n})</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div className="mt-3 space-y-1.5 text-[11px] leading-relaxed text-faint">
        <p>
          Każdy dzień zostaje w kalendarzu, także stratny. Puste pola = brak
          rozliczonych typów.
        </p>
        {OSTATNIA_ZMIANA && (
          <p>
            <span
              aria-hidden
              className="mr-1.5 inline-block h-2.5 w-2.5 rounded-[3px] border border-hairline bg-card-soft align-[-1px] opacity-55"
            />
            Wyblakłe dni są sprzed{" "}
            {new Date(`${OSTATNIA_ZMIANA.od}T12:00:00`).toLocaleDateString(
              "pl-PL",
              { day: "numeric", month: "long" },
            )}
            , czyli sprzed zmiany zasad selekcji ({OSTATNIA_ZMIANA.etykieta}) —
            opisują model, którego już nie ma w produkcji.
            {poNowemu.n > 0 ? (
              <>
                {" "}
                Po zmianie:{" "}
                <span
                  className={`font-data font-semibold ${
                    poNowemu.roi > 0
                      ? "text-data-green"
                      : poNowemu.roi < 0
                        ? "text-data-red-ink"
                        : "text-ink-soft"
                  }`}
                >
                  {fmtU(poNowemu.roi)}
                </span>{" "}
                z {poNowemu.n} rozliczeń — za mało, żeby cokolwiek orzekać.
              </>
            ) : (
              " Nowe zasady nie mają jeszcze ani jednego rozliczenia."
            )}
          </p>
        )}
      </div>
    </div>
  );
}
