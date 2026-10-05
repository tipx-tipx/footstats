"use client";

import { Lnk } from "../linki";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useId, useMemo, useState } from "react";

import { fmtLinia } from "@/lib/format";

import type { MeczStrony, ZawodnikMeczu } from "../../_dane/mecz";
import type { DaneStron } from "../../_dane/strony";
import { Logo } from "../atomy2/podstawowe";
import { PrzewijanyRzad } from "../atomy2/PrzewijanyRzad";
import { KartaA } from "../elementy/karta";
import { Herb } from "../Herb";
import { Pojedynek, stronyTypow } from "./StronaGlowna";

/*
 * Etap 5.4 – strona meczu jako narzędzie (decyzja właściciela 01.10):
 * pokrycie WSZYSTKICH zawodników z ofertą, kursy Superbet i Betclic osobno,
 * okno 5/10 meczów. Żadnych propozycji – tylko znacznik „na liście”, gdy
 * zawodnik ma nasz typ. Typy drużynowe: tylko te, które już są na stronie.
 */

type Okno = 5 | 10;
type Strona = "obie" | "gosp" | "gosc";

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

function Weszlo({ p }: { p: NonNullable<ReturnType<typeof pokrycie>> }) {
  return (
    <span className="mz-weszlo" data-poziom={poziom(p.udzial)}>
      <b>
        {p.weszlo}/{p.zagrane}
      </b>
      <small>{p.nz ? `${p.nz}× nie zagrał` : proc(p.udzial)}</small>
    </span>
  );
}

function Kurs({ k, bukmacher, lepszy, uwaga }: { k: number | null; bukmacher: string; lepszy: boolean; uwaga?: string }) {
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

function TabelaA({ m, rynek, okno, strona, telefon, l }: { m: MeczStrony; rynek: string; okno: Okno; strona: Strona; telefon: boolean; l: number }) {
  const r = m.rynki.find((x) => x.kod === rynek)!;
  const [sort, setSort] = useState<"pokrycie" | "kurs">("pokrycie");

  const wiersze = useMemo(() => {
    const w = m.zawodnicy
      .filter((z) => z.rynki[rynek] && (strona === "obie" || z.strona === strona))
      .map((z) => ({ z, p: pokrycie(z, rynek, l, okno)!, k: z.kursy[rynek]?.[String(l)] ?? { sb: null, bc: null } }));
    w.sort((a, b) =>
      sort === "kurs"
        ? (b.k.sb ?? 0) - (a.k.sb ?? 0)
        : b.p.udzial - a.p.udzial || b.p.zagrane - a.p.zagrane || (a.k.sb ?? 99) - (b.k.sb ?? 99),
    );
    return w;
  }, [m, rynek, l, okno, strona, sort]);

  return (
    <>
      <div className="mz-tabela" role="table" aria-label={`Pokrycie: ${r.nazwa} powyżej ${fmtLinia(l)}`}>
        {!telefon && (
          <div className="mz-tr mz-th" role="row">
            <span role="columnheader">Zawodnik</span>
            <span role="columnheader">Ostatnie {okno} meczów, od najnowszego</span>
            <button type="button" role="columnheader" aria-sort={sort === "pokrycie" ? "descending" : "none"} onClick={() => setSort("pokrycie")}>
              Weszło {sort === "pokrycie" && "↓"}
            </button>
            <span role="columnheader">Średnio</span>
            <button type="button" role="columnheader" aria-sort={sort === "kurs" ? "descending" : "none"} onClick={() => setSort("kurs")}>
              Kursy {sort === "kurs" && "↓"}
            </button>
          </div>
        )}
        <AnimatePresence initial={false}>
          {wiersze.map(({ z, p, k }) => {
            const lepszySb = k.sb !== null && (k.bc === null || k.sb >= k.bc);
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
                  <Kurs k={k.bc} bukmacher="Betclic" lepszy={!lepszySb && k.bc !== null} uwaga={k.bcInaczej ? "Betclic liczy tę statystykę inaczej – ceny nie porównujemy" : undefined} />
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

export function StronaMeczu({ wariant, m, dane, telefon }: { wariant: string; m: MeczStrony; dane: DaneStron; telefon: boolean }) {
  const [rynek, setRynek] = useState(m.rynki[0]?.kod ?? "");
  const [okno, setOkno] = useState<Okno>(10);
  const [strona, setStrona] = useState<Strona>("obie");
  const idRynkow = useId();
  const r = m.rynki.find((x) => x.kod === rynek) ?? m.rynki[0];
  const [linia, setLinia] = useState(0.5);
  const l = r?.linie.includes(linia) ? linia : r?.linie.includes(0.5) ? 0.5 : (r?.linie[0] ?? 0.5);
  const druzynowe = dane.kartyStrony.filter((k) => k.meczId === m.id && k.podmiotTyp === "druzyna");

  return (
    <main className="st-strona mz">
      <GlowaMeczu m={m} />

      {druzynowe.length > 0 && (
        <section className="mz-sekcja" aria-labelledby="mz-druzynowe">
          <h2 id="mz-druzynowe" className="st-h2 p-n">
            Typy drużynowe z tego meczu
          </h2>
          <div className="f-grupa">
            <Pojedynek k={druzynowe[0]} rynki={dane.pojedynki[m.id] ?? []} ile={druzynowe.length} strony={stronyTypow(dane.kartyStrony, m.id)} />
          </div>
          {druzynowe.map((k) => (
            <div key={k.id} className="f-karta-wiersz" data-w-grupie="" data-koniec-grupy={k === druzynowe.at(-1) ? "" : undefined}>
              <KartaA t={k} bezMeczu />
            </div>
          ))}
        </section>
      )}

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
            <div className="mz-linie" role="group" aria-label="Linia">
              <span>Linia</span>
              {r.linie.map((x) => (
                <button key={x} type="button" aria-pressed={x === l} onClick={() => setLinia(x)}>
                  powyżej {fmtLinia(x)}
                </button>
              ))}
            </div>
          )}
        </div>

        {r &&
          (wariant === "b" ? (
            <SiatkaB key={r.kod} m={m} rynek={r.kod} okno={okno} strona={strona} />
          ) : (
            <TabelaA key={r.kod} m={m} rynek={r.kod} okno={okno} strona={strona} telefon={telefon} l={l} />
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
