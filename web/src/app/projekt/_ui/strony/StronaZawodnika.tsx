"use client";

import { Lnk } from "../linki";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useId, useMemo, useState } from "react";

import { fmtLinia } from "@/lib/format";

import type { RynekZawodnika, ZawodnikStrony } from "../../_dane/zawodnik";
import { Logo } from "../atomy2/podstawowe";
import { KartaA } from "../elementy/karta";
import { IkonaRynku } from "../elementy/ikonyRynkow";
import { Herb } from "../Herb";

/*
 * Etap 5.7 – strona zawodnika. Wejście: wyszukiwarka, strona meczu, karta
 * typu (bez pozycji w menu). Strona meczu to jeden rynek × wszyscy
 * zawodnicy; tu odwrotnie: jeden zawodnik × wszystkie jego rynki.
 * Do tego jego typy na liście i historia naszych typów na niego.
 * Bez propozycji ponad to, co już jest na liście.
 */

type Okno = 5 | 10;
const kursTxt = (k: number) => k.toFixed(2).replace(".", ",");
const srTxt = (x: number | null) => (x === null ? "–" : x.toFixed(1).replace(".", ","));

function pokrycie(h: RynekZawodnika["historia"], linia: number, okno: Okno) {
  const mecze = h.v.slice(0, okno).map((v, i) => ({ v, min: h.min[i] ?? 90, rywal: h.rywale[i] ?? "", data: h.daty[i] ?? "" }));
  const zagrane = mecze.filter((m) => m.min > 0);
  const weszlo = zagrane.filter((m) => m.v > linia).length;
  const srednia = zagrane.length ? zagrane.reduce((a, m) => a + m.v, 0) / zagrane.length : null;
  return { mecze, weszlo, zagrane: zagrane.length, nz: mecze.length - zagrane.length, udzial: zagrane.length ? weszlo / zagrane.length : 0, srednia };
}
type Pokrycie = ReturnType<typeof pokrycie>;
const poziom = (u: number) => (u >= 0.8 ? "mocne" : u >= 0.6 ? "srednie" : "slabe");

function Koszulka() {
  return (
    <svg width="13" height="13" viewBox="0 0 14 14" aria-hidden>
      <path d="M5 2 2 3.6 3 6.4l1.2-.5V12h5.6V5.9l1.2.5 1-2.8L9 2c-.3.9-1 1.4-2 1.4S5.3 2.9 5 2Z" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  );
}

