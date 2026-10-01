"use client";

import { useTeraz } from "../czas";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent as KE } from "react";

import type { TypLekki } from "../../_dane/przygotuj";
import { Krzyzyk, Ptaszek } from "../atomy/wspolne";
import { FlagaLigi } from "../Herb";
import { IkonaKoszulka, IkonaZegar, odm, POLKI, Segment } from "./filtry2";
import { KafelekD, SzansaD } from "./podstawowe";
import { PrzewijanyRzad } from "./PrzewijanyRzad";

/*
 * 2.5 FILTRY v3 – po pytaniu „czy czegoś nie brakuje” (30.09).
 *
 * Cztery pytania gracza i gdzie dostaje odpowiedź:
 *   „mam konkretny mecz / zawodnika / drużynę”   → SZUKAJ (brakowało; najczęstsze)
 *   „lubię ten rynek (strzały, faule, rożne)”    → rząd RYNKÓW nad listą (był schowany w panelu)
 *   „co mogę zagrać teraz”, „czy składy pewne”   → dwa PRZEŁĄCZNIKI
 *   „tylko wysoka szansa / kurs / moje ligi”     → panel FILTRY (rzadziej, więc schowany)
 * Plus: pusty wynik podpowiada, który jeden filtr zdjąć, żeby coś się pojawiło.
 *
 * Cztery rodziny kontrolek, każda wygląda inaczej: pole szukania, okrągłe przełączniki,
 * kwadratowe menu, tekstowe zakładki rynków.
 */


type LigaF = { nazwa: string; kategoria: string; flaga: string | null; id: number | null; c1: string; c2: string };
type Panel = { szansa: string; kurs: string; ligi: Set<string> };
const PUSTY: Panel = { szansa: "0", kurs: "0", ligi: new Set() };
type Szukane = { pole: "kto" | "mecz" | "liga"; wartosc: string } | null;

const SORTY: [string, string][] = [
  ["polecane", "Polecane"],
  ["szansa", "Największa szansa"],
  ["kurs", "Najwyższy kurs"],
  ["godzina", "Najbliższy mecz"],
];

const norm = (s: string) =>
  s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/ł/g, "l")
    .replace(/ø/g, "o");

type Warunki = {
  wkrotce: boolean;
  sklady: boolean;
  rynek: string;
  tekst: string;
  szukane: Szukane;
  panel: Panel;
};

function pasuje(t: TypLekki, w: Warunki, TERAZ: number) {
  if (w.wkrotce && t.ts - TERAZ > 3 * 3600) return false;
  if (w.sklady && !t.sklady) return false;
  if (w.rynek && t.rynek !== w.rynek) return false;
  if (w.szukane) {
    if (t[w.szukane.pole] !== w.szukane.wartosc) return false;
  } else if (w.tekst) {
    const q = norm(w.tekst);
    if (![t.kto, t.mecz, t.liga, t.opis].some((x) => norm(x).includes(q))) return false;
  }
  if (w.panel.ligi.size && !w.panel.ligi.has(t.liga)) return false;
  if (t.p < Number(w.panel.szansa) / 100) return false;
  if (t.kurs < Number(w.panel.kurs) / 100) return false;
  return true;
}

