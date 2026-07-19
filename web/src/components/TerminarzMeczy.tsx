"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { fmtMnoznik } from "@/lib/format";
import type { Mecz } from "@/lib/types";

/**
 * Terminarz meczów jak tablica odjazdów (nie siatka kart): wiersze na
 * wspólnej szynie czasu, grupowane po dniach. Zbudowany pod sezon ligowy:
 * przyklejany pasek dni (skok do sekcji), przyklejane nagłówki dni przy
 * scrollu i filtr „tylko z okazjami", bo przy 30+ meczach większość
 * spotkań nie ma jeszcze przewagi.
 */

function godzina(ts: number): string {
  return new Intl.DateTimeFormat("pl-PL", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  }).format(new Date(ts * 1000));
}

function kluczDnia(ts: number): string {
  return new Intl.DateTimeFormat("sv-SE", {
    dateStyle: "short",
    timeZone: "Europe/Warsaw",
  }).format(new Date(ts * 1000));
}

/** Etykieta dnia: „dziś" / „jutro" / „piątek, 24 lipca" (teraz z serwera). */
function etykietaDnia(ts: number, teraz: number): { glowna: string; data: string } {
  const d = new Date(ts * 1000);
  const dzis = kluczDnia(teraz);
  const jutro = kluczDnia(teraz + 86400);
  const pelna = new Intl.DateTimeFormat("pl-PL", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "Europe/Warsaw",
  }).format(d);
  if (kluczDnia(ts) === dzis) return { glowna: "dziś", data: pelna };
  if (kluczDnia(ts) === jutro) return { glowna: "jutro", data: pelna };
  const [dow, ...reszta] = pelna.split(" ");
  return { glowna: dow, data: reszta.join(" ") };
}

/** Krótka etykieta do paska dni: „dziś" / „jutro" / „pt 24.07". */
function krotkaDnia(ts: number, teraz: number): string {
  if (kluczDnia(ts) === kluczDnia(teraz)) return "dziś";
  if (kluczDnia(ts) === kluczDnia(teraz + 86400)) return "jutro";
  return new Intl.DateTimeFormat("pl-PL", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    timeZone: "Europe/Warsaw",
  }).format(new Date(ts * 1000));
}

function odmienOkazje(n: number): string {
  if (n === 1) return "1 okazja";
  const r10 = n % 10;
  const r100 = n % 100;
  return `${n} ${r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14) ? "okazje" : "okazji"}`;
}

function odmienMecze(n: number): string {
  if (n === 1) return "1 mecz";
  const r10 = n % 10;
  const r100 = n % 100;
  return `${n} ${r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14) ? "mecze" : "meczów"}`;
}