function Segment<T extends string | number>({ opcje, wartosc, zmien, etykieta }: { opcje: [T, React.ReactNode][]; wartosc: T; zmien: (v: T) => void; etykieta: string }) {
  const id = useId();
  return (
    <LayoutGroup id={id}>
      <div className="mz-seg" role="radiogroup" aria-label={etykieta}>
        {opcje.map(([v, tresc]) => (
          <button key={String(v)} type="button" role="radio" aria-checked={v === wartosc} onClick={() => zmien(v)}>
            {v === wartosc && <motion.span layoutId="zw-seg-tlo" className="mz-seg-tlo" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
            <span className="mz-seg-tresc">{tresc}</span>
          </button>
        ))}
      </div>
    </LayoutGroup>
  );
}

/* ---- nagłówek -------------------------------------------------------------- */

function Glowa({ z }: { z: ZawodnikStrony }) {
  const m = z.mecz;
  return (
    <header className="zw-glowa">
      <Lnk href={`/mecze/${m.id}`} className="mz-wroc">
        ← {m.gosp.nazwa} – {m.gosc.nazwa}
      </Lnk>
      <div className="zw-kto">
        <Herb d={z.druzyna} tryb="prawdziwy" rozmiar={52} />
        <div>
          <h1 className="p-n">{z.nazwa}</h1>
          <p>
            {z.pozycja && <span>{z.pozycja}</span>}
            <span>{z.druzyna.nazwa}</span>
            {z.xi && (
              <span className="zw-sklad">
                <Koszulka /> w przewidywanym składzie
              </span>
            )}
          </p>
        </div>
      </div>
      <Lnk href={`/mecze/${m.id}`} className="zw-mecz" aria-label={`Najbliższy mecz: ${m.gosp.nazwa} – ${m.gosc.nazwa}, ${m.dzien} ${m.godzina}`}>
        <small>Najbliższy mecz</small>
        <span className="zw-mecz-druzyny">
          <Herb d={m.gosp} tryb="prawdziwy" rozmiar={18} />
          <b>{m.gosp.nazwa}</b>
          <i>–</i>
          <b>{m.gosc.nazwa}</b>
          <Herb d={m.gosc} tryb="prawdziwy" rozmiar={18} />
        </span>
        <span className="zw-mecz-kiedy">
          {m.dzien} {m.godzina} · {m.liga}
          <em>Strona meczu →</em>
        </span>
      </Lnk>
    </header>
  );
}

/* ---- kawałki wiersza ------------------------------------------------------- */

function MiniKratki({ p, linia, okno }: { p: Pokrycie; linia: number; okno: Okno }) {
  // brakujące mecze (rynek liczony od niedawna) jako puste kratki – kolumny trzymają się w pionie
  const puste = Math.max(0, okno - p.mecze.length);
  return (
    <span className="mz-kratki" aria-label={`ostatnie mecze od najnowszego: ${p.mecze.map((m) => (m.min > 0 ? m.v : "nie zagrał")).join(", ")}`}>
      {p.mecze.map((m, i) => (
        <i key={i} data-s={m.min <= 0 ? "nz" : m.v > linia ? "ok" : "nie"} title={`${m.data} ${m.rywal}: ${m.min > 0 ? `${m.v} (${m.min}′)` : "nie zagrał"}`}>
          {m.min > 0 ? m.v : ""}
        </i>
      ))}
      {Array.from({ length: puste }, (_, i) => (
        <i key={`b${i}`} data-s="brak" title="brak danych z tego meczu" />
      ))}
    </span>
  );
}

function Linie({ r, linia, ustaw, okno }: { r: RynekZawodnika; linia: number; ustaw: (l: number) => void; okno: Okno }) {
  return (
    <span className="zw-linie" role="radiogroup" aria-label={`${r.nazwa}: linia`}>
      {r.kursy.map((k) => {
        const p = pokrycie(r.historia, k.linia, okno);
        return (
          <button key={k.linia} type="button" role="radio" aria-checked={k.linia === linia} onClick={() => ustaw(k.linia)} title={`powyżej ${fmtLinia(k.linia)}: ${p.weszlo}/${p.zagrane}, kurs ${kursTxt(k.kurs)}`}>
            {fmtLinia(k.linia)}+
          </button>
        );
      })}
    </span>
  );
}

function KursLinii({ r, linia }: { r: RynekZawodnika; linia: number }) {
  const w = r.kursy.find((x) => x.linia === linia);
  const k = w?.kurs ?? null;
  return (
    <span className="mz-kurs" data-brak={k === null || undefined}>
      <Logo nazwa={w?.bukmacher ?? "Superbet"} wysokosc={10} />
      <b>{k === null ? "–" : kursTxt(k)}</b>
    </span>
  );
}

function NaLiscie({ r }: { r: RynekZawodnika }) {
  if (!r.typ) return null;
  return (
    <Lnk href="/" className="mz-na-liscie" title={`Mamy typ: powyżej ${fmtLinia(r.typ.linia)} – zobacz na liście dnia`}>
      na liście
    </Lnk>
  );
}

/* ---- A · tabela rynków ----------------------------------------------------- */

function Weszlo({ p, klucz }: { p: Pokrycie; klucz: string }) {
  return (
    <span className="mz-weszlo" data-poziom={poziom(p.udzial)}>
      {/* nowa linia = krótki błysk liczby (ruch niesie zmianę, 2.8) */}
      <motion.b key={klucz} initial={{ opacity: 0.25, y: -4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
        {p.weszlo}/{p.zagrane}
      </motion.b>
      <small>{p.nz ? `${p.nz}× nie zagrał` : `${Math.round(p.udzial * 100)}%`}</small>
    </span>
  );
}

/** rozwinięcie wiersza: wszystkie linie naraz + dziennik meczów */
function Szczegoly({ r, linia, ustaw, okno }: { r: RynekZawodnika; linia: number; ustaw: (l: number) => void; okno: Okno }) {
  const p = pokrycie(r.historia, linia, okno);
  return (
    <div className="zw-szczegoly">
      <div>
        <h4 className="zw-h4">Wszystkie linie</h4>
        <div className="zw-linie-lista" role="radiogroup" aria-label={`${r.nazwa}: linia`}>
          {r.kursy.map((k) => {
            const pk = pokrycie(r.historia, k.linia, okno);
            return (
              <button key={k.linia} type="button" role="radio" aria-checked={k.linia === linia} onClick={() => ustaw(k.linia)} data-poziom={poziom(pk.udzial)}>
                <span className="zw-ll-linia">powyżej {fmtLinia(k.linia)}</span>
                <span className="zw-ll-pasek" aria-hidden>
                  <i style={{ width: `${Math.round(pk.udzial * 100)}%` }} />
                </span>
                <b className="zw-ll-weszlo">
                  {pk.weszlo}/{pk.zagrane}
                </b>
                <span className="zw-ll-kurs">{kursTxt(k.kurs)}</span>
              </button>
            );
          })}
        </div>
      </div>
      <div>
        <h4 className="zw-h4">Mecz po meczu</h4>
        <ol className="zw-dziennik">
          {p.mecze.map((m, i) => (
            <li key={i} data-s={m.min <= 0 ? "nz" : m.v > linia ? "ok" : "nie"}>
              <span className="zw-dz-data">{m.data}</span>
              <span className="zw-dz-rywal">{m.rywal}</span>
              <span className="zw-dz-min">{m.min > 0 ? `${m.min}′` : "nie zagrał"}</span>
              <b className="zw-dz-v">{m.min > 0 ? m.v : "–"}</b>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

function WierszRynku({ r, okno, telefon }: { r: RynekZawodnika; okno: Okno; telefon: boolean }) {
  const [linia, setLinia] = useState(r.liniaStart);
  const [otwarty, setOtwarty] = useState(false);
  const p = pokrycie(r.historia, linia, okno);
  const idSz = useId();
  return (
    <div className="zw-blok" data-otwarty={otwarty || undefined}>
      <div className="zw-wiersz" role="row" data-typ={r.typ ? "" : undefined}>
        <span className="zw-rynek" role="cell">
          <button type="button" className="zw-rozwin" aria-expanded={otwarty} aria-controls={idSz} onClick={() => setOtwarty((o) => !o)}>
            <span className="zw-ikona">
              <IkonaRynku rynek={r.nazwa} rozmiar={16} />
            </span>
            <b>{r.nazwa}</b>
            <svg className="zw-strzalka" width="12" height="12" viewBox="0 0 12 12" aria-hidden>
              <path d="M3 4.5 6 7.5 9 4.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <NaLiscie r={r} />
        </span>
        <span role="cell" className="zw-linie-kom">
          <Linie r={r} linia={linia} ustaw={setLinia} okno={okno} />
        </span>
        <span role="cell" className="zw-kratki-kom">
          <MiniKratki p={p} linia={linia} okno={okno} />
        </span>
        <span role="cell">
          <Weszlo p={p} klucz={`${linia}-${okno}`} />
        </span>
        {!telefon && (
          <span role="cell" className="mz-srednia">
            {srTxt(p.srednia)}
          </span>
        )}
        <span role="cell">
          <KursLinii r={r} linia={linia} />
        </span>
      </div>
      <AnimatePresence initial={false}>
        {otwarty && (
          <motion.div id={idSz} initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }} style={{ overflow: "hidden" }}>
            <Szczegoly r={r} linia={linia} ustaw={setLinia} okno={okno} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function TabelaRynkow({ z, okno, telefon }: { z: ZawodnikStrony; okno: Okno; telefon: boolean }) {
  // kolejność raz, na start: najczęściej przebijane linie na górze (bez skakania przy zmianie linii)
  const rynki = useMemo(() => [...z.rynki].sort((a, b) => Number(!!b.typ) - Number(!!a.typ) || pokrycie(b.historia, b.liniaStart, 10).udzial - pokrycie(a.historia, a.liniaStart, 10).udzial), [z]);
  return (
    <div className="zw-tabela" role="table" aria-label={`Rynki: ${z.nazwa}`}>
      {!telefon && (
        <div className="zw-wiersz zw-glowka" role="row">
          <span role="columnheader">rynek</span>
          <span role="columnheader">linia</span>
          <span role="columnheader">ostatnie mecze, od najnowszego</span>
          <span role="columnheader">weszło</span>
          <span role="columnheader">średnio</span>
          <span role="columnheader">kurs</span>
        </div>
      )}
      {rynki.map((r) => (
        <WierszRynku key={`${r.kod}-${okno}`} r={r} okno={okno} telefon={telefon} />
      ))}
    </div>
  );
}

/* ---- historia naszych typów -------------------------------------------- */

function Historia({ z }: { z: ZawodnikStrony }) {
  const ok = z.historia.filter((t) => t.wynik === "wygrany").length;
  const n = z.historia.filter((t) => t.wynik !== "zwrot").length;
  if (z.historia.length === 0) {
    return (
      <div className="d-pusty zw-pusty">
        <div className="p-n" style={{ fontSize: 17 }}>
          Jeszcze go nie typowaliśmy
        </div>
        <p>Każdy nasz typ na tego zawodnika dopisze się tu sam po ostatnim gwizdku – także te, które nie wejdą.</p>
      </div>
    );
  }
  return (
    <>
      <p className="zw-hist-wynik">
        <b>
          {ok} z {n}
        </b>{" "}
        {n === 1 ? "typu weszło" : "typów weszło"}
        {n < 5 && <span> · za mało, żeby liczyć procent</span>}
      </p>
      <div className="sk-lista zw-hist">
        {z.historia.map((t, i) => (
          <div key={i} className="sk-typ" data-wynik={t.wynik}>
            <span className="sk-znak" aria-label={t.wynik === "wygrany" ? "weszło" : t.wynik === "przegrany" ? "nie weszło" : "zwrot"}>
              {t.wynik === "wygrany" ? "✓" : t.wynik === "przegrany" ? "✕" : "↺"}
            </span>
            <span className="sk-typ-tekst">
              <small>
                {t.dzien.slice(8)}.{t.dzien.slice(5, 7)} · {t.mecz}
              </small>
              <span>
                <b>{t.rynek}</b> {t.strona === "ponizej" ? "poniżej" : "powyżej"} <strong>{fmtLinia(t.linia)}</strong>
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
          </div>
        ))}
      </div>
    </>
  );
}

/* ---- strona ---------------------------------------------------------------- */

export function StronaZawodnika({ z, telefon }: { z: ZawodnikStrony; telefon: boolean }) {
  const [okno, setOkno] = useState<Okno>(10);
  return (
    <main className="st-strona zw">
      <Glowa z={z} />

      {z.typy.length > 0 && (
        <section className="zw-sekcja" aria-labelledby="zw-lista">
          <h2 id="zw-lista" className="st-h2 p-n">
            Na liście
          </h2>
          <div className="zw-typy">
            {z.typy.map((k) => (
              <KartaA key={k.id} t={k} />
            ))}
          </div>
        </section>
      )}

      <section className="zw-sekcja" aria-labelledby="zw-rynki">
        <div className="zw-sekcja-glowa">
          <h2 id="zw-rynki" className="st-h2 p-n">
            Wszystkie rynki
          </h2>
          <Segment
            etykieta="Okno meczów"
            wartosc={okno}
            zmien={setOkno}
            opcje={[
              [10, "10 meczów"],
              [5, "5 meczów"],
            ]}
          />
        </div>
        <p className="zw-objasnienie">
          Kratka = jeden mecz, od najnowszego. Zielona – przebił linię, szara – nie, przekreślona – nie zagrał. Kliknij rynek, żeby zobaczyć wszystkie linie i mecz po meczu.
        </p>
        <TabelaRynkow z={z} okno={okno} telefon={telefon} />
        <p className="mz-przypis">Kurs: wyższy z Superbetu i Betclica (osobno pokażemy oba po zmianie w danych).</p>
      </section>

      <section className="zw-sekcja" aria-labelledby="zw-historia">
        <h2 id="zw-historia" className="st-h2 p-n">
          Nasze typy na niego
        </h2>
        <Historia z={z} />
      </section>
    </main>
  );
}
