"use client";

import { Lnk } from "../linki";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { fmtLinia } from "@/lib/format";

import type { MeczStrony, ZawodnikMeczu } from "../../_dane/mecz";
import type { DaneStron } from "../../_dane/strony";
import { Ptaszek } from "../atomy/wspolne";
import { IkonaKoszulka } from "../atomy2/filtry2";
import { Logo } from "../atomy2/podstawowe";
import { PrzewijanyRzad } from "../atomy2/PrzewijanyRzad";
import { Herb } from "../Herb";
import { silaPokrycia } from "../liniePomiar";

/*
 * Etap 5.4 – strona meczu jako narzędzie (decyzja właściciela 01.10):
 * pokrycie WSZYSTKICH zawodników z ofertą, kursy Superbet i Betclic osobno,
 * okno 5/10 meczów. Żadnych propozycji – tylko znacznik „na liście”, gdy
 * zawodnik ma nasz typ. Bez typów drużynowych (właściciel 15.10: w zakładce
 * Mecze nic drużynowego – te są w Drużynach).
 */

type Okno = 5 | 10;
type Strona = "obie" | "gosp" | "gosc";
type Sort = "pokrycie" | "kurs" | "srednia";

const SORTY: [Sort, string][] = [
  ["pokrycie", "Pokrycie"],
  ["kurs", "Najwyższy kurs"],
  ["srednia", "Średnia"],
];
const KURS_OD: [number, string][] = [
  [0, "każdy"],
  [1.3, "od 1,30"],
  [1.5, "od 1,50"],
  [2, "od 2,00"],
];

/** wyższa z dwóch cen; Betclic liczony inaczej się nie liczy (15.10: sort szedł tylko po Superbecie) */
const najlepsza = (k: { sb: number | null; bc: number | null; bcInaczej?: boolean }) => Math.max(k.sb ?? 0, k.bcInaczej ? 0 : (k.bc ?? 0));

const kursTxt = (k: number | null) => (k === null ? "–" : k.toFixed(2).replace(".", ","));
const proc = (x: number) => `${Math.round(x * 100)}%`;

/** pokrycie linii w oknie: mecze bez minut liczą się osobno („nie zagrał”) */
function pokrycie(z: ZawodnikMeczu, rynek: string, linia: number, okno: Okno) {
  const h = z.rynki[rynek];
  if (!h) return null;
  const mecze = h.v.slice(0, okno).map((v, i) => ({ v, min: h.min[i] ?? 90, rywal: h.rywale[i] ?? "", data: h.daty[i] ?? "" }));
  const zagrane = mecze.filter((m) => m.min > 0);
  const weszlo = zagrane.filter((m) => m.v > linia).length;
  const srednia = zagrane.length ? zagrane.reduce((a, m) => a + m.v, 0) / zagrane.length : null;
  return { mecze, weszlo, zagrane: zagrane.length, nz: mecze.length - zagrane.length, udzial: zagrane.length ? weszlo / zagrane.length : 0, srednia };
}

function poziom(u: number) {
  return u >= 0.8 ? "mocne" : u >= 0.6 ? "srednie" : "slabe";
}

/* ---- nagłówek meczu ---------------------------------------------------- */

function GlowaMeczu({ m }: { m: MeczStrony }) {
  return (
    <header className="mz-glowa">
      <Lnk href="/mecze" className="mz-wroc">← Mecze</Lnk>
      <div className="mz-meta">
        {m.liga} · {m.dzien} {m.godzina}
      </div>
      <div className="mz-druzyny">
        <span className="mz-d">
          <Herb d={m.gosp} tryb="prawdziwy" rozmiar={44} />
          <b className="p-n">{m.gosp.nazwa}</b>
        </span>
        <span className="mz-godz p-n">{m.godzina}</span>
        <span className="mz-d mz-d-prawa">
          <b className="p-n">{m.gosc.nazwa}</b>
          <Herb d={m.gosc} tryb="prawdziwy" rozmiar={44} />
        </span>
      </div>
      <p className="mz-info">
        {m.sedzia && <span>Sędzia: {m.sedzia}</span>}
        <span>{m.sklady ? "Składy ogłoszone" : "Składy ok. godzinę przed meczem"}</span>
      </p>
    </header>
  );
}

