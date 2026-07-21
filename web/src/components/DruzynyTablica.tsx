"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useMemo, useState } from "react";

import { BetCard } from "./BetCard";
import { BetRow } from "./BetRow";
import { FilterDropdown } from "./FilterDropdown";
import { Reveal } from "./Reveal";
import type { DruzynaForma, ValueBet, Zawodnik } from "@/lib/types";

/**
 * Ceduła typów drużynowych pod SKALĘ sezonu (setki typów dziennie).
 * Układ: DZIŚ jest głównym elementem strony — top 3 jako karty, pod nimi
 * sortowalna ceduła dnia przycięta do LIMIT_DZIS wierszy. Kolejne dni to
 * jedna linia nagłówka ze spisem rozgrywek, rozwijana na klik (animowane).
 * Dzięki temu strona przy wejściu ma stałą, krótką wysokość niezależnie
 * od tego, czy w bazie jest 10 czy 300 typów.
 */

function kluczDnia(ts: number): string {
  return new Intl.DateTimeFormat("en-CA", {
    dateStyle: "short",
    timeZone: "Europe/Warsaw",
  }).format(new Date(ts * 1000));
}

function etykietaDnia(ts: number, teraz: number): { glowna: string; data: string } {
  const pelna = new Intl.DateTimeFormat("pl-PL", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "Europe/Warsaw",
  }).format(new Date(ts * 1000));
  if (kluczDnia(ts) === kluczDnia(teraz)) return { glowna: "dziś", data: pelna };
  if (kluczDnia(ts) === kluczDnia(teraz + 86400))
    return { glowna: "jutro", data: pelna };
  const [dow, ...reszta] = pelna.split(" ");
  // pl-PL daje "czwartek, 23 lipca" — przecinek zostaje przy dniu tygodnia
  return { glowna: dow.replace(/,$/, ""), data: reszta.join(" ") };
}

function odmienTypy(n: number): string {
  if (n === 1) return "1 typ";
  const r10 = n % 10;
  const r100 = n % 100;
  const kilka = r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14);
  return `${n} ${kilka ? "typy" : "typów"}`;
}

function odmienPozostale(n: number): string {
  const r10 = n % 10;
  const r100 = n % 100;
  const kilka = r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14);
  return `${n} ${kilka ? "pozostałe" : "pozostałych"}`;
}

const PROG_SEKCJI_TOP = 6; // poniżej tylu typów dnia karty "top" to szum
const LIMIT_DZIS = 12; // tyle wierszy ceduły dnia widać przed "pokaż wszystkie"
const LIMIT_LIGI_DNIA = 3; // tyle wierszy pokazuje otwarta liga dnia przyszłego

function dataKrotka(ts: number): string {
  return new Intl.DateTimeFormat("pl-PL", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "Europe/Warsaw",
  }).format(new Date(ts * 1000));
}

type Sort = "rank" | "szansa" | "kurs" | "godzina";
const SORTY: { kod: Sort; label: string }[] = [
  { kod: "rank", label: "najmocniejsze" },
  { kod: "szansa", label: "szansa" },
  { kod: "kurs", label: "kurs" },
  { kod: "godzina", label: "godzina" },
];

