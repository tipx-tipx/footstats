"use client";

import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useId, useMemo, useState } from "react";

import { fmtLinia, odmien } from "@/lib/format";

import { useDzis } from "../czas";
import type { DaneSkutecznosci, DzienWynikow, Produkt, TypWyniku } from "../../_dane/skutecznosc";

/*
 * Etap 5.5 – Skuteczność (widok klienta). Głos marki: każdy typ zostaje
 * w historii, także nietrafione. Bez kuchni modelu (to jest u admina).
 * Warianty różnią się tym, jak się wybiera dzień: kalendarz, lista dni, wykres.
 */

type Filtr = "wszystko" | Produkt;
const FILTRY: [Filtr, string][] = [
  ["wszystko", "Wszystko"],
  ["zawodnicy", "Zawodnicy"],
  ["druzyny", "Drużyny"],
  ["drabinki", "Drabinki"],
];
const TYDZ = ["nd", "pn", "wt", "śr", "cz", "pt", "sb"];

const proc = (ok: number, n: number) => (n ? Math.round((ok / n) * 100) : 0);
const kursTxt = (k: number) => k.toFixed(2).replace(".", ",");
const odmTyp = (n: number) => (n === 1 ? "typu" : "typów");

function licz(typy: TypWyniku[]) {
  let ok = 0;
  let n = 0;
  let zwrot = 0;
  for (const t of typy) {
    if (t.wynik === "wygrany") ok++;
    if (t.wynik === "zwrot") zwrot++;
    else n++;
  }
  return { ok, n, zwrot, p: proc(ok, n) };
}

/** poniżej tylu rozstrzygniętych typów procent dnia nic nie mówi (2 z 2 = „100%”) */
const MALA_PROBA = 5;
const MIESIACE = ["styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień"];

function poziomDnia(l: { p: number; n: number }) {
  if (l.n < MALA_PROBA) return "proba";
  return l.p >= 65 ? "mocny" : l.p >= 55 ? "sredni" : "slaby";
}

function opisDnia(klucz: string) {
  const d = new Date(`${klucz}T12:00:00Z`);
  return { tyg: TYDZ[d.getUTCDay()], data: `${d.getUTCDate()}.${String(d.getUTCMonth() + 1).padStart(2, "0")}`, nr: d.getUTCDate(), dzienTyg: (d.getUTCDay() + 6) % 7 };
}

function etykieta(d: DzienWynikow, dzis: string) {
  const wczoraj = new Date(`${dzis}T12:00:00Z`);
  wczoraj.setUTCDate(wczoraj.getUTCDate() - 1);
  if (d.klucz === dzis) return "Dziś";
  if (d.klucz === wczoraj.toISOString().slice(0, 10)) return "Wczoraj";
  const o = opisDnia(d.klucz);
  return `${o.tyg} ${o.data}`;
}

/* ---- wspólne ----------------------------------------------------------- */

function Naglowek({ start }: { start: string }) {
  return (
    <div className="st-naglowek">
      <h1 className="p-n">Wyniki</h1>
      <p>
        <span>Każdy typ zostaje w historii – także te, które nie weszły.</span> <span>Liczymy od {start} i niczego nie poprawiamy wstecz.</span>
      </p>
    </div>
  );
}