function WierszMeczu({
  mecz: m,
  okazje,
  sugestie,
  najlepsza,
  soon,
}: {
  mecz: Mecz;
  okazje: number;
  sugestie: number;
  najlepsza?: number;
  soon: boolean;
}) {
  const skan =
    okazje > 0
      ? odmienOkazje(okazje)
      : sugestie > 0
        ? `${sugestie} sug. STS`
        : "bez przewagi";
  return (
    <li>
      <Link
        href={`/mecze/${m.id}`}
        className="group -mx-3 flex items-stretch gap-x-4 rounded-(--radius-control) px-3 transition-colors hover:bg-brand-wash/30 sm:gap-x-6"
      >
        {/* kolumna czasu: prawa krawędź kolumny = szyna terminarza */}
        <div className="relative w-14 shrink-0 border-r border-hairline-strong/70 py-4 pr-3 sm:w-20 sm:pr-5">
          <p
            className={`font-data text-base font-bold leading-none tracking-tight sm:text-xl ${
              soon ? "text-data-amber-ink" : "text-ink"
            }`}
          >
            {godzina(m.kickoff_ts)}
          </p>
          {soon && (
            <p className="mt-1 text-[9px] font-semibold uppercase tracking-wide text-data-amber-ink">
              wkrótce
            </p>
          )}
          {/* przystanek na szynie */}
          <span
            aria-hidden
            className={`absolute -right-[5px] top-[21px] h-[9px] w-[9px] rounded-full border-2 bg-card transition-colors sm:top-[23px] ${
              soon
                ? "live-dot border-data-amber"
                : "border-hairline-strong group-hover:border-brand"
            }`}
          />
        </div>

        {/* drużyny + fakty */}
        <div className="min-w-0 flex-1 py-4">
          <p className="font-display text-base font-bold leading-snug tracking-tight sm:text-lg">
            {m.gospodarz}
            <span className="mx-2 text-[10px] font-semibold uppercase tracking-widest text-faint">
              vs
            </span>
            {m.gosc}
          </p>
          <p className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-xs text-muted">
            {m.sklady_ogloszone ? (
              <span
                className="flex items-center gap-1.5 font-medium text-data-green-ink"
                title="Oficjalne jedenastki znane, model przeliczony na pewnych składach"
              >
                <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-data-green" />
                składy ogłoszone
              </span>
            ) : (
              <span title="Oficjalne składy ok. 1 h przed meczem, wtedy model przelicza wszystko od nowa">
                składy ok. 1 h przed
              </span>
            )}
            {m.sedzia && (
              <span className="min-w-0 truncate">
                sędzia {m.sedzia}
                {Math.abs(m.sedzia_mnoznik_fauli - 1) > 0.05 && (
                  <span
                    className={`font-data ml-1.5 font-semibold ${
                      m.sedzia_mnoznik_fauli > 1
                        ? "text-data-red-ink"
                        : "text-data-green-ink"
                    }`}
                    title="Ile fauli gwiżdże ten sędzia względem średniej ligi"
                  >
                    faule {fmtMnoznik(m.sedzia_mnoznik_fauli)}
                  </span>
                )}
              </span>
            )}
          </p>

          {/* wynik skanu na telefonie — pod drużynami */}
          <p className="mt-2 flex items-baseline gap-x-3 text-xs sm:hidden">
            <span
              className={`font-data font-semibold ${
                okazje > 0 ? "text-ink" : "text-faint"
              }`}
            >
              {skan}
            </span>
            {najlepsza !== undefined && (
              <span className="font-data font-semibold text-data-green">
                do +{najlepsza.toFixed(0)}%
              </span>
            )}
          </p>
        </div>

        {/* wynik skanu + strzałka (desktop) */}
        <div className="hidden shrink-0 items-center gap-x-5 py-4 sm:flex">
          <div className="text-right">
            <p
              className={`font-data text-sm font-semibold leading-tight ${
                okazje > 0 ? "text-ink" : "text-faint"
              }`}
            >
              {skan}
            </p>
            {najlepsza !== undefined && (
              <p
                className="font-data mt-0.5 text-xs font-semibold text-data-green"
                title="Najlepsza wartość wśród okazji z tego meczu"
              >
                najlepsza do +{najlepsza.toFixed(0)}%
              </p>
            )}
          </div>
          <span
            aria-hidden
            className="text-faint transition-all group-hover:translate-x-0.5 group-hover:text-brand"
          >
            →
          </span>
        </div>
      </Link>
    </li>
  );
}