/** Animowane rozwijanie bloku — wspólny ruch dla dni, sekcji i ceduły dnia. */
function Rozwin({
  open,
  children,
}: {
  open: boolean;
  children: React.ReactNode;
}) {
  const reduced = useReducedMotion();
  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          initial={reduced ? false : { height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={reduced ? undefined : { height: 0, opacity: 0 }}
          transition={{ duration: 0.28, ease: [0.25, 0.9, 0.3, 1] }}
          className="overflow-hidden"
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Linia "pokaż pozostałe / zwiń" — jedno domknięcie listy w całej tablicy. */
function PokazButton({
  open,
  ukryte,
  zwinLabel,
  onClick,
}: {
  open: boolean;
  ukryte: number;
  zwinLabel: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full border-b border-hairline px-2 py-1.5 text-left text-[11px] font-medium text-brand-deep transition-colors hover:bg-card-soft sm:px-3"
    >
      {open ? zwinLabel : `pokaż ${odmienPozostale(ukryte)}`}
    </button>
  );
}

export function DruzynyTablica({
  bets,
  forma,
  ligaByMecz,
  teraz,
}: {
  /** typy drużynowe w kolejności rankingu silnika (najlepsze pierwsze) */
  bets: ValueBet[];
  forma: DruzynaForma[];
  /** mecz_id -> nazwa rozgrywek (z matches.json) */
  ligaByMecz: Record<number, string>;
  /** timestamp serwera (s) — spójne "dziś/jutro" bez zegara klienta */
  teraz: number;
}) {
  const [rynek, setRynek] = useState("wszystkie");
  const [liga, setLiga] = useState("wszystkie");
  const [sort, setSort] = useState<Sort>("rank");
  // kafelek dnia wybrany w slocie "dalsze dni" (null = pierwszy z brzegu)
  const [wybranyDzien, setWybranyDzien] = useState<string | null>(null);
  // akordeon lig w dniach przyszłych: zwinięta / top 3 / wszystkie
  // (klucz: "dzień|liga"; bez wpisu najmocniejsza liga dnia startuje na "top")
  const [stanLig, setStanLig] = useState<
    Record<string, "zwin" | "top" | "all">
  >({});
  const [calyDzis, setCalyDzis] = useState(false);

  const formaById = useMemo(
    () => new Map(forma.map((f) => [f.id, f])),
    [forma],
  );

  const rynki = useMemo(
    () => [...new Set(bets.map((b) => b.rynek))].sort(),
    [bets],
  );
  const ligi = useMemo(
    () =>
      [...new Set(bets.map((b) => ligaByMecz[b.mecz_id]).filter(Boolean))].sort(),
    [bets, ligaByMecz],
  );

  // liczniki do chipów rozgrywek: po filtrze rynku, przed filtrem ligi —
  // chip mówi, ile typów kryje się za kliknięciem
  const licznikLig = useMemo(() => {
    const m = new Map<string, number>();
    for (const b of bets) {
      if (rynek !== "wszystkie" && b.rynek !== rynek) continue;
      const l = ligaByMecz[b.mecz_id];
      if (l) m.set(l, (m.get(l) ?? 0) + 1);
    }
    return m;
  }, [bets, rynek, ligaByMecz]);

  const widoczne = useMemo(
    () =>
      bets.filter(
        (b) =>
          (rynek === "wszystkie" || b.rynek === rynek) &&
          (liga === "wszystkie" || ligaByMecz[b.mecz_id] === liga),
      ),
    [bets, rynek, liga, ligaByMecz],
  );

  const sortuj = useMemo(
    () =>
      (xs: ValueBet[]): ValueBet[] => {
        switch (sort) {
          case "szansa":
            return [...xs].sort((a, z) => z.p_model - a.p_model);
          case "kurs":
            return [...xs].sort(
              (a, z) => (z.kurs ?? z.fair_kurs) - (a.kurs ?? a.fair_kurs),
            );
          case "godzina":
            return [...xs].sort((a, z) => a.kickoff_ts - z.kickoff_ts);
          default:
            return xs; // kolejność wejścia = ranking silnika
        }
      },
    [sort],
  );

  const dzisKlucz = kluczDnia(teraz);
  const dzisiejsze = useMemo(
    () => widoczne.filter((b) => kluczDnia(b.kickoff_ts) === dzisKlucz),
    [widoczne, dzisKlucz],
  );

  // karty top: 3 najlepsze dnia wg rankingu silnika — stała kotwica,
  // niezależna od wybranego sortowania ceduły
  const topIds = useMemo(() => {
    if (dzisiejsze.length < PROG_SEKCJI_TOP) return new Set<number>();
    return new Set(dzisiejsze.slice(0, 3).map((b) => b.id));
  }, [dzisiejsze]);
  const top = dzisiejsze.filter((b) => topIds.has(b.id));
  const cedulaDzis = sortuj(dzisiejsze.filter((b) => !topIds.has(b.id)));

  const przyszle = useMemo(
    () => widoczne.filter((b) => kluczDnia(b.kickoff_ts) !== dzisKlucz),
    [widoczne, dzisKlucz],
  );

  /**
   * Kolejne dni chronologicznie, w dniu sekcje rozgrywek (dla sortu
   * "najmocniejsze") — rozgrywki i typy wg rankingu silnika.
   */
  const dni = useMemo(() => {
    const rankiem = new Map(przyszle.map((b, i) => [b.id, i]));
    const wgDnia = new Map<string, ValueBet[]>();
    for (const b of [...przyszle].sort((a, z) => a.kickoff_ts - z.kickoff_ts)) {
      const k = kluczDnia(b.kickoff_ts);
      (wgDnia.get(k) ?? wgDnia.set(k, []).get(k)!).push(b);
    }
    return [...wgDnia.entries()].map(([klucz, lista]) => {
      const wgLigi = new Map<string, ValueBet[]>();
      for (const b of lista) {
        const l = ligaByMecz[b.mecz_id] ?? "Inne rozgrywki";
        (wgLigi.get(l) ?? wgLigi.set(l, []).get(l)!).push(b);
      }
      const sekcje = [...wgLigi.entries()].map(([nazwa, typy]) => ({
        nazwa,
        typy: [...typy].sort(
          (a, z) => (rankiem.get(a.id) ?? 0) - (rankiem.get(z.id) ?? 0),
        ),
      }));
      sekcje.sort(
        (a, z) =>
          Math.min(...a.typy.map((t) => rankiem.get(t.id) ?? 0)) -
          Math.min(...z.typy.map((t) => rankiem.get(t.id) ?? 0)),
      );
      return { klucz, lista, sekcje };
    });
  }, [przyszle, ligaByMecz]);

  // stała struktura sekcji: jutro zawsze osobno, dalsze dni w jednym
  // slocie z kafelkami wyboru — liczba sekcji nie rośnie z terminarzem
  const jutroKlucz = kluczDnia(teraz + 86400);
  const jutro = dni.find((d) => d.klucz === jutroKlucz);
  const dalsze = dni.filter((d) => d.klucz !== jutroKlucz);
  const dalszyKlucz =
    wybranyDzien && dalsze.some((d) => d.klucz === wybranyDzien)
      ? wybranyDzien
      : dalsze[0]?.klucz;
  const dalszy = dalsze.find((d) => d.klucz === dalszyKlucz);

  const meczeN = new Set(widoczne.map((b) => b.mecz_id)).size;
  const ligiN = new Set(
    widoczne.map((b) => ligaByMecz[b.mecz_id]).filter(Boolean),
  ).size;

  const formaRynku = (bet: ValueBet) =>
    formaById.get(bet.podmiot_id)?.forma[bet.rynek_kod];

  const wiersz = (bet: ValueBet, zLiga: boolean) => (
    <BetRow
      key={bet.id}
      bet={bet}
      forma={formaRynku(bet)}
      pokazGodzine={sort === "godzina"}
      liga={zLiga ? ligaByMecz[bet.mecz_id] : undefined}
    />
  );

  /**
   * Blok dnia przyszłego: gazetowy nagłówek + AKORDEON LIG. Najmocniejsza
   * liga dnia startuje otwarta (top 3), reszta to zwinięte nagłówki
   * z licznikami. Zwinięta liga = niezamontowane wiersze, więc duży dzień
   * kosztuje przy hydracji tylko tyle, ile realnie widać. Sortowanie działa
   * wewnątrz lig — struktura ligowa zostaje przy każdym sorcie.
   */
  const blokDnia = ({ klucz, lista, sekcje }: (typeof dni)[number]) => {
    const et = etykietaDnia(lista[0].kickoff_ts, teraz);
    return (
      <div key={klucz} className="mt-5">
        {/* nagłówek dnia jak w gazecie: gruba kreska + wersaliki; sticky,
            żeby przy długim dniu nie gubić orientacji */}
        <div className="sticky top-[4.4rem] z-10 -mx-4 bg-paper/85 px-4 backdrop-blur-md sm:-mx-6 sm:px-6">
          <div className="flex items-baseline gap-x-3 border-t-2 border-ink pb-1.5 pt-2">
            <span className="font-display text-lg font-bold uppercase leading-none tracking-tight">
              {et.glowna}
            </span>
            <span className="hidden text-xs text-faint sm:inline">{et.data}</span>
            <span className="ml-auto shrink-0 font-data text-xs text-muted">
              {odmienTypy(lista.length)}
            </span>
          </div>
        </div>

        {sekcje.map(({ nazwa, typy }, idx) => {
          const kluczSekcji = `${klucz}|${nazwa}`;
          const stan = stanLig[kluczSekcji] ?? (idx === 0 ? "top" : "zwin");
          const otwarta = stan !== "zwin";
          // zwijanie ogona dopiero gdy schowa ≥2 wiersze — "pokaż 1
          // pozostały" to więcej UI niż treści
          const zwijalna = typy.length > LIMIT_LIGI_DNIA + 1;
          const posortowane = sortuj(typy);
          return (
            <section
              key={nazwa}
              aria-label={`${nazwa}: ${odmienTypy(typy.length)}`}
              className="mt-2 first:mt-1"
            >
              <button
                onClick={() =>
                  setStanLig((s) => ({
                    ...s,
                    [kluczSekcji]: otwarta ? "zwin" : "top",
                  }))
                }
                aria-expanded={otwarta}
                className="group flex w-full items-baseline gap-2.5 py-1.5 text-left"
              >
                <h3
                  className={`font-display shrink-0 text-[11px] font-semibold uppercase tracking-widest transition-colors ${
                    otwarta ? "text-ink" : "text-muted group-hover:text-ink"
                  }`}
                >
                  {nazwa}
                </h3>
                <span
                  aria-hidden
                  className="flex-1 self-center border-t border-dotted border-hairline-strong/70"
                />
                <span className="font-data shrink-0 text-[11px] text-faint">
                  {odmienTypy(typy.length)}
                </span>
                <svg
                  aria-hidden
                  width="11"
                  height="11"
                  viewBox="0 0 14 14"
                  className={`shrink-0 self-center text-faint transition-transform ${
                    otwarta ? "rotate-180" : ""
                  }`}
                >
                  <path
                    d="M3 5.5 L7 9.5 L11 5.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
              <Rozwin open={otwarta}>
                <div>
                  {posortowane
                    .slice(0, zwijalna ? LIMIT_LIGI_DNIA : typy.length)
                    .map((b) => wiersz(b, false))}
                  {zwijalna && (
                    <>
                      <Rozwin open={stan === "all"}>
                        <div>
                          {posortowane
                            .slice(LIMIT_LIGI_DNIA)
                            .map((b) => wiersz(b, false))}
                        </div>
                      </Rozwin>
                      <PokazButton
                        open={stan === "all"}
                        ukryte={typy.length - LIMIT_LIGI_DNIA}
                        zwinLabel="pokaż tylko najmocniejsze"
                        onClick={() =>
                          setStanLig((s) => ({
                            ...s,
                            [kluczSekcji]: stan === "all" ? "top" : "all",
                          }))
                        }
                      />
                    </>
                  )}
                </div>
              </Rozwin>
            </section>
          );
        })}
      </div>
    );
  };

  return (
    <div>
      {/* odczyty + sortowanie + filtry w jednej bandzie: żywy stan tablicy */}
      <div className="mt-6 border-y border-hairline py-3">
        <div className="flex flex-wrap items-center justify-between gap-x-5 gap-y-2.5">
          <p className="font-data text-xs text-muted">
            <span className="font-semibold text-ink">{odmienTypy(widoczne.length)}</span>
            {" · "}
            {meczeN} {meczeN === 1 ? "mecz" : meczeN < 5 ? "mecze" : "meczów"}
            {ligiN > 0 && (
              <>
                {" · "}
                {ligiN} {ligiN === 1 ? "rozgrywki" : "rozgrywek"}
              </>
            )}
          </p>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <div
              role="group"
              aria-label="Sortowanie typów"
              className="flex items-center gap-3"
            >
              {SORTY.map((s) => (
                <button
                  key={s.kod}
                  onClick={() => setSort(s.kod)}
                  aria-pressed={sort === s.kod}
                  className={`border-b-2 pb-0.5 text-[11px] font-semibold uppercase tracking-wide transition-colors ${
                    sort === s.kod
                      ? "border-brand text-brand-deep"
                      : "border-transparent text-muted hover:text-ink"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
            {rynki.length > 1 && (
              <FilterDropdown
                label="Rynek"
                value={rynek}
                options={[
                  { value: "wszystkie", label: "Wszystkie rynki" },
                  ...rynki.map((r) => ({ value: r, label: r })),
                ]}
                onChange={setRynek}
              />
            )}
          </div>
        </div>
        {/* chipy rozgrywek: filtr jednym klikiem + od razu widać, gdzie jest
            mięso; na mobile pas przewijany poziomo */}
        {ligi.length > 1 && (
          <div
            role="group"
            aria-label="Filtr rozgrywek"
            className="-mx-1 mt-2.5 flex gap-1.5 overflow-x-auto px-1 [scrollbar-width:none] sm:flex-wrap"
          >
            <button
              onClick={() => setLiga("wszystkie")}
              aria-pressed={liga === "wszystkie"}
              className={`shrink-0 rounded-full border px-2.5 py-1 text-xs transition-colors ${
                liga === "wszystkie"
                  ? "border-brand bg-brand-wash font-semibold text-brand-deep"
                  : "border-hairline text-muted hover:border-hairline-strong hover:text-ink"
              }`}
            >
              Wszystkie
            </button>
            {ligi.map((l) => (
              <button
                key={l}
                onClick={() => setLiga(liga === l ? "wszystkie" : l)}
                aria-pressed={liga === l}
                className={`shrink-0 rounded-full border px-2.5 py-1 text-xs transition-colors ${
                  liga === l
                    ? "border-brand bg-brand-wash font-semibold text-brand-deep"
                    : "border-hairline text-muted hover:border-hairline-strong hover:text-ink"
                }`}
              >
                {l}
                <span className="font-data ml-1.5 text-[10px] opacity-70">
                  {licznikLig.get(l) ?? 0}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {widoczne.length === 0 ? (
        <p className="mt-8 text-sm text-muted">
          Brak typów dla tych filtrów. Zdejmij filtr, żeby zobaczyć całą listę.
        </p>
      ) : (
        <>
          {/* GŁÓWNY ELEMENT: dzisiejsza tablica — karty top 3 + sortowalna
              ceduła dnia przycięta do LIMIT_DZIS wierszy */}
          {/* dziś bez typów: jedna cicha linia zamiast znikającej sekcji —
              strona nie wygląda na zepsutą, gdy terminarz ma dziurę */}
          {dzisiejsze.length === 0 && (jutro || dalszy) && (
            <div className="mt-7">
              <div className="flex items-baseline gap-x-3 border-t-2 border-ink pt-2.5">
                <h2 className="font-display text-xl font-bold uppercase leading-none tracking-tight">
                  dziś
                </h2>
                <span className="hidden text-xs text-faint sm:inline">
                  {etykietaDnia(teraz, teraz).data}
                </span>
              </div>
              <p className="mt-2 text-sm text-muted">
                Na dziś nie ma typów drużynowych. Najbliższe mecze znajdziesz
                niżej{jutro ? ", pierwsze już jutro" : ""}.
              </p>
            </div>
          )}

          {dzisiejsze.length > 0 && (
            <section aria-label="Typy na dziś" className="mt-7">
              <div className="flex items-baseline gap-x-3 border-t-2 border-ink pt-2.5">
                <h2 className="font-display text-xl font-bold uppercase leading-none tracking-tight">
                  dziś
                </h2>
                <span className="hidden text-xs text-faint sm:inline">
                  {etykietaDnia(teraz, teraz).data}
                </span>
                <span className="ml-auto shrink-0 font-data text-xs text-muted">
                  {odmienTypy(dzisiejsze.length)}
                </span>
              </div>

              {top.length > 0 && (
                <div className="mt-4 space-y-4">
                  {top.map((bet, i) => (
                    <Reveal key={bet.id} delay={Math.min(i * 0.05, 0.2)}>
                      <BetCard
                        bet={bet}
                        rank={i + 1}
                        zawodnik={
                          // BetCard czyta z tego obiektu wyłącznie `forma` —
                          // kształt DruzynaForma celowo pokrywa potrzebne pola
                          formaById.get(bet.podmiot_id) as unknown as
                            | Zawodnik
                            | undefined
                        }
                      />
                    </Reveal>
                  ))}
                </div>
              )}

              {cedulaDzis.length > 0 && (
                <div className="mt-5">
                  {cedulaDzis.slice(0, LIMIT_DZIS).map((b) => wiersz(b, true))}
                  {cedulaDzis.length > LIMIT_DZIS && (
                    <>
                      <Rozwin open={calyDzis}>
                        <div>
                          {cedulaDzis.slice(LIMIT_DZIS).map((b) => wiersz(b, true))}
                        </div>
                      </Rozwin>
                      <PokazButton
                        open={calyDzis}
                        ukryte={cedulaDzis.length - LIMIT_DZIS}
                        zwinLabel="zwiń listę dnia"
                        onClick={() => setCalyDzis((v) => !v)}
                      />
                    </>
                  )}
                </div>
              )}
            </section>
          )}

          {(jutro || dalszy) && (
            <section aria-label="Typy na kolejne dni" className="mt-10">
              <h2 className="flex items-center gap-2.5 font-body text-xs font-semibold uppercase tracking-widest text-muted">
                <span aria-hidden className="h-px w-6 bg-hairline" />
                Kolejne dni
              </h2>

              {jutro && blokDnia(jutro)}

              {/* slot dalszych dni: kafelki wyboru + jeden widoczny dzień —
                  liczba sekcji strony stała niezależnie od terminarza */}
              {dalsze.length > 1 && (
                <div
                  role="group"
                  aria-label="Wybierz dzień"
                  className="-mx-1 mt-7 flex gap-1.5 overflow-x-auto px-1 [scrollbar-width:none] sm:flex-wrap"
                >
                  {dalsze.map((d) => {
                    const et = etykietaDnia(d.lista[0].kickoff_ts, teraz);
                    const aktywny = d.klucz === dalszyKlucz;
                    return (
                      <button
                        key={d.klucz}
                        onClick={() => setWybranyDzien(d.klucz)}
                        aria-pressed={aktywny}
                        className={`shrink-0 rounded-(--radius-control) border px-3 py-1.5 text-left transition-colors ${
                          aktywny
                            ? "border-brand bg-brand-wash"
                            : "border-hairline hover:border-hairline-strong"
                        }`}
                      >
                        <span
                          className={`block text-[11px] font-semibold uppercase tracking-wide ${
                            aktywny ? "text-brand-deep" : "text-ink"
                          }`}
                        >
                          {et.glowna}
                        </span>
                        <span
                          className={`font-data block text-[10px] ${
                            aktywny ? "text-brand-deep/80" : "text-faint"
                          }`}
                        >
                          {dataKrotka(d.lista[0].kickoff_ts)} · {d.lista.length}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
              {dalszy && blokDnia(dalszy)}
            </section>
          )}
        </>
      )}
    </div>
  );
}