function FiltrProduktu({ filtr, setFiltr, liczby }: { filtr: Filtr; setFiltr: (f: Filtr) => void; liczby: Record<Filtr, number> }) {
  const id = useId();
  return (
    <LayoutGroup id={id}>
      <div className="mz-seg sk-filtr" role="radiogroup" aria-label="Rodzaj typów">
        {FILTRY.filter(([k]) => k === "wszystko" || liczby[k] > 0).map(([k, nazwa]) => (
          <button key={k} type="button" role="radio" aria-checked={k === filtr} onClick={() => setFiltr(k)}>
            {k === filtr && <motion.span layoutId="sk-filtr-tlo" className="mz-seg-tlo" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
            <span className="mz-seg-tresc">
              {nazwa} <small>{liczby[k]}</small>
            </span>
          </button>
        ))}
      </div>
    </LayoutGroup>
  );
}

/* wynik zbiorczy: jedna duża liczba + zdanie, pod nią produkty i 7 dni */
function Wynik({ dni, wszystkieDni, filtr, start }: { dni: DzienWynikow[]; wszystkieDni: DzienWynikow[]; filtr: Filtr; start: string }) {
  const caly = licz(dni.flatMap((d) => d.typy));
  const tydzien = licz(dni.slice(0, 7).flatMap((d) => d.typy));
  const produkty = (["druzyny", "zawodnicy", "drabinki"] as Produkt[])
    .map((prod) => ({ prod, ...licz(wszystkieDni.flatMap((d) => d.typy.filter((t) => t.produkt === prod))) }))
    .filter((x) => x.n > 0);
  const nazwy: Record<Produkt, string> = { druzyny: "Drużyny", zawodnicy: "Zawodnicy", drabinki: "Drabinki" };
  return (
    <section className="sk-wynik" aria-label="Wynik">
      <div className="sk-wynik-glowny">
        <motion.span key={`${filtr}-${caly.p}`} className="p-n sk-wynik-proc" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
          {caly.p}%
        </motion.span>
        <div className="sk-wynik-opis">
          <b>
            {caly.ok} z {caly.n} {odmTyp(caly.n)} weszło
          </b>
          <span>
            od {start}
            {caly.zwrot > 0 && ` · do tego ${caly.zwrot} ${odmien(caly.zwrot, "zwrot", "zwroty", "zwrotów")} (stawka wraca)`}
          </span>
        </div>
      </div>
      <div className="sk-wynik-boki">
        <div className="sk-kafel">
          <small>Ostatnie 7 dni</small>
          <b className="p-n">{tydzien.p}%</b>
          <span>
            {tydzien.ok} z {tydzien.n}
          </span>
        </div>
        {filtr === "wszystko" &&
          produkty.map((x) => (
            <div key={x.prod} className="sk-kafel">
              <small>{nazwy[x.prod]}</small>
              <b className="p-n">{x.p}%</b>
              <span>
                {x.ok} z {x.n}
              </span>
            </div>
          ))}
      </div>
    </section>
  );
}

/* jeden rozliczony typ: znak wyniku, zakład na pierwszym planie, ile było */
function WierszWyniku({ t }: { t: TypWyniku }) {
  const znak = t.wynik === "wygrany" ? "✓" : t.wynik === "przegrany" ? "✕" : "↺";
  return (
    <div className="sk-typ" data-wynik={t.wynik}>
      <span className="sk-znak" aria-label={t.wynik === "wygrany" ? "weszło" : t.wynik === "przegrany" ? "nie weszło" : "zwrot"}>
        {znak}
      </span>
      <span className="sk-typ-tekst">
        <small>{t.kto}</small>
        <span>
          <b>{t.rynek.replace(/\s*drużyny\s*/, " ").trim()}</b>
          {t.strona && (
            <>
              {" "}
              {t.strona === "ponizej" ? "poniżej" : "powyżej"} <strong>{fmtLinia(t.linia)}</strong>
            </>
          )}
        </span>
      </span>
      <span className="sk-typ-bylo">
        {t.wynik === "zwrot" ? (
          <small>zwrot</small>
        ) : (
          <>
            <small>było</small>
            <b>{t.faktyczna ?? "–"}</b>
          </>
        )}
      </span>
      <span className="sk-typ-kurs">{kursTxt(t.kurs)}</span>
      {t.szczeble && t.szczeble.length > 1 && (
        <span className="sk-szczeble" aria-label="Wszystkie szczeble drabinki">
          <small>drabinka</small>
          {t.szczeble.map((s) => (
            <span key={s.linia} className="sk-szczebel" data-wynik={s.wynik} data-polecany={s.polecany || undefined} title={s.polecany ? "nasz typ – ten szczebel liczy się do wyniku" : "dalszy szczebel – nie liczy się do wyniku"}>
              <b>{fmtLinia(s.linia)}</b>
              <i aria-label={s.wynik === "wygrany" ? "weszło" : s.wynik === "przegrany" ? "nie weszło" : "zwrot"}>{s.wynik === "wygrany" ? "✓" : s.wynik === "przegrany" ? "✕" : "↺"}</i>
              <span>{kursTxt(s.kurs)}</span>
            </span>
          ))}
        </span>
      )}
    </div>
  );
}

function PanelDnia({ d, poprzedni, nastepny }: { d: DzienWynikow; poprzedni?: () => void; nastepny?: () => void }) {
  const dzis = useDzis();
  const [wszystkie, setWszystkie] = useState(false);
  const l = licz(d.typy);
  const pokaz = wszystkie ? d.typy : d.typy.slice(0, 10);
  const proba = l.n < MALA_PROBA;
  return (
    <section className="sk-panel" aria-label={`Wyniki: ${etykieta(d, dzis)}`}>
      <header className="sk-panel-glowa">
        {(poprzedni || nastepny) && (
          <span className="sk-panel-strzalki">
            <button type="button" aria-label="Poprzedni dzień" disabled={!poprzedni} onClick={poprzedni}>
              ‹
            </button>
            <button type="button" aria-label="Następny dzień" disabled={!nastepny} onClick={nastepny}>
              ›
            </button>
          </span>
        )}
        <b className="p-n">{etykieta(d, dzis)}</b>
        <span>
          {l.ok} z {l.n} weszło{l.zwrot > 0 && ` · ${l.zwrot} ${odmien(l.zwrot, "zwrot", "zwroty", "zwrotów")}`}
        </span>
        {proba ? <em className="sk-proba">mała próba</em> : <em data-dobry={l.p >= 55 || undefined}>{l.p}%</em>}
      </header>
      <div className="sk-lista">
        {pokaz.map((t, i) => (
          <WierszWyniku key={i} t={t} />
        ))}
      </div>
      {d.typy.length > 10 && !wszystkie && (
        <button type="button" className="f-wiecej" onClick={() => setWszystkie(true)}>
          Pokaż wszystkie {d.typy.length}
        </button>
      )}
    </section>
  );
}

/* ---- A · kalendarz ------------------------------------------------------ */

function Kalendarz({ dni, wybrany, wybierz, telefon }: { dni: DzienWynikow[]; wybrany: string; wybierz: (k: string) => void; telefon: boolean }) {
  const dzis = useDzis();
  const mapa = useMemo(() => new Map(dni.map((d) => [d.klucz, d])), [dni]);
  const miesiace = useMemo(() => [...new Set(dni.map((d) => d.klucz.slice(0, 7)))].sort(), [dni]);
  const [miesiac, setMiesiac] = useState(wybrany.slice(0, 7) || miesiace.at(-1)!);
  const m = miesiace.includes(miesiac) ? miesiac : miesiace.at(-1)!;
  const im = miesiace.indexOf(m);

  // tygodnie od poniedziałku: od pierwszego dnia miesiąca do ostatniego
  const [rok, mies] = m.split("-").map(Number);
  const pierwszy = new Date(Date.UTC(rok, mies - 1, 1, 12));
  const ostatni = new Date(Date.UTC(rok, mies, 0, 12));
  const start = new Date(pierwszy);
  start.setUTCDate(start.getUTCDate() - ((pierwszy.getUTCDay() + 6) % 7));
  const tygodnie: string[][] = [];
  for (const d = new Date(start); d <= ostatni; ) {
    const tydz: string[] = [];
    for (let i = 0; i < 7; i++, d.setUTCDate(d.getUTCDate() + 1)) tydz.push(d.toISOString().slice(0, 10));
    // tydzień bez żadnego wyniku na początku miesiąca (przed startem statystyk) pomijamy
    tygodnie.push(tydz);
  }
  const zWynikami = tygodnie.filter((t) => t.some((k) => mapa.has(k)) || t.some((k) => k >= dzis && k.slice(0, 7) === m));
  const ostatniWynik = dni[0]?.klucz ?? "";

  // strzałki na kalendarzu przesuwają wybrany dzień (tylko po dniach z wynikami)
  const posort = useMemo(() => [...dni].map((d) => d.klucz).sort(), [dni]);
  const klawisze = (e: React.KeyboardEvent) => {
    const i = posort.indexOf(wybrany);
    const krok = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key];
    if (krok === undefined || i < 0) return;
    e.preventDefault();
    const cel = new Date(`${wybrany}T12:00:00Z`);
    cel.setUTCDate(cel.getUTCDate() + krok);
    const k = cel.toISOString().slice(0, 10);
    const nast = mapa.has(k) ? k : posort[Math.min(Math.max(i + Math.sign(krok), 0), posort.length - 1)];
    wybierz(nast);
    setMiesiac(nast.slice(0, 7));
  };

  return (
    <div className="sk-kal-ramka">
      <div className="sk-kal-glowa">
        <button type="button" aria-label="Poprzedni miesiąc" disabled={im <= 0} onClick={() => setMiesiac(miesiace[im - 1])}>
          ‹
        </button>
        <b className="p-n">
          {MIESIACE[mies - 1]} {rok}
        </b>
        <button type="button" aria-label="Następny miesiąc" disabled={im >= miesiace.length - 1} onClick={() => setMiesiac(miesiace[im + 1])}>
          ›
        </button>
      </div>
      <div className="sk-kal" role="grid" aria-label={`Kalendarz wyników: ${MIESIACE[mies - 1]}`} onKeyDown={klawisze} data-z-tygodniem={!telefon || undefined}>
        {["pn", "wt", "śr", "cz", "pt", "sb", "nd"].map((t) => (
          <span key={t} className="sk-kal-tydz" role="columnheader">
            {t}
          </span>
        ))}
        {!telefon && (
          <span className="sk-kal-tydz" role="columnheader">
            tydzień
          </span>
        )}
        {zWynikami.map((tydz) => {
          const lt = licz(tydz.flatMap((k) => mapa.get(k)?.typy ?? []));
          return (
            <div key={tydz[0]} role="row" style={{ display: "contents" }}>
              {tydz.map((k) => {
                const d = mapa.get(k);
                const nr = Number(k.slice(8));
                const inny = k.slice(0, 7) !== m;
                if (!d) {
                  const przyszly = k > ostatniWynik;
                  return (
                    <span key={k} className="sk-kal-pusty" data-przyszly={przyszly || undefined} data-inny={inny || undefined} aria-hidden>
                      {nr}
                      {k === dzis && <i className="sk-kal-dzis" />}
                    </span>
                  );
                }
                const l = licz(d.typy);
                const poziom = poziomDnia(l);
                return (
                  <button
                    key={k}
                    type="button"
                    role="gridcell"
                    className="sk-kal-dzien"
                    aria-selected={k === wybrany}
                    aria-label={`${etykieta(d, dzis)}: ${l.ok} z ${l.n} weszło`}
                    tabIndex={k === wybrany ? 0 : -1}
                    data-inny={inny || undefined}
                    onClick={() => wybierz(k)}
                    data-poziom={poziom}
                  >
                    <span className="sk-kal-nr">
                      {nr}
                      {k === dzis && <i className="sk-kal-dzis" title="dziś" />}
                    </span>
                    {poziom === "proba" ? (
                      <b className="sk-kal-proba">
                        {l.ok} z {l.n}
                      </b>
                    ) : (
                      <>
                        <b>{l.p}%</b>
                        <small>
                          {l.ok}/{l.n}
                        </small>
                      </>
                    )}
                  </button>
                );
              })}
              {!telefon && (
                <span className="sk-kal-tydzien" data-poziom={lt.n ? poziomDnia(lt) : "brak"}>
                  {lt.n ? (
                    <>
                      <b>{lt.p}%</b>
                      <small>
                        {lt.ok}/{lt.n}
                      </small>
                    </>
                  ) : (
                    <small>–</small>
                  )}
                </span>
              )}
            </div>
          );
        })}
      </div>
      <p className="sk-kal-legenda">
        <span>
          <i data-poziom="mocny" /> 65% i więcej
        </span>
        <span>
          <i data-poziom="sredni" /> 55–64%
        </span>
        <span>
          <i data-poziom="slaby" /> poniżej 55%
        </span>
        <span>„2 z 2” – za mało typów, żeby liczyć procent</span>
      </p>
    </div>
  );
}

