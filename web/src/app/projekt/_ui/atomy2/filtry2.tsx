"use client";

import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import type { TypLekki } from "../../_dane/przygotuj";
import { Krzyzyk, Ptaszek } from "../atomy/wspolne";
import { FlagaLigi } from "../Herb";
import { KafelekD, SzansaD } from "./podstawowe";

/*
 * 2.5 FILTRY – przebudowa po „trochę chaos” (30.09).
 *
 * Skąd był chaos:
 *  - „Szansa od 70%” i „Kurs od 1,50” dublowały zakładki Wysokie szanse / Wyższe kursy,
 *  - te same ustawienia żyły w dwóch miejscach (chip i panel),
 *  - aktywny filtr pokazywał się trzema sposobami, trzy rodzaje chipów wyglądały tak samo,
 *  - liczba i sortowanie w osobnym rzędzie.
 *
 * Zasady nowej wersji:
 *  1. Jedno ustawienie = jedno miejsce. Szybkie przełączniki tylko dla tego, czego nie ma
 *     nigdzie indziej (czas, składy); szansa/kurs/rynek/liga tylko w panelu.
 *  2. Jeden rząd: przełączniki z lewej, menu (Sortuj, Filtry) z prawej.
 *  3. Aktywne filtry z panelu = jedna cicha linijka pod paskiem, tylko gdy coś jest włączone.
 */

const TERAZ = Date.UTC(2026, 8, 30, 20, 40) / 1000;

type LigaF = { nazwa: string; kategoria: string; flaga: string | null; id: number | null; c1: string; c2: string };

type Panel = { rynki: Set<string>; szansa: string; kurs: string; ligi: Set<string> };
const PUSTY: Panel = { rynki: new Set(), szansa: "0", kurs: "0", ligi: new Set() };

const SORTY: [string, string][] = [
  ["polecane", "Polecane"],
  ["szansa", "Największa szansa"],
  ["kurs", "Najwyższy kurs"],
  ["godzina", "Najbliższy mecz"],
];

export const POLKI = [
  { klucz: "wysoka_szansa", nazwa: "Wysokie szanse", opis: "wchodzą najczęściej, kursy niższe" },
  { klucz: "wyzsze_kursy", nazwa: "Wyższe kursy", opis: "więcej płacą, wchodzą rzadziej" },
  { klucz: "drabinki", nazwa: "Drabinki", opis: "jeden zawodnik, kilka linii" },
];

export function odm(n: number) {
  return n === 1 ? "typ" : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? "typy" : "typów";
}

export function Segment({ opcje, wartosc, zmien }: { opcje: [string, string][]; wartosc: string; zmien: (v: string) => void }) {
  const id = useId();
  return (
    <LayoutGroup id={id}>
      <div className="a-segment" role="radiogroup">
        {opcje.map(([v, e]) => (
          <button key={v} type="button" role="radio" aria-checked={v === wartosc} onClick={() => zmien(v)}>
            {v === wartosc && (
              <motion.span layoutId="tlo" className="a-segment-tlo" transition={{ type: "spring", stiffness: 500, damping: 38 }} />
            )}
            {e}
          </button>
        ))}
      </div>
    </LayoutGroup>
  );
}

export function IkonaZegar() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
      <circle cx="7" cy="7" r="5.2" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M7 4.3V7l1.8 1.2" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

