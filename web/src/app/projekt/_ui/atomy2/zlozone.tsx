"use client";

import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { fmtKurs, fmtLinia } from "@/lib/format";

import type { TypLekki, TypV } from "../../_dane/przygotuj";
import { Krzyzyk, Ptaszek, Zegar, Zwrot } from "../atomy/wspolne";
import { Blysk } from "../atomy/wyniki-ruch";
import { KafelekD, type Kurs } from "./podstawowe";

/* „teraz” migawki (30.09, 22:40 w Polsce) – filtry czasu liczą od tej chwili */
const TERAZ = Date.UTC(2026, 8, 30, 20, 40) / 1000;

function SegmentD<T extends string>({
  opcje,
  wartosc,
  zmien,
}: {
  opcje: [T, string][];
  wartosc: T;
  zmien: (v: T) => void;
}) {
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

/* ======================================================================
   2.5 FILTRY – przycisk i panel + szybkie filtry
   ====================================================================== */

type Szansa = "kazda" | "60" | "70" | "80";
type KursF = "kazdy" | "150" | "200";
type Czas = "wszystkie" | "3h" | "24h";

type Stan = { rynki: Set<string>; szansa: Szansa; kurs: KursF; czas: Czas; sklady: boolean };

const PUSTY: Stan = { rynki: new Set(), szansa: "kazda", kurs: "kazdy", czas: "wszystkie", sklady: false };

function pasuje(t: TypLekki, s: Stan, bezRynku = false) {
  if (!bezRynku && s.rynki.size > 0 && !s.rynki.has(t.rynek)) return false;
  if (s.szansa !== "kazda" && t.p < Number(s.szansa) / 100) return false;
  if (s.kurs !== "kazdy" && t.kurs < Number(s.kurs) / 100) return false;
  if (s.czas === "3h" && t.ts - TERAZ > 3 * 3600) return false;
  if (s.czas === "24h" && t.ts - TERAZ > 24 * 3600) return false;
  if (s.sklady && !t.sklady) return false;
  return true;
}

const SORTY = ["Polecane", "Największa szansa", "Najwyższy kurs", "Najbliższy mecz"];

export function FiltryD({ wszystkie, rynki, telefon }: { wszystkie: TypLekki[]; rynki: string[]; telefon: boolean }) {
  const [s, setS] = useState<Stan>(PUSTY);
  const [roboczy, setRoboczy] = useState<Stan>(PUSTY);
  const [otwarty, setOtwarty] = useState(false);
  const [sort, setSort] = useState(SORTY[0]);
  const [menu, setMenu] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const przycisk = useRef<HTMLButtonElement>(null);

  const ile = (x: Stan) => wszystkie.filter((t) => pasuje(t, x)).length;
  const widocznych = ile(s);
  const wRoboczym = ile(roboczy);
  const licznikiRynkow = useMemo(() => {
    const m = new Map<string, number>();
    for (const t of wszystkie) if (pasuje(t, roboczy, true)) m.set(t.rynek, (m.get(t.rynek) ?? 0) + 1);
    return m;
  }, [wszystkie, roboczy]);
  const ileAktywnych =
    s.rynki.size + (s.szansa !== "kazda" ? 1 : 0) + (s.kurs !== "kazdy" ? 1 : 0) + (s.czas !== "wszystkie" ? 1 : 0) + (s.sklady ? 1 : 0);
  const skladowPewnych = wszystkie.filter((t) => t.sklady).length;

  const otworz = () => {
    setRoboczy(s);
    setOtwarty(true);
  };

  // dymek (komputer): zamyka klik obok i Escape; arkusz ma własne tło
  useEffect(() => {
    if (!otwarty && !menu) return;
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOtwarty(false);
        setMenu(false);
        przycisk.current?.focus();
      }
    };
    const klik = (e: MouseEvent) => {
      const cel = e.target as Node;
      if (otwarty && !telefon && panel.current && !panel.current.contains(cel) && !przycisk.current?.contains(cel)) setOtwarty(false);
    };
    document.addEventListener("keydown", esc);
    document.addEventListener("mousedown", klik);
    return () => {
      document.removeEventListener("keydown", esc);
      document.removeEventListener("mousedown", klik);
    };
  }, [otwarty, menu, telefon]);

  const przelaczSzybki = (zmiana: Partial<Stan>, aktywny: boolean) =>
    setS((x) => ({ ...x, ...(aktywny ? Object.fromEntries(Object.keys(zmiana).map((k) => [k, PUSTY[k as keyof Stan]])) : zmiana) }));

  const szybkie: { etykieta: string; aktywny: boolean; zmiana: Partial<Stan>; wylaczony?: string }[] = [
    { etykieta: "Szansa od 70%", aktywny: s.szansa === "70", zmiana: { szansa: "70" } },
    { etykieta: "Kurs od 1,50", aktywny: s.kurs === "150", zmiana: { kurs: "150" } },
    { etykieta: "Najbliższe 3 h", aktywny: s.czas === "3h", zmiana: { czas: "3h" } },
    {
      etykieta: "Pewne składy",
      aktywny: s.sklady,
      zmiana: { sklady: true },
      wylaczony: skladowPewnych === 0 ? "Składy ogłaszane są ok. godzinę przed meczem" : undefined,
    },
  ];

  const trybPanelu = telefon ? "arkusz" : "dymek";

  return (
    // miejsce na otwarty panel rezerwujemy tylko wtedy, gdy jest otwarty
    <div className="d-scena-filtrow" style={{ minHeight: otwarty ? (telefon ? 560 : 540) : undefined }}>
      <div className="d-filtry-pasek">
        <button
          ref={przycisk}
          type="button"
          className="a-chip d-dotyk"
          aria-haspopup="dialog"
          aria-expanded={otwarty}
          aria-pressed={ileAktywnych > 0}
          onClick={() => (otwarty ? setOtwarty(false) : otworz())}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
            <path d="M2 3.5h10M4 7h6M6 10.5h2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
          Filtry
          <AnimatePresence initial={false}>
            {ileAktywnych > 0 && (
              <motion.span
                className="a-licznik"
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                exit={{ scale: 0 }}
                transition={{ type: "spring", stiffness: 500, damping: 26 }}
              >
                {ileAktywnych}
              </motion.span>
            )}
          </AnimatePresence>
        </button>
        <span className="d-separator" aria-hidden />
        {szybkie.map((q) => (
          <button
            key={q.etykieta}
            type="button"
            className="a-chip d-dotyk"
            aria-pressed={q.aktywny}
            disabled={!!q.wylaczony}
            title={q.wylaczony}
            style={q.wylaczony ? { opacity: 0.45, cursor: "not-allowed" } : undefined}
            onClick={() => przelaczSzybki(q.zmiana, q.aktywny)}
          >
            {q.etykieta}
          </button>
        ))}
        <AnimatePresence initial={false}>
          {[...s.rynki].map((r) => (
            <motion.span
              key={r}
              className="a-chip d-chip-aktywny"
              layout
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
            >
              {r}
              <button
                type="button"
                className="d-chip-usun"
                aria-label={`Usuń filtr ${r}`}
                onClick={() =>
                  setS((x) => {
                    const n = new Set(x.rynki);
                    n.delete(r);
                    return { ...x, rynki: n };
                  })
                }
              >
                <Krzyzyk rozmiar={8} />
              </button>
            </motion.span>
          ))}
        </AnimatePresence>
      </div>

      <div className="d-filtry-dol">
        <span>
          <b style={{ color: "var(--t1)" }}>{widocznych}</b> {widocznych === 1 ? "typ" : widocznych < 5 && widocznych > 1 ? "typy" : "typów"}
          {ileAktywnych > 0 && (
            <>
              {" · "}
              <button type="button" className="a-guzik" data-t="cichy" data-r="s" style={{ height: 24, padding: "0 6px" }} onClick={() => setS(PUSTY)}>
                wyczyść
              </button>
            </>
          )}
        </span>
        <span style={{ position: "relative" }}>
          <button type="button" className="d-sort" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>
            Sortuj: <b>{sort}</b>
            <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden>
              <path d="m2 3.5 3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
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
                {SORTY.map((x) => (
                  <button
                    key={x}
                    type="button"
                    role="menuitemradio"
                    aria-checked={x === sort}
                    onClick={() => {
                      setSort(x);
                      setMenu(false);
                    }}
                  >
                    {x}
                    {x === sort && <Ptaszek rozmiar={11} />}
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </span>
      </div>

      <AnimatePresence>
        {otwarty && telefon && (
          <motion.div
            key="tlo"
            className="d-panel-tlo"
            onClick={() => setOtwarty(false)}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
        )}
        {otwarty && (
          <motion.div
            key="panel"
            ref={panel}
            className="d-panel"
            data-tryb={trybPanelu}
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
                  {rynki.map((r) => {
                    const n = licznikiRynkow.get(r) ?? 0;
                    return (
                      <button
                        key={r}
                        type="button"
                        className="a-chip d-dotyk"
                        aria-pressed={roboczy.rynki.has(r)}
                        disabled={n === 0 && !roboczy.rynki.has(r)}
                        style={n === 0 && !roboczy.rynki.has(r) ? { opacity: 0.4 } : undefined}
                        onClick={() =>
                          setRoboczy((x) => {
                            const nr = new Set(x.rynki);
                            if (nr.has(r)) nr.delete(r);
                            else nr.add(r);
                            return { ...x, rynki: nr };
                          })
                        }
                      >
                        {r} <small>{n}</small>
                      </button>
                    );
                  })}
                </div>
              </div>
              <div>
                <h4>Szansa</h4>
                <SegmentD
                  wartosc={roboczy.szansa}
                  zmien={(v) => setRoboczy((x) => ({ ...x, szansa: v }))}
                  opcje={[
                    ["kazda", "każda"],
                    ["60", "od 60%"],
                    ["70", "od 70%"],
                    ["80", "od 80%"],
                  ]}
                />
              </div>
              <div>
                <h4>Kurs</h4>
                <SegmentD
                  wartosc={roboczy.kurs}
                  zmien={(v) => setRoboczy((x) => ({ ...x, kurs: v }))}
                  opcje={[
                    ["kazdy", "każdy"],
                    ["150", "od 1,50"],
                    ["200", "od 2,00"],
                  ]}
                />
              </div>
              <div>
                <h4>Kiedy</h4>
                <SegmentD
                  wartosc={roboczy.czas}
                  zmien={(v) => setRoboczy((x) => ({ ...x, czas: v }))}
                  opcje={[
                    ["wszystkie", "wszystkie"],
                    ["3h", "w ciągu 3 h"],
                    ["24h", "w ciągu doby"],
                  ]}
                />
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
                  setS(roboczy);
                  setOtwarty(false);
                }}
              >
                {wRoboczym === 0 ? "Brak typów" : `Pokaż ${wRoboczym} ${wRoboczym === 1 ? "typ" : wRoboczym < 5 ? "typy" : "typów"}`}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ======================================================================
   2.6 KARTY ZAKŁADEK – z prawdziwymi liczbami
   ====================================================================== */

export function KartyD({ wszystkie, drabinki }: { wszystkie: TypLekki[]; drabinki: number }) {
  const id = useId();
  const staty = (polka: string) => {
    const x = wszystkie.filter((t) => t.polka === polka);
    const sr = x.reduce((a, t) => a + t.p, 0) / Math.max(x.length, 1);
    const k = x.map((t) => t.kurs);
    return { ile: x.length, sr, min: Math.min(...k), max: Math.max(...k) };
  };
  const ws = staty("wysoka_szansa");
  const wk = staty("wyzsze_kursy");
  const karty = [
    {
      klucz: "ws",
      nazwa: "Wysokie szanse",
      ile: ws.ile,
      opis: "wchodzą najczęściej",
      staty: [
        ["śr. szansa", `${Math.round(ws.sr * 100)}%`],
        ["kursy", `${fmtKurs(ws.min)}–${fmtKurs(ws.max)}`],
      ],
    },
    {
      klucz: "wk",
      nazwa: "Wyższe kursy",
      ile: wk.ile,
      opis: "płacą więcej, wchodzą rzadziej",
      staty: [
        ["śr. szansa", `${Math.round(wk.sr * 100)}%`],
        ["kursy", `${fmtKurs(wk.min)}–${fmtKurs(wk.max)}`],
      ],
    },
    {
      klucz: "dr",
      nazwa: "Drabinki",
      ile: drabinki,
      opis: "jeden zawodnik, kilka linii",
      staty: [["szczeble", "do 5"]],
    },
  ];
  const [wybrana, setWybrana] = useState(karty[0].klucz);

  return (
    <LayoutGroup id={id}>
      <div className="d-karty" role="tablist" aria-label="Rodzaj typów">
        {karty.map((k) => (
          <button
            key={k.klucz}
            type="button"
            role="tab"
            aria-selected={k.klucz === wybrana}
            className="d-karta"
            onClick={() => setWybrana(k.klucz)}
          >
            {k.klucz === wybrana && (
              <motion.span layoutId="kreska-karty" className="d-karta-kreska" transition={{ type: "spring", stiffness: 480, damping: 38 }} />
            )}
            <span className="d-karta-glowa">
              <b>{k.nazwa}</b>
              <span>{k.ile}</span>
            </span>
            <small>{k.opis}</small>
            <span className="d-karta-staty">
              {k.staty.map(([a, b]) => (
                <span key={a}>
                  {a} <b>{b}</b>
                </span>
              ))}
            </span>
          </button>
        ))}
      </div>
    </LayoutGroup>
  );
}

/* ======================================================================
   2.7 ROZLICZENIE – pasek i przygaszenie, z animacją rozliczenia
   ====================================================================== */

type Wynik = "ok" | "nie" | "zwrot" | "czeka";
const KOLOR: Record<Wynik, string> = { ok: "var(--ok)", nie: "var(--nie)", zwrot: "var(--zwrot)", czeka: "var(--czeka)" };
const TEKST: Record<Wynik, string> = { ok: "weszło", nie: "nie weszło", zwrot: "zwrot", czeka: "czeka" };

function Etykieta({ w }: { w: Wynik }) {
  const ikona = { ok: <Ptaszek rozmiar={11} />, nie: <Krzyzyk rozmiar={10} />, zwrot: <Zwrot rozmiar={11} />, czeka: <Zegar rozmiar={11} /> }[w];
  return (
    <motion.span
      key={w}
      className={`p-wynik p-wynik-${w}`}
      initial={{ opacity: 0, scale: 0.85 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 480, damping: 30 }}
    >
      {ikona}
      {TEKST[w]}
    </motion.span>
  );
}

export function RozliczenieD({ typy }: { typy: TypV[] }) {
  const [rozliczony, setRozliczony] = useState(false);
  const wiersze: { t: TypV; w: Wynik; bylo: string }[] = [
    { t: typy[0], w: "ok", bylo: "było 3" },
    { t: typy[1], w: "nie", bylo: "było 0" },
    { t: typy[2], w: "zwrot", bylo: "nie zagrał" },
    { t: typy[0], w: rozliczony ? "ok" : "czeka", bylo: rozliczony ? "było 2" : `start ${typy[0].godzina}` },
  ];
  const ok = wiersze.filter((x) => x.w === "ok").length;
  const rozstrzygniete = wiersze.filter((x) => x.w === "ok" || x.w === "nie").length;

  return (
    <div className="a-scena">
      <div className="d-dzien-wynikow">
        <b>Czw 1.10</b>
        <span>
          {ok} z {rozstrzygniete} weszło
        </span>
        <span className="d-mini-pasek" aria-hidden>
          {wiersze.map((x, i) => (
            <motion.i key={i} layout style={{ flex: 1, background: KOLOR[x.w], opacity: x.w === "czeka" ? 0.35 : 1 }} />
          ))}
        </span>
      </div>
      {wiersze.map(({ t, w, bylo }, i) => (
        <div key={i} className="d-wiersz" data-wynik={w} style={{ ["--kolor-wyniku" as string]: KOLOR[w] }}>
          <motion.span
            key={`pasek-${w}`}
            className="d-wiersz-pasek"
            initial={{ scaleY: 0 }}
            animate={{ scaleY: 1 }}
            transition={{ type: "spring", stiffness: 300, damping: 26, delay: 0.05 * i }}
          />
          <div className="d-przygas" style={{ minWidth: 0 }}>
            <div className="a-typ-kto">{t.kto}</div>
            <div className="a-typ-co">
              {t.rynek.toLowerCase()} {t.strona === "ponizej" ? "poniżej" : "powyżej"} {fmtLinia(t.linia)}
            </div>
          </div>
          <span className="d-kurs-liczba d-przygas" style={{ fontSize: 15 }}>
            {fmtKurs(t.kurs)}
          </span>
          <span className="d-wynik-prawa">
            <AnimatePresence mode="popLayout" initial={false}>
              <Etykieta w={w} />
            </AnimatePresence>
            <span className="d-wynik-bylo">{bylo}</span>
          </span>
        </div>
      ))}
      <button type="button" className="a-demo-guzik" onClick={() => setRozliczony((r) => !r)}>
        {rozliczony ? "Cofnij rozliczenie" : "Rozlicz ostatni mecz"}
      </button>
    </div>
  );
}

/* ======================================================================
   2.8 BŁYSK – na kafelkach kursu i szansie jednocześnie
   ====================================================================== */

const ZMIANY = [0, 0.05, -0.04, 0.08, -0.02];

export function BlyskD({ typy }: { typy: TypV[] }) {
  const [krok, setKrok] = useState(0);
  const kursy: Kurs[] = typy.map((t, i) => {
    const teraz = +(t.kurs + ZMIANY[(krok + i) % ZMIANY.length]).toFixed(2);
    const przed = +(t.kurs + ZMIANY[(krok + i - 1 + ZMIANY.length) % ZMIANY.length]).toFixed(2);
    return {
      kurs: teraz,
      bukmacher: t.bukmacher,
      zmiana: krok === 0 || teraz === przed ? null : teraz > przed ? "gora" : "dol",
    };
  });
  const p = (typy[0].szansa + [0, 0.02, -0.03, 0.04, -0.01][krok % 5]).toFixed(2);
  const pPrzed = (typy[0].szansa + [0, 0.02, -0.03, 0.04, -0.01][(krok + 4) % 5]).toFixed(2);

  return (
    <div className="a-scena">
      <div className="a-rzad" style={{ gap: 28, alignItems: "flex-end" }}>
        <div>
          <div className="a-podpis">szansa</div>
          <div className="d-szansa-liczba">
            <Blysk tekst={`${Math.round(Number(p) * 100)}%`} kier={krok === 0 || p === pPrzed ? null : p > pPrzed ? "gora" : "dol"} />
          </div>
        </div>
        {kursy.map((k, i) => (
          <div key={i}>
            <div className="a-podpis">{typy[i].kto.split(" ").slice(-1)[0]}</div>
            <KafelekD k={k} blysk={`${krok}-${i}`} />
          </div>
        ))}
      </div>
      <button type="button" className="a-demo-guzik" onClick={() => setKrok((x) => x + 1)}>
        Symuluj przeliczenie
      </button>
    </div>
  );
}