function IkonaLupa() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" aria-hidden>
      <circle cx="6.5" cy="6.5" r="4.6" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="m10 10 3.2 3.2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function FiltryV3({
  wszystkie,
  ligi,
  drabinki,
  telefon,
  wiersz,
  ile: ileStart = 6,
  drabinkaTresc,
  grupuj,
  obokPolek,
  bezDrabinek = false,
}: {
  wszystkie: TypLekki[];
  ligi: LigaF[];
  drabinki: number;
  telefon: boolean;
  /** własny wiersz (np. karta typu A) – null = zwykły wiersz */
  wiersz?: (t: TypLekki) => React.ReactNode | null;
  /** ile wierszy pokazać przed „i jeszcze N” */
  ile?: number;
  /** treść zakładki Drabinki */
  drabinkaTresc?: React.ReactNode;
  /** grupy (np. mecz): kolejność grup wg pierwszego typu po sortowaniu */
  grupuj?: { klucz: (t: TypLekki) => string; naglowek: (t: TypLekki, ile: number) => React.ReactNode };
  /** element w jednym rzędzie z półkami (np. dni) – półki stają się wtedy przełącznikiem */
  obokPolek?: React.ReactNode;
  /** strona drużyn: drabinki są tylko dla zawodników */
  bezDrabinek?: boolean;
}) {
  const TERAZ = useTeraz();
  const [ile, setIle] = useState(ileStart);
  const [polka, setPolka] = useState(POLKI[0].klucz);
  const [wkrotce, setWkrotce] = useState(false);
  const [sklady, setSklady] = useState(false);
  const [rynek, setRynek] = useState("");
  const [tekst, setTekst] = useState("");
  const [szukane, setSzukane] = useState<Szukane>(null);
  const [podpowiedzi, setPodpowiedzi] = useState(false);
  const [aktywnaPodp, setAktywnaPodp] = useState(0);
  const [szukajOtwarte, setSzukajOtwarte] = useState(false);
  const [panel, setPanel] = useState<Panel>(PUSTY);
  const [roboczy, setRoboczy] = useState<Panel>(PUSTY);
  const [otwarty, setOtwarty] = useState(false);
  const [sort, setSort] = useState("polecane");
  const [menu, setMenu] = useState(false);

  const panelRef = useRef<HTMLDivElement>(null);
  const przycisk = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLSpanElement>(null);
  const pole = useRef<HTMLInputElement>(null);
  const szukajRef = useRef<HTMLDivElement>(null);
  const idKart = useId();
  const idRynkow = useId();
  const idListy = useId();
  const idPodp = useId();

  const naPolce = useMemo(() => wszystkie.filter((t) => t.polka === polka), [wszystkie, polka]);
  const w: Warunki = { wkrotce, sklady, rynek, tekst, szukane, panel };

  const wynik = useMemo(() => {
    const x = naPolce.filter((t) => pasuje(t, { wkrotce, sklady, rynek, tekst, szukane, panel }, TERAZ));
    if (sort === "szansa") x.sort((a, b) => b.p - a.p);
    if (sort === "kurs") x.sort((a, b) => b.kurs - a.kurs);
    if (sort === "godzina") x.sort((a, b) => a.ts - b.ts);
    if (!grupuj) return x;
    // grupa ląduje tam, gdzie jej najlepszy (pierwszy po sortowaniu) typ
    const g = new Map<string, TypLekki[]>();
    for (const t of x) {
      const k = grupuj.klucz(t);
      if (!g.has(k)) g.set(k, []);
      g.get(k)!.push(t);
    }
    return [...g.values()].flat();
  }, [naPolce, wkrotce, sklady, rynek, tekst, szukane, panel, sort, grupuj, TERAZ]);

  const wGrupie = useMemo(() => {
    const m = new Map<string, number>();
    if (grupuj) for (const t of wynik) m.set(grupuj.klucz(t), (m.get(grupuj.klucz(t)) ?? 0) + 1);
    return m;
  }, [wynik, grupuj]);

  // liczniki rynków: z wszystkimi innymi filtrami, bez samego rynku
  const rynki = useMemo(() => {
    const m = new Map<string, number>();
    for (const t of naPolce) if (pasuje(t, { ...w, rynek: "" }, TERAZ)) m.set(t.rynek, (m.get(t.rynek) ?? 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [naPolce, wkrotce, sklady, tekst, szukane, panel]);
  const bezRynku = rynki.reduce((s, [, n]) => s + n, 0);

  // podpowiedzi szukania: zawodnicy/drużyny, mecze, rozgrywki – z liczbą typów
  const podp = useMemo(() => {
    if (!tekst || szukane) return [];
    const q = norm(tekst);
    const grupa = (pole: "kto" | "mecz" | "liga", naglowek: string) => {
      const m = new Map<string, number>();
      for (const t of naPolce) if (norm(t[pole]).includes(q)) m.set(t[pole], (m.get(t[pole]) ?? 0) + 1);
      return [...m.entries()].slice(0, 4).map(([wartosc, ile]) => ({ pole, naglowek, wartosc, ile }));
    };
    return [...grupa("kto", "Zawodnicy i drużyny"), ...grupa("mecz", "Mecze"), ...grupa("liga", "Rozgrywki")];
  }, [tekst, szukane, naPolce]);

  const wybierzPodp = (i: number) => {
    const p = podp[i];
    if (!p) return;
    setSzukane({ pole: p.pole, wartosc: p.wartosc });
    setTekst(p.wartosc);
    setPodpowiedzi(false);
    pole.current?.blur();
  };

  const klawiszeSzukania = (e: KE<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setAktywnaPodp((i) => Math.min(i + 1, podp.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setAktywnaPodp((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && podp.length) {
      e.preventDefault();
      wybierzPodp(aktywnaPodp);
    } else if (e.key === "Escape") {
      setPodpowiedzi(false);
      if (telefon && !tekst) setSzukajOtwarte(false);
    }
  };

  const wyczyscSzukanie = () => {
    setTekst("");
    setSzukane(null);
    setAktywnaPodp(0);
  };

  // „/” skacze do szukania (komputer), Escape/klik obok zamyka menu i dymki
  useEffect(() => {
    const klaw = (e: KeyboardEvent) => {
      const cel = e.target as HTMLElement;
      if (e.key === "/" && !["INPUT", "TEXTAREA"].includes(cel.tagName)) {
        e.preventDefault();
        setSzukajOtwarte(true);
        pole.current?.focus();
      }
      if (e.key === "Escape") {
        setOtwarty(false);
        setMenu(false);
      }
    };
    const klik = (e: MouseEvent) => {
      const c = e.target as Node;
      if (menuRef.current && !menuRef.current.contains(c)) setMenu(false);
      if (szukajRef.current && !szukajRef.current.contains(c)) setPodpowiedzi(false);
      if (!telefon && panelRef.current && !panelRef.current.contains(c) && !przycisk.current?.contains(c)) setOtwarty(false);
    };
    document.addEventListener("keydown", klaw);
    document.addEventListener("mousedown", klik);
    return () => {
      document.removeEventListener("keydown", klaw);
      document.removeEventListener("mousedown", klik);
    };
  }, [telefon]);

  const aktywne: { etykieta: string; usun: () => void }[] = [
    ...(szukane || tekst ? [{ etykieta: `„${tekst}”`, usun: wyczyscSzukanie }] : []),
    ...(panel.szansa !== "0" ? [{ etykieta: `szansa od ${panel.szansa}%`, usun: () => setPanel((x) => ({ ...x, szansa: "0" })) }] : []),
    ...(panel.kurs !== "0"
      ? [{ etykieta: `kurs od ${(Number(panel.kurs) / 100).toFixed(2).replace(".", ",")}`, usun: () => setPanel((x) => ({ ...x, kurs: "0" })) }]
      : []),
    ...[...panel.ligi].map((l) => ({
      etykieta: l,
      usun: () => setPanel((x) => ({ ...x, ligi: new Set([...x.ligi].filter((y) => y !== l)) })),
    })),
  ];
  const ilePanel = (panel.szansa !== "0" ? 1 : 0) + (panel.kurs !== "0" ? 1 : 0) + panel.ligi.size;

  // pusty wynik: który JEDEN warunek zdjąć, żeby coś się pojawiło
  const ratunek = useMemo(() => {
    if (wynik.length) return null;
    const proby: { opis: string; w: Warunki; zastosuj: () => void }[] = [
      { opis: "„Wkrótce”", w: { ...w, wkrotce: false }, zastosuj: () => setWkrotce(false) },
      { opis: "„Pewne składy”", w: { ...w, sklady: false }, zastosuj: () => setSklady(false) },
      { opis: `rynku „${rynek}”`, w: { ...w, rynek: "" }, zastosuj: () => setRynek("") },
      { opis: "szukania", w: { ...w, tekst: "", szukane: null }, zastosuj: wyczyscSzukanie },
      { opis: "filtrów z panelu", w: { ...w, panel: PUSTY }, zastosuj: () => setPanel(PUSTY) },
    ].filter((p) => JSON.stringify({ ...p.w, panel: [...p.w.panel.ligi] }) !== JSON.stringify({ ...w, panel: [...w.panel.ligi] }) || p.opis === "filtrów z panelu");
    const oceny = proby
      .map((p) => ({ ...p, ile: naPolce.filter((t) => pasuje(t, p.w, TERAZ)).length }))
      .filter((p) => p.ile > 0)
      .sort((a, b) => b.ile - a.ile);
    return oceny[0] ?? null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wynik.length, naPolce, wkrotce, sklady, rynek, tekst, szukane, panel]);

  const wRoboczym = naPolce.filter((t) => pasuje(t, { ...w, panel: roboczy }, TERAZ)).length;
  const ligiPolki = ligi.filter((l) => naPolce.some((t) => t.liga === l.nazwa));
  const ileLigi = (nazwa: string) => naPolce.filter((t) => t.liga === nazwa && pasuje(t, { ...w, panel: { ...roboczy, ligi: new Set() } }, TERAZ)).length;
  const ileSkladow = naPolce.filter((t) => t.sklady).length;

  const pokazPole = !telefon || szukajOtwarte;

  return (
    <div className="e-rama" style={{ minHeight: otwarty ? (telefon ? 600 : 560) : undefined }}>
      {/* półki – pierwsza wersja kart; z „obokPolek” – jeden rząd z dniami */}
      <div className={obokPolek ? "f-rzad-polek" : undefined} style={obokPolek ? undefined : { display: "contents" }}>
      {obokPolek}
      <LayoutGroup id={idKart}>
        <div className="a-karty-zakladek" role="tablist" aria-label="Rodzaj typów" data-kompakt={obokPolek ? "" : undefined}>
          {POLKI.filter((p) => !bezDrabinek || p.klucz !== "drabinki").map((p) => {
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
                  setRynek("");
                }}
              >
                {p.klucz === polka && (
                  <motion.span layoutId="kreska-karty" className="a-podkreslenie" transition={{ type: "spring", stiffness: 500, damping: 38 }} />
                )}
                <b>
                  {p.nazwa}{" "}
                  <span>
                    {ile}
                    <i> {odm(ile)}</i>
                  </span>
                </b>
                <small>{p.opis}</small>
              </button>
            );
          })}
        </div>
      </LayoutGroup>
      </div>

      {/* pasek: szukaj · przełączniki · menu */}
      <div className="e-pasek f-pasek">
        <div className="e-lewa" style={{ flex: 1 }}>
          {pokazPole ? (
            <div className="f-szukaj" ref={szukajRef}>
              <IkonaLupa />
              <input
                ref={pole}
                type="search"
                role="combobox"
                aria-controls={idPodp}
                value={tekst}
                placeholder={telefon ? "Zawodnik, drużyna, mecz" : "Szukaj zawodnika, drużyny, meczu"}
                aria-label="Szukaj"
                aria-autocomplete="list"
                aria-expanded={podpowiedzi && podp.length > 0}
                autoFocus={telefon && szukajOtwarte}
                onChange={(e) => {
                  setTekst(e.target.value);
                  setSzukane(null);
                  setPodpowiedzi(true);
                  setAktywnaPodp(0);
                }}
                onFocus={() => setPodpowiedzi(true)}
                onKeyDown={klawiszeSzukania}
              />
              {tekst ? (
                <button type="button" className="f-szukaj-x" aria-label="Wyczyść szukanie" onClick={wyczyscSzukanie}>
                  <Krzyzyk rozmiar={9} />
                </button>
              ) : (
                !telefon && <kbd className="f-kbd">/</kbd>
              )}
              <AnimatePresence>
                {podpowiedzi && podp.length > 0 && (
                  <motion.div
                    id={idPodp}
                    className="f-podpowiedzi"
                    role="listbox"
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.12 }}
                  >
                    {podp.map((p, i) => (
                      <div key={`${p.pole}-${p.wartosc}`}>
                        {(i === 0 || podp[i - 1].naglowek !== p.naglowek) && <div className="f-podp-naglowek">{p.naglowek}</div>}
                        <button
                          type="button"
                          role="option"
                          aria-selected={i === aktywnaPodp}
                          className="f-podp"
                          onMouseEnter={() => setAktywnaPodp(i)}
                          onClick={() => wybierzPodp(i)}
                        >
                          <span>{p.wartosc}</span>
                          <small>
                            {p.ile} {odm(p.ile)}
                          </small>
                        </button>
                      </div>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ) : (
            <button type="button" className="e-menu-guzik d-dotyk" aria-label="Szukaj" onClick={() => setSzukajOtwarte(true)}>
              <IkonaLupa />
            </button>
          )}
          {!(telefon && szukajOtwarte) && (
            <>
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
                title={ileSkladow === 0 ? "Składy ogłaszane są ok. godzinę przed meczem" : "Tylko mecze z ogłoszonymi składami"}
              >
                <IkonaKoszulka />
                {telefon ? "Składy" : "Pewne składy"}
              </button>
            </>
          )}
        </div>
        {telefon && szukajOtwarte ? (
          <button
            type="button"
            className="a-guzik"
            data-t="cichy"
            data-r="s"
            onClick={() => {
              setSzukajOtwarte(false);
              wyczyscSzukanie();
            }}
          >
            Anuluj
          </button>
        ) : (
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
              data-aktywny={ilePanel > 0 ? "true" : undefined}
              onClick={() => {
                setRoboczy(panel);
                setOtwarty((o) => !o);
              }}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
                <path d="M2 3.5h10M4 7h6M6 10.5h2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
              <span className="e-etykieta-sortu" style={{ color: "inherit", fontWeight: 600 }}>
                Filtry
              </span>
              {ilePanel > 0 && <span className="a-licznik">{ilePanel}</span>}
            </button>
          </div>
        )}
      </div>

      {/* rynki – najczęstszy filtr, na widoku, pojedynczy wybór jak u Superbetu */}
      {polka !== "drabinki" && (
        <LayoutGroup id={idRynkow}>
          <PrzewijanyRzad className="f-rynki" role="tablist" ariaLabel="Rynek">
            {[["", bezRynku] as [string, number], ...rynki].map(([r, n]) => (
              <button key={r || "wszystkie"} type="button" role="tab" aria-selected={r === rynek} className="f-rynek" onClick={(e) => {
                setRynek(r);
                e.currentTarget.scrollIntoView({ inline: "nearest", block: "nearest", behavior: "smooth" });
              }}>
                {r || "Wszystkie"}
                <sup>{n}</sup>
                {r === rynek && <motion.span layoutId="kreska-rynku" className="a-podkreslenie" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
              </button>
            ))}
          </PrzewijanyRzad>
        </LayoutGroup>
      )}

      <AnimatePresence initial={false}>
        {aktywne.length > 0 && (
          <motion.div className="e-aktywne" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.2 }}>
            <span className="e-aktywne-liczba">
              {wynik.length} z {naPolce.length}
            </span>
            {aktywne.map((a) => (
              <button key={a.etykieta} type="button" className="e-aktywny" onClick={a.usun} aria-label={`Usuń: ${a.etykieta}`}>
                {a.etykieta}
                <Krzyzyk rozmiar={8} />
              </button>
            ))}
            <button
              type="button"
              className="e-wyczysc"
              onClick={() => {
                setPanel(PUSTY);
                wyczyscSzukanie();
              }}
            >
              Wyczyść
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="e-lista">
        {polka === "drabinki" ? (
          (drabinkaTresc ?? (
            <div className="d-pusty">
              <div className="p-n" style={{ fontSize: 17 }}>
                Drabinki mają własny układ
              </div>
              <p>Tu wejdzie karta drabinki z etapu 3.</p>
            </div>
          ))
        ) : wynik.length === 0 ? (
          <div className="d-pusty">
            <div className="p-n" style={{ fontSize: 17 }}>
              Nic tu nie pasuje
            </div>
            <p>
              {ratunek
                ? `Bez ${ratunek.opis} byłoby ${ratunek.ile} ${odm(ratunek.ile)}.`
                : "Zmień filtry albo wybierz inny dzień."}
            </p>
            {ratunek && (
              <button type="button" className="a-guzik" data-t="drugi" data-r="m" onClick={ratunek.zastosuj}>
                Pokaż {ratunek.ile} {odm(ratunek.ile)}
              </button>
            )}
          </div>
        ) : (
          <LayoutGroup id={idListy}>
            <AnimatePresence initial={false}>
              {wynik.slice(0, ile).flatMap((t, i, lista) => {
                const wlasny = wiersz?.(t);
                const kg = grupuj?.klucz(t);
                const naglowek =
                  grupuj && kg !== undefined && (i === 0 || grupuj.klucz(lista[i - 1]) !== kg) ? (
                    <motion.div
                      key={`g-${kg}`}
                      layout="position"
                      className="f-grupa"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ layout: { type: "spring", stiffness: 420, damping: 38 }, opacity: { duration: 0.15 } }}
                    >
                      {grupuj.naglowek(t, wGrupie.get(kg) ?? 0)}
                    </motion.div>
                  ) : null;
                const koniecGrupy = !!grupuj && (i === lista.length - 1 || grupuj.klucz(lista[i + 1]) !== kg);
                const rzad = (() => {
                if (wlasny) {
                  return (
                    <motion.div
                      key={t.id}
                      layout="position"
                      className="f-karta-wiersz"
                      data-w-grupie={grupuj ? "" : undefined}
                      data-koniec-grupy={koniecGrupy ? "" : undefined}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ layout: { type: "spring", stiffness: 420, damping: 38 }, opacity: { duration: 0.15 } }}
                    >
                      {wlasny}
                    </motion.div>
                  );
                }
                return (
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
                    <div className="a-typ-co" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {t.opis} · {t.mecz}
                    </div>
                  </div>
                  <SzansaD p={t.p} mala />
                  <KafelekD k={{ kurs: t.kurs, bukmacher: t.bukmacher }} />
                </motion.div>
                );
                })();
                return naglowek ? [naglowek, rzad] : [rzad];
              })}
            </AnimatePresence>
            {wynik.length > ile && (
              <button type="button" className="f-wiecej" onClick={() => setIle((n) => n + 10)}>
                Pokaż kolejne {Math.min(10, wynik.length - ile)}
                <small>z {wynik.length - ile}</small>
              </button>
            )}
          </LayoutGroup>
        )}
      </div>

      {/* panel: to, co rzadziej – szansa, kurs, rozgrywki */}
      <AnimatePresence>
        {otwarty && telefon && (
          <motion.div key="tlo" className="d-panel-tlo" onClick={() => setOtwarty(false)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
        )}
        {otwarty && (
          <motion.div
            key="panel"
            ref={panelRef}
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
                    const n = ileLigi(l.nazwa);
                    const on = roboczy.ligi.has(l.nazwa);
                    return (
                      <button
                        key={l.nazwa}
                        type="button"
                        className="e-liga"
                        role="checkbox"
                        aria-checked={on}
                        disabled={n === 0 && !on}
                        onClick={() =>
                          setRoboczy((x) => {
                            const s = new Set(x.ligi);
                            if (s.has(l.nazwa)) s.delete(l.nazwa);
                            else s.add(l.nazwa);
                            return { ...x, ligi: s };
                          })
                        }
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
                  setPanel(roboczy);
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