export function IkonaKoszulka() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
      <path
        d="M5 2 2 3.6 3 6.4l1.2-.5V12h5.6V5.9l1.2.5 1-2.8L9 2c-.3.9-1 1.4-2 1.4S5.3 2.9 5 2Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function FiltryWKontekscie({
  wszystkie,
  ligi,
  drabinki,
  telefon,
}: {
  wszystkie: TypLekki[];
  ligi: LigaF[];
  drabinki: number;
  telefon: boolean;
}) {
  const [polka, setPolka] = useState(POLKI[0].klucz);
  const [wkrotce, setWkrotce] = useState(false);
  const [sklady, setSklady] = useState(false);
  const [f, setF] = useState<Panel>(PUSTY);
  const [roboczy, setRoboczy] = useState<Panel>(PUSTY);
  const [otwarty, setOtwarty] = useState(false);
  const [sort, setSort] = useState("polecane");
  const [menu, setMenu] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const przycisk = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLSpanElement>(null);
  const idKart = useId();

  const naPolce = useMemo(() => wszystkie.filter((t) => t.polka === polka), [wszystkie, polka]);

  const pasuje = (t: TypLekki, p: Panel, pomin?: "rynek" | "liga") => {
    if (wkrotce && t.ts - TERAZ > 3 * 3600) return false;
    if (sklady && !t.sklady) return false;
    if (pomin !== "rynek" && p.rynki.size && !p.rynki.has(t.rynek)) return false;
    if (pomin !== "liga" && p.ligi.size && !p.ligi.has(t.liga)) return false;
    if (t.p < Number(p.szansa) / 100) return false;
    if (t.kurs < Number(p.kurs) / 100) return false;
    return true;
  };

  const wynik = useMemo(() => {
    const x = naPolce.filter((t) => pasuje(t, f));
    if (sort === "szansa") x.sort((a, b) => b.p - a.p);
    if (sort === "kurs") x.sort((a, b) => b.kurs - a.kurs);
    if (sort === "godzina") x.sort((a, b) => a.ts - b.ts);
    return x;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [naPolce, f, sort, wkrotce, sklady]);

  const wRoboczym = naPolce.filter((t) => pasuje(t, roboczy)).length;
  const licz = (klucz: "rynek" | "liga", wartosc: string) =>
    naPolce.filter((t) => pasuje(t, roboczy, klucz) && (klucz === "rynek" ? t.rynek === wartosc : t.liga === wartosc)).length;

  const rynkiPolki = [...new Set(naPolce.map((t) => t.rynek))];
  const ligiPolki = ligi.filter((l) => naPolce.some((t) => t.liga === l.nazwa));

  const aktywne: { etykieta: string; usun: () => void }[] = [
    ...[...f.rynki].map((r) => ({
      etykieta: r,
      usun: () => setF((x) => ({ ...x, rynki: new Set([...x.rynki].filter((y) => y !== r)) })),
    })),
    ...(f.szansa !== "0" ? [{ etykieta: `szansa od ${f.szansa}%`, usun: () => setF((x) => ({ ...x, szansa: "0" })) }] : []),
    ...(f.kurs !== "0" ? [{ etykieta: `kurs od ${(Number(f.kurs) / 100).toFixed(2).replace(".", ",")}`, usun: () => setF((x) => ({ ...x, kurs: "0" })) }] : []),
    ...[...f.ligi].map((l) => ({
      etykieta: l,
      usun: () => setF((x) => ({ ...x, ligi: new Set([...x.ligi].filter((y) => y !== l)) })),
    })),
  ];

  useEffect(() => {
    if (!otwarty && !menu) return;
    const esc = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOtwarty(false);
      setMenu(false);
    };
    const klik = (e: MouseEvent) => {
      const c = e.target as Node;
      if (menu && menuRef.current && !menuRef.current.contains(c)) setMenu(false);
      if (otwarty && !telefon && panel.current && !panel.current.contains(c) && !przycisk.current?.contains(c)) setOtwarty(false);
    };
    document.addEventListener("keydown", esc);
    document.addEventListener("mousedown", klik);
    return () => {
      document.removeEventListener("keydown", esc);
      document.removeEventListener("mousedown", klik);
    };
  }, [otwarty, menu, telefon]);

  const przelacz = <T,>(zbior: Set<T>, v: T) => {
    const n = new Set(zbior);
    if (n.has(v)) n.delete(v);
    else n.add(v);
    return n;
  };

  const ileSkladow = naPolce.filter((t) => t.sklady).length;

  return (
    <div className="e-rama" style={{ minHeight: otwarty ? (telefon ? 640 : 600) : undefined }}>
      {/* zakładki – pierwsza wersja kart (decyzja 30.09), prawdziwe liczby */}
      <LayoutGroup id={idKart}>
        <div className="a-karty-zakladek" role="tablist" aria-label="Rodzaj typów">
          {POLKI.map((p) => {
            const ile = p.klucz === "drabinki" ? drabinki : wszystkie.filter((t) => t.polka === p.klucz).length;
            return (
              <button
                key={p.klucz}
                type="button"
                role="tab"
                className="a-karta-zakladki"
                aria-selected={p.klucz === polka}
                onClick={() => {
                  setPolka(p.klucz);
                  setF(PUSTY);
                }}
              >
                {p.klucz === polka && (
                  <motion.span layoutId="kreska-karty" className="a-podkreslenie" transition={{ type: "spring", stiffness: 500, damping: 38 }} />
                )}
                <b>
                  {p.nazwa} <span>{ile}</span>
                </b>
                <small>{p.opis}</small>
              </button>
            );
          })}
        </div>
      </LayoutGroup>

      {/* JEDEN rząd: przełączniki z lewej, menu z prawej */}
      <div className="e-pasek">
        <div className="e-lewa">
          <button
            type="button"
            className="e-przelacznik d-dotyk"
            aria-pressed={wkrotce}
            onClick={() => setWkrotce((x) => !x)}
            title="Mecze, które zaczynają się w ciągu 3 godzin"
          >
            <IkonaZegar />
            Wkrótce
          </button>
          <button
            type="button"
            className="e-przelacznik d-dotyk"
            aria-pressed={sklady}
            disabled={ileSkladow === 0 && !sklady}
            onClick={() => setSklady((x) => !x)}
            title={ileSkladow === 0 ? "Składy ogłaszane są ok. godzinę przed meczem – na razie żaden mecz ich nie ma" : "Tylko mecze z ogłoszonymi składami"}
          >
            <IkonaKoszulka />
            Pewne składy
          </button>
        </div>
        <div className="e-prawa">
          <span ref={menuRef} style={{ position: "relative" }}>
            <button
              type="button"
              className="e-menu-guzik d-dotyk"
              aria-haspopup="menu"
              aria-expanded={menu}
              aria-label={`Sortuj: ${SORTY.find(([k]) => k === sort)?.[1]}`}
              onClick={() => setMenu((m) => !m)}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
                <path d="M4 2.5v9M1.8 9.3 4 11.5l2.2-2.2M10 11.5v-9M7.8 4.7 10 2.5l2.2 2.2" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="e-etykieta-sortu">{SORTY.find(([k]) => k === sort)?.[1]}</span>
            </button>
            <AnimatePresence>
              {menu && (
                <motion.div
                  className="d-menu"
                  role="menu"
                  initial={{ opacity: 0, y: -4, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -4, scale: 0.98 }}
                  transition={{ duration: 0.14 }}
                >
                  {SORTY.map(([k, e]) => (
                    <button
                      key={k}
                      type="button"
                      role="menuitemradio"
                      aria-checked={k === sort}
                      onClick={() => {
                        setSort(k);
                        setMenu(false);
                      }}
                    >
                      {e}
                      {k === sort && <Ptaszek rozmiar={11} />}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </span>
          <button
            ref={przycisk}
            type="button"
            className="e-menu-guzik d-dotyk"
            aria-haspopup="dialog"
            aria-expanded={otwarty}
            data-aktywny={aktywne.length > 0 ? "true" : undefined}
            onClick={() => {
              setRoboczy(f);
              setOtwarty((o) => !o);
            }}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
              <path d="M2 3.5h10M4 7h6M6 10.5h2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
            Filtry
            {aktywne.length > 0 && <span className="a-licznik">{aktywne.length}</span>}
          </button>
        </div>
      </div>

      {/* aktywne filtry z panelu – jedna cicha linijka, tylko gdy coś jest włączone */}
      <AnimatePresence initial={false}>
        {aktywne.length > 0 && (
          <motion.div
            className="e-aktywne"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
          >
            <span className="e-aktywne-liczba">
              {wynik.length} z {naPolce.length}
            </span>
            {aktywne.map((a) => (
              <button key={a.etykieta} type="button" className="e-aktywny" onClick={a.usun} aria-label={`Usuń filtr: ${a.etykieta}`}>
                {a.etykieta}
                <Krzyzyk rozmiar={8} />
              </button>
            ))}
            <button type="button" className="e-wyczysc" onClick={() => setF(PUSTY)}>
              Wyczyść
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* lista – naprawdę filtrowana i sortowana */}
      <div className="e-lista">
        {polka === "drabinki" ? (
          <div className="d-pusty">
            <div className="p-n" style={{ fontSize: 17 }}>
              Drabinki mają własny układ
            </div>
            <p>Tu wejdzie karta drabinki z etapu 3 – jeden zawodnik, kilka linii obok siebie.</p>
          </div>
        ) : wynik.length === 0 ? (
          <div className="d-pusty">
            <div className="p-n" style={{ fontSize: 17 }}>
              Żaden typ nie pasuje
            </div>
            <p>{wkrotce ? "W najbliższych 3 godzinach nie ma meczów z typami na tej półce." : "Za wąsko ustawione filtry."}</p>
            <button
              type="button"
              className="a-guzik"
              data-t="drugi"
              data-r="m"
              onClick={() => {
                setF(PUSTY);
                setWkrotce(false);
                setSklady(false);
              }}
            >
              Wyczyść wszystko
            </button>
          </div>
        ) : (
          <LayoutGroup>
            <AnimatePresence initial={false}>
              {wynik.slice(0, 6).map((t) => (
                <motion.div
                  key={t.id}
                  layout
                  className="e-wiersz"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ layout: { type: "spring", stiffness: 420, damping: 38 }, opacity: { duration: 0.15 } }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div className="a-typ-kto" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {t.kto}
                    </div>
                    <div className="a-typ-co">{t.opis}</div>
                  </div>
                  <SzansaD p={t.p} mala />
                  <KafelekD k={{ kurs: t.kurs, bukmacher: t.bukmacher }} />
                </motion.div>
              ))}
            </AnimatePresence>
            {wynik.length > 6 && <div className="e-wiecej">i jeszcze {wynik.length - 6} {odm(wynik.length - 6)}</div>}
          </LayoutGroup>
        )}
      </div>

      {/* panel */}
      <AnimatePresence>
        {otwarty && telefon && (
          <motion.div key="tlo" className="d-panel-tlo" onClick={() => setOtwarty(false)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
        )}
        {otwarty && (
          <motion.div
            key="panel"
            ref={panel}
            className="d-panel e-panel"
            data-tryb={telefon ? "arkusz" : "dymek"}
            role="dialog"
            aria-label="Filtry"
            initial={telefon ? { y: "100%" } : { opacity: 0, y: -6, scale: 0.98 }}
            animate={telefon ? { y: 0 } : { opacity: 1, y: 0, scale: 1 }}
            exit={telefon ? { y: "100%" } : { opacity: 0, y: -6, scale: 0.98 }}
            transition={telefon ? { type: "spring", stiffness: 380, damping: 38 } : { duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
            drag={telefon ? "y" : false}
            dragConstraints={{ top: 0, bottom: 0 }}
            dragElastic={{ top: 0, bottom: 0.6 }}
            onDragEnd={(_, info) => {
              if (info.offset.y > 90) setOtwarty(false);
            }}
          >
            <div>
              {telefon && <div className="d-uchwyt" aria-hidden />}
              <div className="d-panel-glowa">
                <b className="p-n" style={{ fontSize: 17 }}>
                  Filtry
                </b>
                <button type="button" className="a-guzik" data-t="cichy" data-r="s" onClick={() => setRoboczy(PUSTY)}>
                  Wyczyść
                </button>
              </div>
            </div>
            <div className="d-panel-tresc">
              <div>
                <h4>Rynek</h4>
                <div className="a-chipy">
                  {rynkiPolki.map((r) => {
                    const n = licz("rynek", r);
                    const on = roboczy.rynki.has(r);
                    return (
                      <button
                        key={r}
                        type="button"
                        className="a-chip d-dotyk"
                        aria-pressed={on}
                        disabled={n === 0 && !on}
                        style={n === 0 && !on ? { opacity: 0.4 } : undefined}
                        onClick={() => setRoboczy((x) => ({ ...x, rynki: przelacz(x.rynki, r) }))}
                      >
                        {r} <small>{n}</small>
                      </button>
                    );
                  })}
                </div>
              </div>
              <div>
                <h4>Szansa</h4>
                <Segment
                  wartosc={roboczy.szansa}
                  zmien={(v) => setRoboczy((x) => ({ ...x, szansa: v }))}
                  opcje={[
                    ["0", "każda"],
                    ["60", "od 60%"],
                    ["70", "od 70%"],
                    ["80", "od 80%"],
                  ]}
                />
              </div>
              <div>
                <h4>Kurs</h4>
                <Segment
                  wartosc={roboczy.kurs}
                  zmien={(v) => setRoboczy((x) => ({ ...x, kurs: v }))}
                  opcje={[
                    ["0", "każdy"],
                    ["130", "od 1,30"],
                    ["150", "od 1,50"],
                    ["200", "od 2,00"],
                  ]}
                />
              </div>
              <div>
                <h4>Rozgrywki</h4>
                <div className="e-ligi">
                  {ligiPolki.map((l) => {
                    const n = licz("liga", l.nazwa);
                    const on = roboczy.ligi.has(l.nazwa);
                    return (
                      <button
                        key={l.nazwa}
                        type="button"
                        className="e-liga"
                        role="checkbox"
                        aria-checked={on}
                        disabled={n === 0 && !on}
                        onClick={() => setRoboczy((x) => ({ ...x, ligi: przelacz(x.ligi, l.nazwa) }))}
                      >
                        <span className="e-pole" aria-hidden>
                          {on && <Ptaszek rozmiar={10} />}
                        </span>
                        <FlagaLigi flaga={l.flaga} id={l.id} c1={l.c1} c2={l.c2} tryb="prawdziwy" />
                        <span className="e-liga-nazwa">
                          {l.nazwa}
                          <small>{l.kategoria}</small>
                        </span>
                        <em>{n}</em>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
            <div className="d-panel-stopka">
              <button type="button" className="a-guzik" data-t="cichy" data-r="m" onClick={() => setOtwarty(false)}>
                Anuluj
              </button>
              <button
                type="button"
                className="a-guzik"
                data-t="glowny"
                data-r={telefon ? "l" : "m"}
                disabled={wRoboczym === 0}
                onClick={() => {
                  setF(roboczy);
                  setOtwarty(false);
                }}
              >
                {wRoboczym === 0 ? "Brak typów" : `Pokaż ${wRoboczym} ${odm(wRoboczym)}`}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