/* ---- C · wykres ------------------------------------------------------- */

function Wykres({ dni, wybrany, wybierz, srednia }: { dni: DzienWynikow[]; wybrany: string; wybierz: (k: string) => void; srednia: number }) {
  const os = [...dni].sort((a, b) => a.klucz.localeCompare(b.klucz));
  return (
    <div className="sk-wykres" aria-label="Trafność dzień po dniu">
      <span className="sk-wykres-srednia" style={{ bottom: `${srednia}%` }}>
        <small>średnio {srednia}%</small>
      </span>
      <div className="sk-wykres-slupki">
        {os.map((d, i) => {
          const l = licz(d.typy);
          const o = opisDnia(d.klucz);
          return (
            <button key={d.klucz} type="button" className="sk-slup" aria-pressed={d.klucz === wybrany} onClick={() => wybierz(d.klucz)} aria-label={`${o.tyg} ${o.data}: ${l.ok} z ${l.n} weszło`}>
              <span className="sk-slup-tor">
                <motion.i
                  initial={{ scaleY: 0 }}
                  animate={{ scaleY: 1 }}
                  transition={{ duration: 0.45, delay: i * 0.025, ease: [0.22, 1, 0.36, 1] }}
                  style={{ height: `${Math.max(l.p, 3)}%` }}
                  data-dobry={l.p >= srednia || undefined}
                />
              </span>
              <small>{o.nr}</small>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ---- B · lista dni --------------------------------------------------- */

function ListaDni({ dni }: { dni: DzienWynikow[] }) {
  const dzis = useDzis();
  const [otwarty, setOtwarty] = useState(dni[0]?.klucz ?? "");
  const [ile, setIle] = useState(7);
  return (
    <div className="sk-dni">
      {dni.slice(0, ile).map((d) => {
        const l = licz(d.typy);
        const on = d.klucz === otwarty;
        return (
          <section key={d.klucz} className="sk-dzien" data-otwarty={on || undefined}>
            <button type="button" className="sk-dzien-glowa" aria-expanded={on} onClick={() => setOtwarty(on ? "" : d.klucz)}>
              <b className="p-n">{etykieta(d, dzis)}</b>
              <span className="sk-dzien-pasek" aria-hidden>
                <i style={{ width: `${l.p}%` }} />
              </span>
              <span className="sk-dzien-liczby">
                {l.ok} z {l.n}
              </span>
              <em data-dobry={l.p >= 55 || undefined}>{l.p}%</em>
            </button>
            <AnimatePresence initial={false}>
              {on && (
                <motion.div
                  className="sk-dzien-tresc"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
                >
                  <div className="sk-lista">
                    {d.typy.map((t, i) => (
                      <WierszWyniku key={i} t={t} />
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </section>
        );
      })}
      {dni.length > ile && (
        <button type="button" className="f-wiecej" onClick={() => setIle((n) => n + 7)}>
          Pokaż starsze dni
        </button>
      )}
    </div>
  );
}

/* ---- strona ------------------------------------------------------------ */

export function StronaSkutecznosci({
  wariant,
  dane,
  telefon,
  naglowek,
  dzienStart,
}: {
  wariant: string;
  dane: DaneSkutecznosci;
  telefon: boolean;
  /** admin (5.6): własny nagłówek z przełącznikiem Wyniki | Kontrola */
  naglowek?: React.ReactNode;
  /** dzień otwarty na start (`?dzien=RRRR-MM-DD`, np. z 404 rozegranego meczu) */
  dzienStart?: string;
}) {
  const [filtr, setFiltr] = useState<Filtr>("wszystko");
  const dni = useMemo(
    () =>
      dane.dni
        .map((d) => ({ ...d, typy: filtr === "wszystko" ? d.typy : d.typy.filter((t) => t.produkt === filtr) }))
        .filter((d) => d.typy.length),
    [dane, filtr],
  );
  const liczby = useMemo(() => {
    const w = { wszystko: 0, zawodnicy: 0, druzyny: 0, drabinki: 0 } as Record<Filtr, number>;
    for (const d of dane.dni)
      for (const t of d.typy) {
        // jak w wyniku obok: liczą się rozstrzygnięte, bez zwrotów
        if (t.wynik === "zwrot") continue;
        w.wszystko++;
        w[t.produkt]++;
      }
    return w;
  }, [dane]);
  const [dzien, setDzien] = useState(dzienStart ?? "");
  const wybrany = dni.find((d) => d.klucz === dzien) ?? dni[0];
  const srednia = licz(dni.flatMap((d) => d.typy)).p;
  // dni idą od najnowszego: „poprzedni” = starszy = dalej w tablicy
  const iDnia = wybrany ? dni.indexOf(wybrany) : -1;

  return (
    <main className="st-strona sk">
      {naglowek ?? <Naglowek start={dane.start} />}
      <FiltrProduktu filtr={filtr} setFiltr={setFiltr} liczby={liczby} />
      <Wynik dni={dni} wszystkieDni={dane.dni} filtr={filtr} start={dane.start} />
      {wariant === "b" ? (
        <>
          <h2 className="st-h2 p-n">Dzień po dniu</h2>
          <ListaDni key={filtr} dni={dni} />
        </>
      ) : (
        <>
          <h2 className="st-h2 p-n">{wariant === "c" ? "Trafność dzień po dniu" : "Dzień po dniu"}</h2>
          {wariant === "c" ? (
            <Wykres dni={dni} wybrany={wybrany?.klucz ?? ""} wybierz={setDzien} srednia={srednia} />
          ) : (
            <Kalendarz dni={dni} wybrany={wybrany?.klucz ?? ""} wybierz={setDzien} telefon={telefon} />
          )}
          <AnimatePresence mode="wait">
            {wybrany && (
              <motion.div key={`${filtr}-${wybrany.klucz}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
                <PanelDnia
                  d={wybrany}
                  poprzedni={iDnia < dni.length - 1 ? () => setDzien(dni[iDnia + 1].klucz) : undefined}
                  nastepny={iDnia > 0 ? () => setDzien(dni[iDnia - 1].klucz) : undefined}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </>
      )}
    </main>
  );
}
