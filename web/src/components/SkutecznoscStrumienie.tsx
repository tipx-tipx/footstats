"use client";

import { useMemo, useState } from "react";

import { KartyDrabinek } from "./KartyDrabinek";
import { Segmented } from "./Segmented";
import { SkutecznoscDzienna } from "./SkutecznoscDzienna";
import type { SkutecznoscStrumienia, Strumien, TypyWyniki } from "@/lib/types";

/**
 * Skuteczność rozbita na STRUMIENIE zamiast jednego wspólnego licznika.
 *
 * Typ zawodniczy z silnika, rynek drużynowy i karta z drabinki to trzy różne
 * produkty: inne źródło prawdopodobieństwa, inne ryzyko, inne bramy jakości.
 * Wspólna liczba uśredniała je w coś, co nie odpowiadało na żadne konkretne
 * pytanie — a przede wszystkim nie mówiła, czy drabinki w ogóle działają.
 */
const OPIS: Record<Strumien, { label: string; opis: string }> = {
  pewniaki: {
    label: "Pewniaki",
    opis:
      "Typy zawodnicze policzone przez silnik i opublikowane na liście typów — to one uczą kalibrację modelu.",
  },
  druzyny: {
    label: "Drużyny",
    opis:
      "Rynki drużynowe (gole, rożne, kartki, strzały zespołu) — osobny produkt o innym profilu ryzyka niż typy zawodnicze.",
  },
  drabinki: {
    label: "Drabinki",
    opis:
      "Wybrany typ z każdej karty Drabinek. Jego szansa NIE pochodzi z silnika, tylko z pokrycia linii skorygowanego o rywala, sędziego i scenariusz meczu — dlatego rozlicza się osobno i nie miesza się do kalibracji modelu.",
  },
};

/** Kafelek liczbowy podsumowania strumienia. */
function Kafelek({
  etykieta,
  wartosc,
  akcent,
  tytul,
}: {
  etykieta: string;
  wartosc: string;
  akcent?: "dodatni" | "ujemny";
  tytul?: string;
}) {
  return (
    <div
      className="rounded-(--radius-control) border border-hairline bg-card px-3.5 py-2.5"
      title={tytul}
    >
      <p className="text-[10px] uppercase tracking-wide text-faint">
        {etykieta}
      </p>
      <p
        className={`font-data mt-0.5 text-lg font-semibold ${
          akcent === "dodatni"
            ? "text-data-green-ink"
            : akcent === "ujemny"
              ? "text-data-amber-ink"
              : "text-ink"
        }`}
      >
        {wartosc}
      </p>
    </div>
  );
}

export function SkutecznoscStrumienie({
  strumienie,
  fallbackDni,
}: {
  strumienie?: TypyWyniki["skutecznosc_strumienie"];
  /** stary, wspólny widok — gdy backend nie przysłał jeszcze strumieni */
  fallbackDni?: TypyWyniki["skutecznosc_dzienna"];
}) {
  // pokazujemy tylko strumienie, które mają co pokazać: pusta zakładka
  // „Drabinki — 0 rozliczonych" jest gorsza niż jej brak
  const dostepne = useMemo(() => {
    const kolejnosc: Strumien[] = ["pewniaki", "druzyny", "drabinki"];
    return kolejnosc.filter(
      (k) => (strumienie?.[k]?.podsumowanie.rozliczone ?? 0) > 0,
    );
  }, [strumienie]);

  const [aktywny, setAktywny] = useState<Strumien>(dostepne[0] ?? "pewniaki");
  const wybrany: Strumien = dostepne.includes(aktywny)
    ? aktywny
    : (dostepne[0] ?? "pewniaki");
  const dane: SkutecznoscStrumienia | undefined = strumienie?.[wybrany];

  if (!dostepne.length) {
    return fallbackDni?.length ? (
      <SkutecznoscDzienna dni={fallbackDni} />
    ) : null;
  }

  const p = dane!.podsumowanie;
  const roi = p.roi_flat;

  return (
    <div className="mt-5 max-w-3xl">
      {dostepne.length > 1 && (
        <Segmented
          id="strumien-skutecznosci"
          opcje={dostepne.map((k) => ({
            kod: k,
            label: OPIS[k].label,
            title: OPIS[k].opis,
          }))}
          wartosc={wybrany}
          onChange={(v) => setAktywny(v as Strumien)}
        />
      )}

      <p className="mt-3 max-w-prose text-xs leading-relaxed text-muted">
        {OPIS[wybrany].opis}
      </p>

      <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <Kafelek
          etykieta="rozliczone"
          wartosc={String(p.rozliczone)}
          tytul="Typy z tego strumienia, których mecze już się zakończyły"
        />
        <Kafelek
          etykieta="trafione"
          wartosc={`${p.trafione}/${p.rozliczone}`}
        />
        <Kafelek
          etykieta="skuteczność"
          wartosc={
            p.skutecznosc != null ? `${Math.round(p.skutecznosc * 100)}%` : "—"
          }
        />
        <Kafelek
          etykieta="ROI flat"
          wartosc={`${roi >= 0 ? "+" : "−"}${Math.abs(roi).toFixed(2)} j.`}
          akcent={roi > 0 ? "dodatni" : roi < 0 ? "ujemny" : undefined}
          tytul="Wynik przy stawce 1 jednostki na każdy typ z kursem"
        />
      </div>

      {/* drabinki: czy klasa karty cokolwiek znaczy — jedyny sposób sprawdzić,
          czy progi „top/mocny/solidny" są ustawione sensownie */}
      {dane!.klasy && (
        <div className="mt-3 rounded-(--radius-control) border border-hairline bg-card px-3.5 py-3">
          <p
            className="text-[10px] uppercase tracking-wide text-faint"
            title="Jeśli karty oznaczone jako TOP nie trafiają lepiej niż solidne, progi klas są do poprawki — i tu to widać"
          >
            czy oznaczenia się bronią
          </p>
          <div className="mt-1.5 flex flex-wrap gap-x-5 gap-y-1">
            {["top", "mocny", "solidny"]
              .filter((k) => dane!.klasy![k])
              .map((k) => {
                const v = dane!.klasy![k];
                return (
                  <span key={k} className="font-data text-[11px] text-ink-soft">
                    <span className="text-faint">{k}</span>{" "}
                    <span className="font-semibold">
                      {Math.round(v.skutecznosc * 100)}%
                    </span>
                    <span className="text-faint">
                      {" "}
                      ({v.trafione}/{v.n})
                    </span>
                  </span>
                );
              })}
          </div>
        </div>
      )}

      {/* DRABINKI: kronika kart zamiast pagera po dniach. Kart jest kilka na
          dobę, więc pytanie „która weszła, a która nie" musi mieć odpowiedź
          bez klikania po dniach — patrz KartyDrabinek. Pozostałe strumienie
          (dziesiątki typów dziennie) zostają przy widoku dziennym. */}
      {dane!.dni.length > 0 &&
        (wybrany === "drabinki" ? (
          <KartyDrabinek dni={dane!.dni} />
        ) : (
          <SkutecznoscDzienna dni={dane!.dni} />
        ))}
    </div>
  );
}