export function TerminarzMeczy({
  mecze,
  okazje,
  sugestie,
  najlepsze,
  teraz,
}: {
  mecze: Mecz[];
  /** liczby per mecz_id (serializowalne rekordy z serwera) */
  okazje: Record<number, number>;
  sugestie: Record<number, number>;
  najlepsze: Record<number, number>;
  /** znacznik czasu serwera — „dziś/jutro/wkrótce" liczone deterministycznie */
  teraz: number;
}) {
  const [tylkoOkazje, setTylkoOkazje] = useState(false);

  const widoczne = useMemo(
    () =>
      tylkoOkazje
        ? mecze.filter((m) => (okazje[m.id] ?? 0) > 0 || (sugestie[m.id] ?? 0) > 0)
        : mecze,
    [mecze, okazje, sugestie, tylkoOkazje],
  );

  const dni = useMemo(() => {
    const posortowane = [...widoczne].sort((a, b) => a.kickoff_ts - b.kickoff_ts);
    const out: { klucz: string; mecze: Mecz[] }[] = [];
    for (const m of posortowane) {
      const k = kluczDnia(m.kickoff_ts);
      const d = out.find((x) => x.klucz === k);
      if (d) d.mecze.push(m);
      else out.push({ klucz: k, mecze: [m] });
    }
    return out;
  }, [widoczne]);

  const zOkazjami = mecze.filter(
    (m) => (okazje[m.id] ?? 0) > 0 || (sugestie[m.id] ?? 0) > 0,
  ).length;

  if (mecze.length === 0) {
    return (
      <div className="mt-8 rounded-(--radius-card) border border-dashed border-hairline-strong bg-card px-8 py-14 text-center shadow-(--shadow-card)">
        <p className="font-semibold">Brak nadchodzących meczów w skanie</p>
        <p className="mx-auto mt-1.5 max-w-md text-sm leading-relaxed text-muted">
          Wszystkie przeanalizowane mecze już się rozpoczęły albo zakończyły.
          Nowe pojawią się tutaj, gdy tylko bukmacher wystawi linie na kolejne
          spotkania.
        </p>
      </div>
    );
  }

  return (
    <div className="mt-6">
      {/* pasek nawigacji: dni jako skoki + filtr okazji; przykleja się pod
          nawigacją, żeby przy długim sezonowym terminarzu nie wracać na górę */}
      <div className="sticky top-[4.4rem] z-20 -mx-4 bg-paper/85 px-4 py-2 backdrop-blur-md sm:-mx-6 sm:px-6">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
          <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto pb-0.5">
            {dni.map(({ klucz, mecze: grupa }) => (
              <a
                key={klucz}
                href={`#dzien-${klucz}`}
                className="font-data shrink-0 whitespace-nowrap rounded-full border border-hairline bg-card px-3 py-1 text-xs font-medium text-muted shadow-(--shadow-card) transition-colors hover:border-brand/40 hover:text-brand-deep"
              >
                {krotkaDnia(grupa[0].kickoff_ts, teraz)}
              </a>
            ))}
          </div>
          <button
            onClick={() => setTylkoOkazje((v) => !v)}
            aria-pressed={tylkoOkazje}
            title="Pokaż tylko mecze, w których skan znalazł okazje albo sugestie STS"
            className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
              tylkoOkazje
                ? "border-brand/50 bg-brand-wash font-semibold text-brand-deep"
                : "border-hairline bg-card text-muted shadow-(--shadow-card) hover:text-ink"
            }`}
          >
            {tylkoOkazje && (
              <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-brand" />
            )}
            tylko z okazjami
            <span className="font-data">{zOkazjami}</span>
          </button>
        </div>
      </div>

      {widoczne.length === 0 ? (
        <div className="mt-8 rounded-(--radius-card) border border-dashed border-hairline bg-card-soft/50 px-6 py-12 text-center">
          <p className="text-sm font-medium text-ink">
            Żaden nadchodzący mecz nie ma jeszcze okazji
          </p>
          <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted">
            Okazje pojawiają się zwykle 1–2 dni przed meczem, gdy bukmacher
            wystawi linie. Wyłącz filtr, żeby zobaczyć pełny terminarz.
          </p>
        </div>
      ) : (
        dni.map(({ klucz, mecze: grupa }) => {
          const et = etykietaDnia(grupa[0].kickoff_ts, teraz);
          return (
            <section key={klucz} id={`dzien-${klucz}`} className="mt-8 scroll-mt-32">
              {/* nagłówek dnia przykleja się pod paskiem nawigacji */}
              <div className="sticky top-[7.1rem] z-10 -mx-3 bg-paper/90 px-3 py-1.5 backdrop-blur-md">
                <div className="flex items-baseline gap-3">
                  <h2 className="font-display shrink-0 text-xs font-semibold uppercase tracking-widest text-brand">
                    {et.glowna}
                  </h2>
                  <span className="shrink-0 text-xs text-faint">{et.data}</span>
                  <span aria-hidden className="h-px flex-1 self-center bg-hairline" />
                  <span className="font-data shrink-0 text-xs text-faint">
                    {odmienMecze(grupa.length)}
                  </span>
                </div>
              </div>

              <ul className="mt-1 divide-y divide-hairline/70">
                {grupa.map((m) => (
                  <WierszMeczu
                    key={m.id}
                    mecz={m}
                    okazje={okazje[m.id] ?? 0}
                    sugestie={sugestie[m.id] ?? 0}
                    najlepsza={najlepsze[m.id]}
                    soon={m.kickoff_ts - teraz < 3 * 3600}
                  />
                ))}
              </ul>
            </section>
          );
        })
      )}
    </div>
  );
}