/* ---- pasek narzędzi ---------------------------------------------------- */

function Segment<T extends string | number>({
  opcje,
  wartosc,
  zmien,
  etykieta,
  podpisy,
}: {
  opcje: [T, React.ReactNode][];
  wartosc: T;
  zmien: (v: T) => void;
  etykieta: string;
  /** nazwy dla czytników ekranu, gdy na telefonie zostaje sam herb */
  podpisy?: Record<string, string>;
}) {
  const id = useId();
  return (
    <LayoutGroup id={id}>
      <div className="mz-seg" role="radiogroup" aria-label={etykieta}>
        {opcje.map(([v, tresc]) => (
          <button key={String(v)} type="button" role="radio" aria-checked={v === wartosc} aria-label={typeof tresc === "string" ? undefined : String(v) === "gosp" || String(v) === "gosc" ? podpisy?.[String(v)] : undefined} onClick={() => zmien(v)}>
            {v === wartosc && <motion.span layoutId="mz-seg-tlo" className="mz-seg-tlo" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
            <span className="mz-seg-tresc">{tresc}</span>
          </button>
        ))}
      </div>
    </LayoutGroup>
  );
}

/* menu z jednym wyborem – ten sam guzik i dymek co „Sortuj” na stronie głównej */
export function MenuWyboru<T extends string | number>({
  etykieta,
  ikona,
  opcje,
  wartosc,
  zmien,
  aktywny,
}: {
  etykieta: string;
  ikona: React.ReactNode;
  opcje: [T, string][];
  wartosc: T;
  zmien: (v: T) => void;
  aktywny?: boolean;
}) {
  const [otwarte, setOtwarte] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!otwarte) return;
    const klik = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOtwarte(false);
    };
    const klaw = (e: KeyboardEvent) => e.key === "Escape" && setOtwarte(false);
    document.addEventListener("mousedown", klik);
    document.addEventListener("keydown", klaw);
    return () => {
      document.removeEventListener("mousedown", klik);
      document.removeEventListener("keydown", klaw);
    };
  }, [otwarte]);
  const nazwa = opcje.find(([v]) => v === wartosc)?.[1];
  return (
    <span ref={ref} className="mz-menu">
      <button type="button" className="e-menu-guzik d-dotyk" aria-haspopup="menu" aria-expanded={otwarte} aria-label={`${etykieta}: ${nazwa}`} data-aktywny={aktywny ? "true" : undefined} onClick={() => setOtwarte((o) => !o)}>
        {ikona}
        <span className="e-etykieta-sortu">
          <span className="mz-menu-co">{etykieta}:</span> {nazwa}
        </span>
      </button>
      <AnimatePresence>
        {otwarte && (
          <motion.div className="d-menu" role="menu" initial={{ opacity: 0, y: -4, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -4, scale: 0.98 }} transition={{ duration: 0.14 }}>
            {opcje.map(([v, e]) => (
              <button
                key={String(v)}
                type="button"
                role="menuitemradio"
                aria-checked={v === wartosc}
                onClick={() => {
                  zmien(v);
                  setOtwarte(false);
                }}
              >
                {e}
                {v === wartosc && <Ptaszek rozmiar={11} />}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </span>
  );
}

export const IkonaSortu = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
    <path d="M4 2.5v9M1.8 9.3 4 11.5l2.2-2.2M10 11.5v-9M7.8 4.7 10 2.5l2.2 2.2" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
/* kurs jak kafelek: ramka z liczbą */
const IkonaKursu = () => (
  <svg width="16" height="14" viewBox="0 0 16 14" aria-hidden>
    <rect x="1" y="2" width="14" height="10" rx="2.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
    <path d="M5 9.5V7.2M8 9.5V5M11 9.5V6.2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);

/* ---- komórki --------------------------------------------------------- */

function MiniKratki({ p, linia }: { p: NonNullable<ReturnType<typeof pokrycie>>; linia: number }) {
  return (
    <span className="mz-kratki" aria-label={`ostatnie mecze od najnowszego: ${p.mecze.map((m) => (m.min > 0 ? m.v : "nie zagrał")).join(", ")}`}>
      {p.mecze.map((m, i) => (
        <i key={i} data-s={m.min <= 0 ? "nz" : m.v > linia ? "ok" : "nie"} title={`${m.data} ${m.rywal}: ${m.min > 0 ? `${m.v} (${m.min}′)` : "nie zagrał"}`}>
          {m.min > 0 ? m.v : ""}
        </i>
      ))}
    </span>
  );
}

export function Weszlo({ p }: { p: { weszlo: number; zagrane: number; nz: number; udzial: number } }) {
  return (
    <span className="mz-weszlo" data-poziom={poziom(p.udzial)}>
      <b>
        {p.weszlo}/{p.zagrane}
      </b>
      <small>{p.nz ? `${p.nz}× nie zagrał` : proc(p.udzial)}</small>
    </span>
  );
}

export function Kurs({ k, bukmacher, lepszy, uwaga }: { k: number | null; bukmacher: string; lepszy: boolean; uwaga?: string }) {
  return (
    <span className="mz-kurs" data-lepszy={lepszy || undefined} data-brak={k === null || undefined} title={uwaga} aria-label={uwaga ? `${bukmacher}: ${uwaga}` : undefined}>
      <Logo nazwa={bukmacher} wysokosc={10} />
      <b>{kursTxt(k)}</b>
    </span>
  );
}

function Kto({ z, m, rynek }: { z: ZawodnikMeczu; m: MeczStrony; rynek: string }) {
  const typ = z.naLiscie[rynek];
  return (
    <span className="mz-kto">
      <Herb d={z.strona === "gosp" ? m.gosp : m.gosc} tryb="prawdziwy" rozmiar={18} />
      <span className="mz-kto-tekst">
        <Lnk href={`/zawodnik/${z.id}`} className="mz-kto-nazwa">
          <b>{z.nazwa}</b>
        </Lnk>
        <small>
          {z.pozycja}
          {z.xi && " · w składzie"}
        </small>
      </span>
      {typ && (
        <Lnk href="/" className="mz-na-liscie" title={`Mamy typ: powyżej ${fmtLinia(typ.linia)} – zobacz na liście dnia`}>
          na liście
        </Lnk>
      )}
    </span>
  );
}

/* ---- A · tabela z wyborem linii --------------------------------------- */

function TabelaA({
  m,
  rynek,
  okno,
  strona,
  telefon,
  l,
  sort,
  setSort,
  kursOd,
  tylkoXi,
}: {
  m: MeczStrony;
  rynek: string;
  okno: Okno;
  strona: Strona;
  telefon: boolean;
  l: number;
  sort: Sort;
  setSort: (s: Sort) => void;
  kursOd: number;
  tylkoXi: boolean;
}) {
  const r = m.rynki.find((x) => x.kod === rynek)!;

  const wszystkie = useMemo(
    () =>
      m.zawodnicy
        .filter((z) => z.rynki[rynek] && (strona === "obie" || z.strona === strona) && (!tylkoXi || z.xi))
        .map((z) => ({ z, p: pokrycie(z, rynek, l, okno)!, k: z.kursy[rynek]?.[String(l)] ?? { sb: null, bc: null } })),
    [m, rynek, l, okno, strona, tylkoXi],
  );
  const wiersze = useMemo(() => {
    const w = kursOd ? wszystkie.filter((x) => najlepsza(x.k) >= kursOd) : [...wszystkie];
    w.sort((a, b) =>
      sort === "kurs"
        ? najlepsza(b.k) - najlepsza(a.k) || b.p.udzial - a.p.udzial
        : sort === "srednia"
          ? (b.p.srednia ?? -1) - (a.p.srednia ?? -1) || b.p.udzial - a.p.udzial
          : // z kursem przed bez kursu, potem siła dowodu (7/7 nad 9/10, 2/2 przy ośmiu meczach bez gry nisko)
            Number(najlepsza(b.k) > 0) - Number(najlepsza(a.k) > 0) || silaPokrycia(b.p) - silaPokrycia(a.p) || najlepsza(b.k) - najlepsza(a.k),
    );
    return w;
  }, [wszystkie, kursOd, sort]);

  if (!wiersze.length) {
    return (
      <div className="d-pusty">
        <div className="p-n" style={{ fontSize: 17 }}>
          Nikt nie ma tu kursu {KURS_OD.find(([k]) => k === kursOd)?.[1]}
        </div>
        <p>Spróbuj niższej linii albo niższego progu kursu.</p>
      </div>
    );
  }

  return (
    <>
      {kursOd > 0 && wiersze.length < wszystkie.length && (
        <p className="mz-ukryci">
          {wiersze.length} z {wszystkie.length} zawodników ma kurs {KURS_OD.find(([k]) => k === kursOd)?.[1]}
        </p>
      )}
      <div className="mz-tabela" role="table" aria-label={`Pokrycie: ${r.nazwa} powyżej ${fmtLinia(l)}`}>
        {!telefon && (
          <div className="mz-tr mz-th" role="row">
            <span role="columnheader">Zawodnik</span>
            <span role="columnheader">Ostatnie {okno} meczów, od najnowszego</span>
            <button type="button" role="columnheader" aria-sort={sort === "pokrycie" ? "descending" : "none"} onClick={() => setSort("pokrycie")}>
              Weszło {sort === "pokrycie" && "↓"}
            </button>
            <button type="button" role="columnheader" aria-sort={sort === "srednia" ? "descending" : "none"} onClick={() => setSort("srednia")}>
              Średnio {sort === "srednia" && "↓"}
            </button>
            <button type="button" role="columnheader" aria-sort={sort === "kurs" ? "descending" : "none"} onClick={() => setSort("kurs")}>
              Kursy {sort === "kurs" && "↓"}
            </button>
          </div>
        )}
        <AnimatePresence initial={false}>
          {wiersze.map(({ z, p, k }) => {
            const lepszySb = k.sb !== null && (k.bc === null || k.bcInaczej || k.sb >= k.bc);
            return (
              <motion.div
                key={z.id}
                layout="position"
                className="mz-tr"
                role="row"
                data-bez-kursu={k.sb === null && k.bc === null ? "" : undefined}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ layout: { type: "spring", stiffness: 420, damping: 38 }, opacity: { duration: 0.15 } }}
              >
                <span role="cell">
                  <Kto z={z} m={m} rynek={rynek} />
                </span>
                <span role="cell">
                  <MiniKratki p={p} linia={l} />
                </span>
                <span role="cell">
                  <Weszlo p={p} />
                </span>
                <span role="cell" className="mz-srednia">
                  {p.srednia === null ? "–" : p.srednia.toFixed(1).replace(".", ",")}
                </span>
                <span role="cell" className="mz-kursy">
                  <Kurs k={k.sb} bukmacher="Superbet" lepszy={lepszySb} />
                  <Kurs k={k.bcInaczej ? null : k.bc} bukmacher="Betclic" lepszy={!lepszySb && k.bc !== null && !k.bcInaczej} uwaga={k.bcInaczej ? "Betclic liczy tę statystykę inaczej – ceny nie porównujemy" : undefined} />
                </span>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </>
  );
}

/* ---- B · siatka wszystkich linii --------------------------------------- */

function SiatkaB({ m, rynek, okno, strona }: { m: MeczStrony; rynek: string; okno: Okno; strona: Strona }) {
  const r = m.rynki.find((x) => x.kod === rynek)!;
  const linie = r.linie.slice(0, 5);
  const [sortLinia, setSortLinia] = useState<number | null>(null);
  const ls = sortLinia !== null && linie.includes(sortLinia) ? sortLinia : linie[0];

  const wiersze = useMemo(() => {
    const w = m.zawodnicy
      .filter((z) => z.rynki[rynek] && (strona === "obie" || z.strona === strona))
      .map((z) => ({ z, komorki: linie.map((l) => ({ l, p: pokrycie(z, rynek, l, okno)!, k: z.kursy[rynek]?.[String(l)] ?? null })) }));
    const i = linie.indexOf(ls);
    w.sort((a, b) => b.komorki[i].p.udzial - a.komorki[i].p.udzial || b.komorki[i].p.zagrane - a.komorki[i].p.zagrane);
    return w;
  }, [m, rynek, okno, strona, linie, ls]);

  return (
    <div className="mz-siatka-ramka">
      <div className="mz-siatka" role="table" style={{ "--linie": linie.length } as React.CSSProperties}>
        <div className="mz-sr mz-sh" role="row">
          <span role="columnheader">Zawodnik</span>
          {linie.map((l) => (
            <button key={l} type="button" role="columnheader" aria-sort={l === ls ? "descending" : "none"} onClick={() => setSortLinia(l)}>
              {fmtLinia(l)}+{l === ls && " ↓"}
            </button>
          ))}
        </div>
        <AnimatePresence initial={false}>
          {wiersze.map(({ z, komorki }) => (
            <motion.div key={z.id} layout="position" className="mz-sr" role="row" transition={{ layout: { type: "spring", stiffness: 420, damping: 38 } }}>
              <span role="cell" className="mz-sr-kto">
                <Kto z={z} m={m} rynek={rynek} />
              </span>
              {komorki.map(({ l, p, k }) => (
                <span key={l} role="cell" className="mz-komorka" data-poziom={k ? poziom(p.udzial) : "brak"} style={{ "--udzial": p.udzial } as React.CSSProperties}>
                  <b>
                    {p.weszlo}/{p.zagrane}
                  </b>
                  <small>{k ? `${kursTxt(k.sb)}${k.bc !== null ? ` · ${kursTxt(k.bc)}` : ""}` : "bez kursu"}</small>
                </span>
              ))}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}

/* ---- strona ----------------------------------------------------------- */

export function StronaMeczu({ wariant, m, telefon, start }: { wariant: string; m: MeczStrony; dane: DaneStron; telefon: boolean; start?: { rynek?: string; linia?: string } }) {
  // wejście z „Najlepszych linii”: od razu ten rynek i ta linia
  const [rynek, setRynek] = useState(m.rynki.some((x) => x.kod === start?.rynek) ? start!.rynek! : (m.rynki[0]?.kod ?? ""));
  const [sort, setSort] = useState<Sort>("pokrycie");
  const [kursOd, setKursOd] = useState(0);
  const [tylkoXi, setTylkoXi] = useState(false);
  const [okno, setOkno] = useState<Okno>(10);
  const [strona, setStrona] = useState<Strona>("obie");
  const idRynkow = useId();
  const r = m.rynki.find((x) => x.kod === rynek) ?? m.rynki[0];
  const [linia, setLinia] = useState(start?.linia && Number.isFinite(Number(start.linia)) ? Number(start.linia) : 0.5);
  const l = r?.linie.includes(linia) ? linia : r?.linie.includes(0.5) ? 0.5 : (r?.linie[0] ?? 0.5);

  return (
    <main className="st-strona mz">
      <GlowaMeczu m={m} />

      <section className="mz-sekcja" aria-labelledby="mz-pokrycie">
        <div className="st-h2-z-opisem">
          <h2 id="mz-pokrycie" className="st-h2 p-n">
            Pokrycie zawodników
          </h2>
          <p>Ile razy zawodnik przebił linię w ostatnich meczach. To statystyka, nie nasz typ – decyzja należy do Ciebie.</p>
        </div>

        <div className="mz-narzedzia">
          <LayoutGroup id={idRynkow}>
            <PrzewijanyRzad className="f-rynki" role="tablist" ariaLabel="Rynek">
              {m.rynki.map((x) => (
                <button key={x.kod} type="button" role="tab" aria-selected={x.kod === r.kod} className="f-rynek" onClick={() => setRynek(x.kod)}>
                  {x.nazwa}
                  <sup>{x.ile}</sup>
                  {x.kod === r.kod && <motion.span layoutId="mz-kreska-rynku" className="a-podkreslenie" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
                </button>
              ))}
            </PrzewijanyRzad>
          </LayoutGroup>
          <div className="mz-przelaczniki">
            <Segment
              etykieta="Okno"
              wartosc={okno}
              zmien={setOkno}
              opcje={[
                [10, "10 meczów"],
                [5, "5 meczów"],
              ]}
            />
            <Segment
              etykieta="Drużyna"
              podpisy={{ gosp: m.gosp.nazwa, gosc: m.gosc.nazwa }}
              wartosc={strona}
              zmien={setStrona}
              opcje={[
                ["obie", "Obie"],
                ["gosp", <><Herb key="g" d={m.gosp} tryb="prawdziwy" rozmiar={14} /> <span className="mz-seg-nazwa">{m.gosp.nazwa}</span></>],
                ["gosc", <><Herb key="h" d={m.gosc} tryb="prawdziwy" rozmiar={14} /> <span className="mz-seg-nazwa">{m.gosc.nazwa}</span></>],
              ]}
            />
          </div>
          {wariant !== "b" && r && (
            <div className="mz-linie-rzad">
              <div className="mz-linie" role="group" aria-label="Linia">
                <span>Linia</span>
                {r.linie.map((x) => (
                  <button key={x} type="button" aria-pressed={x === l} onClick={() => setLinia(x)}>
                    powyżej {fmtLinia(x)}
                  </button>
                ))}
              </div>
              <div className="mz-menu-rzad">
                {m.sklady && (
                  <button type="button" className="e-przelacznik d-dotyk" aria-pressed={tylkoXi} onClick={() => setTylkoXi((x) => !x)} title="Tylko zawodnicy z ogłoszonego składu">
                    <IkonaKoszulka />
                    <span className="mz-menu-etykieta">W składzie</span>
                  </button>
                )}
                <MenuWyboru etykieta="Kurs" ikona={<IkonaKursu />} opcje={KURS_OD} wartosc={kursOd} zmien={setKursOd} aktywny={kursOd > 0} />
                <MenuWyboru etykieta="Sortuj" ikona={<IkonaSortu />} opcje={SORTY} wartosc={sort} zmien={setSort} />
              </div>
            </div>
          )}
        </div>

        {r &&
          (wariant === "b" ? (
            <SiatkaB key={r.kod} m={m} rynek={r.kod} okno={okno} strona={strona} />
          ) : (
            <TabelaA key={r.kod} m={m} rynek={r.kod} okno={okno} strona={strona} telefon={telefon} l={l} sort={sort} setSort={setSort} kursOd={kursOd} tylkoXi={tylkoXi} />
          ))}
        <p className="mz-przypis">
          Pokazujemy zawodników, na których bukmacher daje kurs w tym rynku. Kratka z kreską = nie zagrał (nie liczy się do wyniku).
        </p>
      </section>

      <Lnk href="/kupony" className="mz-kupony">
        <span>
          <b>Chcesz kupon z tego meczu?</b>
          <small>Złożysz go w 10 sekund w zakładce Kupony.</small>
        </span>
        <span aria-hidden>→</span>
      </Lnk>
    </main>
  );
}
