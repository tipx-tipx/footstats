"use client";

import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useId, useMemo, useState } from "react";

import { fmtLinia } from "@/lib/format";

import type { DzienV, TypV } from "../../_dane/przygotuj";
import { Poprzeczka } from "../Poprzeczka";

/* ======================================================================
   2.3 HISTORIA vs LINIA
   ====================================================================== */

const trafil = (v: number, linia: number, strona: string) => (strona === "ponizej" ? v < linia : v > linia);

function Slupki({ t }: { t: TypV }) {
  const W = 300;
  const H = 70;
  const dol = 50;
  const max = Math.max(t.linia + 1, ...t.historia);
  const skala = (v: number) => (v / max) * (dol - 6);
  const krok = W / t.historia.length;
  const szer = Math.min(18, krok * 0.56);
  const yLinii = dol - skala(t.linia);
  const ile = t.historia.filter((v) => trafil(v, t.linia, t.strona)).length;
  return (
    <div className="p-poprzeczka">
      <div className="p-poprzeczka-opis">
        <span>
          ostatnie {t.historia.length} meczów · linia {fmtLinia(t.linia)}
        </span>
        <span>
          <b>{ile}</b> z {t.historia.length} ponad linią
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${ile} z ${t.historia.length} ponad linią`}>
        {t.historia.map((v, i) => {
          const h = Math.max(skala(v), 2);
          return (
            <g key={i}>
              <motion.rect
                className="a-slupek"
                data-trafil={trafil(v, t.linia, t.strona) ? "true" : undefined}
                x={krok * i + (krok - szer) / 2}
                width={szer}
                rx={3}
                initial={{ height: 0, y: dol }}
                animate={{ height: h, y: dol - h }}
                transition={{ delay: 0.1 + i * 0.04, type: "spring", stiffness: 260, damping: 26 }}
              >
                <title>{`${t.rywale[i] ?? "mecz"}: ${v}`}</title>
              </motion.rect>
              <text className="p-pp-liczba" x={krok * i + krok / 2} y={H - 4}>
                {v}
              </text>
            </g>
          );
        })}
        <line className="p-pp-linia" x1="0" x2={W} y1={yLinii} y2={yLinii} />
      </svg>
    </div>
  );
}

function Kratki({ t }: { t: TypV }) {
  const ile = t.historia.filter((v) => trafil(v, t.linia, t.strona)).length;
  return (
    <div className="p-poprzeczka">
      <div className="p-poprzeczka-opis">
        <span>
          ostatnie mecze · linia {fmtLinia(t.linia)}
        </span>
        <span>
          <b>{ile}</b> z {t.historia.length}
        </span>
      </div>
      <div className="a-kratki">
        {t.historia.map((v, i) => (
          <motion.span
            key={i}
            className="a-kratka"
            data-trafil={trafil(v, t.linia, t.strona) ? "true" : undefined}
            title={`${t.rywale[i] ?? "mecz"}: ${v}`}
            initial={{ opacity: 0, scale: 0.6 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.05 + i * 0.035, type: "spring", stiffness: 380, damping: 24 }}
          >
            {v}
          </motion.span>
        ))}
      </div>
    </div>
  );
}

export function Historia({ wariant, t }: { wariant: string; t: TypV }) {
  if (wariant === "b") return <Slupki t={t} />;
  if (wariant === "c") return <Kratki t={t} />;
  return <Poprzeczka historia={t.historia} rywale={t.rywale} linia={t.linia} strona={t.strona} />;
}

export function ScenaHistorii({ wariant, typy }: { wariant: string; typy: TypV[] }) {
  return (
    <div className="a-scena" style={{ display: "grid", gap: 24 }}>
      {typy.map((t) => (
        <div key={`${wariant}-${t.id}`}>
          <div className="a-typ-kto" style={{ marginBottom: 2 }}>
            {t.kto}
          </div>
          <div className="a-typ-co" style={{ marginBottom: 4 }}>
            {t.rynek.toLowerCase()} {t.strona === "ponizej" ? "poniżej" : "powyżej"} {fmtLinia(t.linia)}
          </div>
          <div style={{ maxWidth: 420 }}>
            <Historia wariant={wariant} t={t} />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ======================================================================
   2.4 PASEK DNI
   ====================================================================== */

export function PasekDni({ wariant, dni }: { wariant: string; dni: DzienV[] }) {
  const [wybrany, setWybrany] = useState(dni[0]?.klucz);
  const id = useId();

  if (wariant === "b") {
    return (
      <div className="a-dni" role="group" aria-label="Dzień">
        {dni.map((d) => {
          const [tydz, data] = d.etykieta.includes(" ") ? d.etykieta.split(" ") : [d.etykieta, ""];
          const nrDnia = Number(d.klucz.slice(8, 10));
          return (
            <button
              key={d.klucz}
              type="button"
              className="a-dzien-kal"
              aria-pressed={d.klucz === wybrany}
              onClick={() => setWybrany(d.klucz)}
              title={data ? `${tydz} ${data}` : tydz}
            >
              <small>{tydz}</small>
              <b>{nrDnia}</b>
              <em>{d.ile} mecz.</em>
            </button>
          );
        })}
      </div>
    );
  }

  if (wariant === "c") {
    return (
      <LayoutGroup id={id}>
        <div className="a-zakladki-tekst" role="group" aria-label="Dzień">
          {dni.map((d) => (
            <button
              key={d.klucz}
              type="button"
              className="a-zakladka-tekst"
              aria-pressed={d.klucz === wybrany}
              onClick={() => setWybrany(d.klucz)}
            >
              {d.etykieta}
              <sup>{d.ile}</sup>
              {d.klucz === wybrany && (
                <motion.span layoutId="kreska-dnia" className="a-podkreslenie" transition={{ type: "spring", stiffness: 500, damping: 38 }} />
              )}
            </button>
          ))}
        </div>
      </LayoutGroup>
    );
  }

  return (
    <div className="p-dni" style={{ margin: 0 }} role="group" aria-label="Dzień">
      {dni.map((d) => (
        <button key={d.klucz} type="button" className="p-dzien" aria-pressed={d.klucz === wybrany} onClick={() => setWybrany(d.klucz)}>
          {d.etykieta}
          <small>{d.ile}</small>
        </button>
      ))}
    </div>
  );
}

/* ======================================================================
   2.5 FILTRY
   ====================================================================== */

type Rynek = { nazwa: string; ile: number };

function Segment({
  opcje,
  wartosc,
  zmien,
}: {
  opcje: string[];
  wartosc: string;
  zmien: (v: string) => void;
}) {
  const id = useId();
  return (
    <LayoutGroup id={id}>
      <div className="a-segment" role="group">
        {opcje.map((o) => (
          <button key={o} type="button" aria-pressed={o === wartosc} onClick={() => zmien(o)}>
            {o === wartosc && (
              <motion.span layoutId="tlo-segmentu" className="a-segment-tlo" transition={{ type: "spring", stiffness: 500, damping: 38 }} />
            )}
            {o}
          </button>
        ))}
      </div>
    </LayoutGroup>
  );
}

export function Filtry({ wariant, rynki, wszystkich }: { wariant: string; rynki: Rynek[]; wszystkich: number }) {
  const [wybrane, setWybrane] = useState<Set<string>>(new Set());
  const [otwarty, setOtwarty] = useState(false);
  const [sort, setSort] = useState("Polecane");
  const [szansa, setSzansa] = useState("każda");
  const przelacz = (n: string) =>
    setWybrane((w) => {
      const x = new Set(w);
      if (x.has(n)) x.delete(n);
      else x.add(n);
      return x;
    });
  const widocznych = useMemo(
    () => (wybrane.size === 0 ? wszystkich : rynki.filter((r) => wybrane.has(r.nazwa)).reduce((s, r) => s + r.ile, 0)),
    [wybrane, rynki, wszystkich],
  );

  const chipyRynkow = (
    <div className="a-chipy" role="group" aria-label="Rynek">
      <button type="button" className="a-chip" aria-pressed={wybrane.size === 0} onClick={() => setWybrane(new Set())}>
        Wszystkie <small>{wszystkich}</small>
      </button>
      {rynki.map((r) => (
        <button key={r.nazwa} type="button" className="a-chip" aria-pressed={wybrane.has(r.nazwa)} onClick={() => przelacz(r.nazwa)}>
          {r.nazwa} <small>{r.ile}</small>
        </button>
      ))}
    </div>
  );

  if (wariant === "b") {
    const ileFiltrow = wybrane.size + (szansa !== "każda" ? 1 : 0);
    return (
      <div>
        <div className="a-rzad">
          <button type="button" className="a-chip" aria-pressed={otwarty} aria-expanded={otwarty} onClick={() => setOtwarty((o) => !o)}>
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
              <path d="M2 3.5h10M4 7h6M6 10.5h2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
            Filtry
            {ileFiltrow > 0 && <span className="a-licznik">{ileFiltrow}</span>}
          </button>
          <span className="p-t3" style={{ fontSize: 13 }}>
            {widocznych} typów
          </span>
        </div>
        <AnimatePresence initial={false}>
          {otwarty && (
            <motion.div
              className="a-panel"
              initial={{ opacity: 0, height: 0, y: -6 }}
              animate={{ opacity: 1, height: "auto", y: 0 }}
              exit={{ opacity: 0, height: 0, y: -6 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            >
              <div>
                <h4>Rynek</h4>
                {chipyRynkow}
              </div>
              <div>
                <h4>Szansa</h4>
                <Segment opcje={["każda", "od 60%", "od 70%"]} wartosc={szansa} zmien={setSzansa} />
              </div>
              <div className="a-rzad" style={{ justifyContent: "flex-end" }}>
                <button type="button" className="a-guzik" data-t="cichy" data-r="m" onClick={() => { setWybrane(new Set()); setSzansa("każda"); }}>
                  Wyczyść
                </button>
                <button type="button" className="a-guzik" data-t="glowny" data-r="m" onClick={() => setOtwarty(false)}>
                  Pokaż {widocznych} typów
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    );
  }

  if (wariant === "c") {
    return (
      <div style={{ display: "grid", gap: 12 }}>
        <div className="a-rzad" style={{ justifyContent: "space-between" }}>
          <Segment opcje={["Polecane", "Szansa", "Kurs", "Godzina"]} wartosc={sort} zmien={setSort} />
          <span className="p-t3" style={{ fontSize: 13 }}>
            {widocznych} typów
          </span>
        </div>
        {chipyRynkow}
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 10 }}>
      {chipyRynkow}
      <span className="p-t3" style={{ fontSize: 13 }}>
        {widocznych} typów
      </span>
    </div>
  );
}

/* ======================================================================
   2.6 ZAKŁADKI SEKCJI
   ====================================================================== */

const ZAKLADKI = [
  { nazwa: "Wysokie szanse", ile: 24, opis: "wchodzą najczęściej, kursy niższe" },
  { nazwa: "Wyższe kursy", ile: 19, opis: "więcej płacą, wchodzą rzadziej" },
  { nazwa: "Drabinki", ile: 7, opis: "jeden zawodnik, kilka linii" },
];

export function Zakladki({ wariant }: { wariant: string }) {
  const [wybrana, setWybrana] = useState(ZAKLADKI[0].nazwa);
  const id = useId();
  const sprezyna = { type: "spring" as const, stiffness: 500, damping: 38 };

  if (wariant === "b") {
    return (
      <Segment opcje={ZAKLADKI.map((z) => z.nazwa)} wartosc={wybrana} zmien={setWybrana} />
    );
  }

  if (wariant === "c") {
    return (
      <LayoutGroup id={id}>
        <div className="a-karty-zakladek" role="group">
          {ZAKLADKI.map((z) => (
            <button key={z.nazwa} type="button" className="a-karta-zakladki" aria-pressed={z.nazwa === wybrana} onClick={() => setWybrana(z.nazwa)}>
              {z.nazwa === wybrana && <motion.span layoutId="kreska-karty" className="a-podkreslenie" transition={sprezyna} />}
              <b>
                {z.nazwa} <span>{z.ile}</span>
              </b>
              <small>{z.opis}</small>
            </button>
          ))}
        </div>
      </LayoutGroup>
    );
  }

  return (
    <LayoutGroup id={id}>
      <div className="a-zakladki-tekst" role="group">
        {ZAKLADKI.map((z) => (
          <button key={z.nazwa} type="button" className="a-zakladka-tekst" aria-pressed={z.nazwa === wybrana} onClick={() => setWybrana(z.nazwa)}>
            {z.nazwa}
            <sup>{z.ile}</sup>
            {z.nazwa === wybrana && <motion.span layoutId="kreska-zakladki" className="a-podkreslenie" transition={sprezyna} />}
          </button>
        ))}
      </div>
    </LayoutGroup>
  );
}
