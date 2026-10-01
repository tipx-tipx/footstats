"use client";

import { AnimatePresence, LayoutGroup, motion, MotionConfig } from "framer-motion";
import Link from "next/link";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent as KE } from "react";

import "../../atomy.css";
import "../../atomy2.css";
import "../../elementy.css";
import "../../szkielet.css";

import type { DaneElementow } from "../../_dane/elementy";
import type { DruzynaV } from "../../_dane/przygotuj";
import { Sekcja, type WariantAtomu } from "../atomy/wspolne";
import { KafelekD, SzansaD } from "../atomy2/podstawowe";
import { Herb } from "../Herb";
import { LogoPoziome } from "../LogoPoziome";
import { IkonaMotyw, IkonaNav, IkonaSzukaj, IkonaWyloguj, type KluczNav } from "./ikonyNav";

type Motyw = "ciemny" | "jasny";
const PALETA: Record<Motyw, string> = { ciemny: "b1", jasny: "p3" };
export type Stan = "swieze" | "stare" | "awaria" | "offline";

const MENU: { k: KluczNav; label: string; grupa: 1 | 2 }[] = [
  { k: "zawodnicy", label: "Zawodnicy", grupa: 1 },
  { k: "druzyny", label: "Drużyny", grupa: 1 },
  { k: "kupony", label: "Kupony", grupa: 1 },
  { k: "mecze", label: "Mecze", grupa: 1 },
  { k: "skutecznosc", label: "Wyniki", grupa: 2 },
  { k: "jak", label: "Jak czytać typy", grupa: 2 },
];

const TYTULY: Record<string, [string, string]> = {
  zawodnicy: ["Zawodnicy", "Strzały, faule i kartki zawodników – nasze najmocniejsze typy na dziś."],
  druzyny: ["Drużyny", "Gole, rożne i kartki całych drużyn."],
  kupony: ["Kupony", "Wybierz, ile chcesz wygrać. Resztę dobierzemy."],
  mecze: ["Mecze", "Najbliższe mecze, które już przeliczyliśmy."],
  skutecznosc: ["Wyniki", "Każdy typ zostaje w historii – także te, które nie weszły."],
  jak: ["Jak czytać typy", "Co znaczą liczby przy typie – krótko i na przykładach."],
};

const norm = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l");

/* ---- świeżość danych -------------------------------------------------- */

export function Swiezosc({ stan, krotko = false, tekst }: { stan: Stan; krotko?: boolean; tekst?: { przedrostek: string; rdzen: string; opis: string } }) {
  // przedrostek chowa się na węższych ekranach (zostaje sama godzina/czas)
  const [przedrostek, rdzen] = tekst ? [tekst.przedrostek, tekst.rdzen] : { swieze: ["kursy z ", "22:28"], stare: ["kursy sprzed ", "5 h"], awaria: ["dane sprzed ", "2 dni"], offline: ["offline · ", "22:28"] }[stan];
  const opis = {
    swieze: "Kursy i typy przeliczone o 22:28. Odświeżamy co godzinę.",
    stare: "Od 5 godzin nie mamy świeżych kursów – sprawdź kurs u bukmachera przed postawieniem.",
    awaria: "Dane nie odświeżają się od 2 dni. Typy mogą być nieaktualne.",
    offline: "Brak internetu – widzisz typy i kursy z 22:28.",
  }[stan];
  const opisDo = tekst?.opis ?? opis;
  return (
    <span className="s-swiezosc" data-stan={stan} title={opisDo}>
      <i aria-hidden />
      {!krotko && <span className="s-sw-przedrostek">{przedrostek}</span>}
      {rdzen}
    </span>
  );
}

function BanerAwarii() {
  return (
    <div className="s-baner-awarii" role="status">
      <span>
        <b>Dane nie odświeżają się od 2 dni.</b> Typy poniżej mogą być nieaktualne – wrócimy, gdy tylko źródło zacznie odpowiadać.
      </span>
    </div>
  );
}

/* ---- treść przykładowa ------------------------------------------------ */

function Tresc({ dane, aktywna, stan }: { dane: DaneElementow; aktywna: string; stan: Stan }) {
  const [tytul, opis] = TYTULY[aktywna] ?? TYTULY.zawodnicy;
  return (
    <main className="s-tresc">
      {stan === "awaria" && <BanerAwarii />}
      <h1 className="p-n">{tytul}</h1>
      <p>{opis}</p>
      <div className="s-lista">
        {dane.wszystkie.slice(0, 9).map((t) => (
          <div key={t.id} className="e-wiersz">
            <div style={{ minWidth: 0 }}>
              <div className="a-typ-kto" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {t.kto}
              </div>
              <div className="a-typ-co" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {t.opis}
              </div>
            </div>
            <SzansaD p={t.p} mala />
            <KafelekD k={{ kurs: t.kurs, bukmacher: t.bukmacher }} />
          </div>
        ))}
      </div>
    </main>
  );
}

/* ---- szukaj z każdego miejsca (Ctrl+K) -------------------------------- */

export function Paleta({ dane, zamknij }: { dane: DaneElementow; zamknij: () => void }) {
  const [q, setQ] = useState("");
  const [i, setI] = useState(0);
  const pole = useRef<HTMLInputElement>(null);
  useEffect(() => pole.current?.focus(), []);

  const wyniki = useMemo(() => {
    const n = norm(q);
    const kto = new Map<string, number>();
    for (const t of dane.wszystkie) if (!n || norm(t.kto).includes(n)) kto.set(t.kto, (kto.get(t.kto) ?? 0) + 1);
    type Wynik = { grupa: string; nazwa: string; opis: string; herby?: [DruzynaV, DruzynaV] };
    const ludzie: Wynik[] = [...kto.entries()].slice(0, 5).map(([nazwa, ile]) => ({ grupa: "Zawodnicy i drużyny", nazwa, opis: `${ile} ${ile === 1 ? "typ" : ile < 5 ? "typy" : "typów"}` }));
    const mecze = dane.meczeE
      .filter((m) => !n || norm(`${m.gosp.nazwa} ${m.gosc.nazwa}`).includes(n))
      .slice(0, 4)
      .map((m): Wynik => ({ grupa: "Mecze", nazwa: `${m.gosp.nazwa} – ${m.gosc.nazwa}`, opis: `${m.dzien}, ${m.godzina}`, herby: [m.gosp, m.gosc] }));
    return [...ludzie, ...mecze];
  }, [q, dane]);

  const klawisze = (e: KE) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setI((x) => Math.min(x + 1, wyniki.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setI((x) => Math.max(x - 1, 0));
    } else if (e.key === "Escape" || e.key === "Enter") zamknij();
  };

  return (
    <motion.div className="s-paleta-tlo" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={zamknij}>
      <motion.div
        className="s-paleta"
        role="dialog"
        aria-label="Szukaj"
        initial={{ y: -10, scale: 0.98 }}
        animate={{ y: 0, scale: 1 }}
        exit={{ y: -10, scale: 0.98 }}
        transition={{ duration: 0.16 }}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={klawisze}
      >
        <div className="s-paleta-pole">
          <IkonaSzukaj r={18} />
          <input
            ref={pole}
            value={q}
            placeholder="Zawodnik, drużyna, mecz…"
            aria-label="Szukaj"
            onChange={(e) => {
              setQ(e.target.value);
              setI(0);
            }}
          />
        </div>
        <div className="s-paleta-wyniki" role="listbox">
          {wyniki.length === 0 && <div className="s-paleta-grupa">Nic nie znaleźliśmy</div>}
          {wyniki.map((w, j) => (
            <div key={`${w.grupa}-${w.nazwa}`}>
              {(j === 0 || wyniki[j - 1].grupa !== w.grupa) && <div className="s-paleta-grupa">{w.grupa}</div>}
              <button type="button" role="option" aria-selected={j === i} className="s-paleta-poz" onMouseEnter={() => setI(j)} onClick={zamknij}>
                {w.herby ? (
                  <span style={{ display: "inline-flex", gap: 3 }}>
                    <Herb d={w.herby[0]} tryb="prawdziwy" rozmiar={16} />
                    <Herb d={w.herby[1]} tryb="prawdziwy" rozmiar={16} />
                  </span>
                ) : (
                  <IkonaNav klucz="zawodnicy" rozmiar={16} />
                )}
                {w.nazwa}
                <small>{w.opis}</small>
              </button>
            </div>
          ))}
        </div>
        <div className="s-paleta-stopka">
          <span>
            <kbd>↑↓</kbd>wybierz
          </span>
          <span>
            <kbd>Enter</kbd>otwórz
          </span>
          <span>
            <kbd>Esc</kbd>zamknij
          </span>
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ---- 4.1 menu na komputerze ------------------------------------------- */

export function PrawaStrona({
  motyw,
  zmienMotyw,
  stan,
  szukaj,
  bok = false,
}: {
  motyw: Motyw;
  zmienMotyw: () => void;
  stan: Stan;
  szukaj: () => void;
  bok?: boolean;
}) {
  return (
    <div className={bok ? "s-prawa-bok" : "s-prawa"}>
      <button type="button" className="s-szukaj" onClick={szukaj} aria-label="Szukaj (Ctrl+K)">
        <IkonaSzukaj />
        <span>Szukaj</span>
        <kbd>Ctrl K</kbd>
      </button>
      <Swiezosc stan={stan} />
      <button type="button" className="s-ikona-guzik" aria-label="Zmień motyw" onClick={zmienMotyw}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={motyw}
            style={{ display: "grid" }}
            initial={{ rotate: -40, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            exit={{ rotate: 40, opacity: 0 }}
            transition={{ duration: 0.18 }}
          >
            <IkonaMotyw ciemny={motyw === "ciemny"} />
          </motion.span>
        </AnimatePresence>
      </button>
      <button type="button" className="s-ikona-guzik" aria-label="Wyloguj">
        <IkonaWyloguj />
      </button>
    </div>
  );
}

/* A+ (dopracowane 01.10): liczby przy pozycjach, zwężenie po przewinięciu,
   kreska-podpowiedź przy najechaniu, cienki pasek ładowania po kliknięciu */
export function MenuKomputerPlus({
  aktywna,
  ustaw,
  prawa,
  jasneLogo,
  liczby,
  children,
}: {
  aktywna: string;
  ustaw: (k: string) => void;
  prawa: React.ReactNode;
  jasneLogo: boolean;
  liczby: Partial<Record<KluczNav, number>>;
  children: React.ReactNode;
}) {
  const id = useId();
  const pasek = useRef<HTMLElement>(null);
  const [zwezony, setZwezony] = useState(false);
  const [laduje, setLaduje] = useState(0);

  // zwężenie po przewinięciu – w podglądzie przewija się okno, na stronie sam dokument
  useEffect(() => {
    const okno = pasek.current?.closest(".s-okno");
    if (!okno) return;
    const zmierz = () => setZwezony(okno.scrollTop > 12);
    okno.addEventListener("scroll", zmierz, { passive: true });
    return () => okno.removeEventListener("scroll", zmierz);
  }, []);

  const kliknij = (k: string) => {
    if (k === aktywna) return;
    ustaw(k);
    setLaduje((x) => x + 1);
  };

  return (
    <>
      <header ref={pasek} className="s-pasek-a s-pasek-plus" data-zwezony={zwezony || undefined}>
        <LogoPoziome jasne={jasneLogo} wysokosc={zwezony ? 24 : 27} />
        <LayoutGroup id={id}>
          <nav className="s-menu-a" aria-label="Menu">
            {MENU.map((m, i) => (
              <span key={m.k} style={{ display: "contents" }}>
                {i === 4 && <span className="s-separator" aria-hidden />}
                <a className="s-poz-a s-poz-plus" aria-current={aktywna === m.k ? "page" : undefined} onClick={() => kliknij(m.k)}>
                  {aktywna === m.k && <motion.span layoutId="kreska-plus" className="s-kreska-a" transition={{ type: "spring", stiffness: 480, damping: 38 }} />}
                  <span style={{ position: "relative" }}>{m.label}</span>
                  {liczby[m.k] ? <sup className="s-licznik-poz">{liczby[m.k]}</sup> : null}
                </a>
              </span>
            ))}
          </nav>
        </LayoutGroup>
        {prawa}
        <AnimatePresence>
          {laduje > 0 && (
            <motion.span
              key={laduje}
              className="s-ladowanie"
              aria-hidden
              initial={{ scaleX: 0, opacity: 1 }}
              animate={{ scaleX: 1, opacity: [1, 1, 0] }}
              transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1], opacity: { times: [0, 0.8, 1], duration: 0.55 } }}
            />
          )}
        </AnimatePresence>
      </header>
      {children}
    </>
  );
}

function MenuKomputer({
  wariant,
  aktywna,
  ustaw,
  prawa,
  jasneLogo,
  children,
}: {
  wariant: string;
  aktywna: string;
  ustaw: (k: string) => void;
  prawa: React.ReactNode;
  jasneLogo: boolean;
  children: React.ReactNode;
}) {
  const id = useId();
  const sprezyna = { type: "spring" as const, stiffness: 480, damping: 38 };

  if (wariant === "c") {
    return (
      <div className="s-uklad-c">
        <aside className="s-bok">
          <LogoPoziome jasne={jasneLogo} wysokosc={24} />
          <LayoutGroup id={id}>
            {[1, 2].map((g) => (
              <nav key={g} className="s-bok-grupa" aria-label={g === 1 ? "Typy" : "Sprawdź nas"}>
                <small>{g === 1 ? "Typy" : "Sprawdź nas"}</small>
                {MENU.filter((m) => m.grupa === g).map((m) => (
                  <a key={m.k} className="s-poz-c" aria-current={aktywna === m.k ? "page" : undefined} onClick={() => ustaw(m.k)}>
                    {aktywna === m.k && <motion.span layoutId="tlo-c" className="s-tlo-c" transition={sprezyna} />}
                    <IkonaNav klucz={m.k} pelna={aktywna === m.k} />
                    {m.label}
                  </a>
                ))}
              </nav>
            ))}
          </LayoutGroup>
          <div className="s-bok-dol">{prawa}</div>
        </aside>
        <div>{children}</div>
      </div>
    );
  }

  const pozycje = (klasa: string, tlo: React.ReactNode) =>
    MENU.map((m, i) => (
      <span key={m.k} style={{ display: "contents" }}>
        {i === 4 && <span className="s-separator" aria-hidden />}
        <a className={klasa} aria-current={aktywna === m.k ? "page" : undefined} onClick={() => ustaw(m.k)}>
          {aktywna === m.k && tlo}
          <span style={{ position: "relative" }}>{m.label}</span>
        </a>
      </span>
    ));

  if (wariant === "b") {
    return (
      <>
        <div className="s-pasek-b-rama">
          <header className="s-pasek-b">
            <LogoPoziome jasne={jasneLogo} wysokosc={24} />
            <LayoutGroup id={id}>
              <nav className="s-menu-b" aria-label="Menu">
                {pozycje("s-poz-b", <motion.span layoutId="tlo-b" className="s-tlo-b" transition={sprezyna} />)}
              </nav>
            </LayoutGroup>
            {prawa}
          </header>
        </div>
        {children}
      </>
    );
  }

  return (
    <>
      <header className="s-pasek-a">
        <LogoPoziome jasne={jasneLogo} wysokosc={24} />
        <LayoutGroup id={id}>
          <nav className="s-menu-a" aria-label="Menu">
            {pozycje("s-poz-a", <motion.span layoutId="kreska-a" className="s-kreska-a" transition={sprezyna} />)}
          </nav>
        </LayoutGroup>
        {prawa}
      </header>
      {children}
    </>
  );
}

/* ---- 4.2 menu na telefonie -------------------------------------------- */

export function MenuTelefon({
  wariant,
  aktywna,
  ustaw,
  motyw,
  zmienMotyw,
  stan,
  szukaj,
  children,
}: {
  wariant: string;
  aktywna: string;
  ustaw: (k: string) => void;
  motyw: Motyw;
  zmienMotyw: () => void;
  stan: Stan;
  szukaj: () => void;
  children: React.ReactNode;
}) {
  const [wiecej, setWiecej] = useState(false);
  const id = useId();
  const sprezyna = { type: "spring" as const, stiffness: 480, damping: 38 };
  const wybierz = (k: string) => {
    ustaw(k);
    setWiecej(false);
  };

  const gora = (
    <header className="s-t-gora">
      <LogoPoziome jasne={motyw === "ciemny"} wysokosc={22} />
      <div className="s-prawa">
        <Swiezosc stan={stan} krotko />
        <button type="button" className="s-ikona-guzik" aria-label="Szukaj" onClick={szukaj}>
          <IkonaSzukaj r={18} />
        </button>
        {wariant === "b" && (
          <button type="button" className="s-ikona-guzik" aria-label={wiecej ? "Zamknij menu" : "Otwórz menu"} aria-expanded={wiecej} onClick={() => setWiecej((w) => !w)}>
            <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden>
              <motion.path d="M3 6h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" animate={wiecej ? { d: "M5 5l10 10" } : { d: "M3 6h14" }} />
              <motion.path d="M3 14h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" animate={wiecej ? { d: "M5 15L15 5" } : { d: "M3 14h14" }} />
            </svg>
          </button>
        )}
      </div>
    </header>
  );

  const dodatki = (
    <>
      <button type="button" className="s-arkusz-poz" onClick={zmienMotyw}>
        <IkonaMotyw ciemny={motyw === "ciemny"} r={20} />
        Motyw
        <small>{motyw === "ciemny" ? "ciemny" : "jasny"}</small>
      </button>
      <button type="button" className="s-arkusz-poz">
        <IkonaWyloguj r={20} />
        Wyloguj
      </button>
    </>
  );

  const pozycjaDolu = (k: KluczNav, label: string, onClick: () => void, aktywny: boolean) => (
    <a key={k} className="s-t-poz" aria-current={aktywny ? "page" : undefined} onClick={onClick}>
      {aktywny && <motion.span layoutId="kreska-t" className="s-t-kreska" transition={sprezyna} />}
      <IkonaNav klucz={k} pelna={aktywny} rozmiar={22} />
      {label}
    </a>
  );
  const wWiecej = aktywna === "skutecznosc" || aktywna === "jak";

  return (
    <div style={{ position: "relative", height: "100%" }}>
      <div className="s-telefon">
        {gora}
        {children}
        {wariant !== "b" && (
          <LayoutGroup id={id}>
            <nav className="s-t-dol" aria-label="Menu">
              {wariant === "c" ? (
                <>
                  {pozycjaDolu("zawodnicy", "Zawodnicy", () => wybierz("zawodnicy"), aktywna === "zawodnicy")}
                  {pozycjaDolu("druzyny", "Drużyny", () => wybierz("druzyny"), aktywna === "druzyny")}
                  <a className="s-t-kupon" aria-current={aktywna === "kupony" ? "page" : undefined} onClick={() => wybierz("kupony")}>
                    <span className="s-t-kupon-kolo">
                      <IkonaNav klucz="kupony" pelna rozmiar={24} />
                    </span>
                    Kupon
                  </a>
                  {pozycjaDolu("mecze", "Mecze", () => wybierz("mecze"), aktywna === "mecze")}
                  {pozycjaDolu("wiecej", "Więcej", () => setWiecej(true), wWiecej)}
                </>
              ) : (
                <>
                  {MENU.slice(0, 4).map((m) => pozycjaDolu(m.k, m.label, () => wybierz(m.k), aktywna === m.k))}
                  {pozycjaDolu("wiecej", "Więcej", () => setWiecej(true), wWiecej)}
                </>
              )}
            </nav>
          </LayoutGroup>
        )}
      </div>

      <AnimatePresence>
        {wariant !== "b" && wiecej && (
          <>
            <motion.div key="tlo" className="s-arkusz-tlo" style={{ borderRadius: 23 }} onClick={() => setWiecej(false)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            <motion.div
              key="arkusz"
              className="s-arkusz"
              role="dialog"
              aria-label="Więcej"
              initial={{ y: "100%" }}
              animate={{ y: 0 }}
              exit={{ y: "100%" }}
              transition={{ type: "spring", stiffness: 380, damping: 38 }}
              style={{ borderRadius: "18px 18px 23px 23px" }}
            >
              <div className="s-arkusz-uchwyt" aria-hidden />
              {MENU.filter((m) => m.grupa === 2).map((m) => (
                <a key={m.k} className="s-arkusz-poz" aria-current={aktywna === m.k ? "page" : undefined} onClick={() => wybierz(m.k)}>
                  <IkonaNav klucz={m.k} rozmiar={20} />
                  {m.label}
                </a>
              ))}
              {dodatki}
            </motion.div>
          </>
        )}
        {wariant === "b" && wiecej && (
          <motion.div
            key="tlo-b"
            className="s-arkusz-tlo"
            style={{ top: 54, borderRadius: "0 0 23px 23px" }}
            onClick={() => setWiecej(false)}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
        )}
        {wariant === "b" && wiecej && (
          <motion.nav
            key="menu"
            className="s-menu-pelne"
            aria-label="Menu"
            style={{ top: 54 }}
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
          >
            <small>Typy</small>
            {MENU.filter((m) => m.grupa === 1).map((m) => (
              <a key={m.k} className="s-arkusz-poz" aria-current={aktywna === m.k ? "page" : undefined} onClick={() => wybierz(m.k)}>
                <IkonaNav klucz={m.k} pelna={aktywna === m.k} rozmiar={20} />
                {m.label}
              </a>
            ))}
            <small>Sprawdź nas</small>
            {MENU.filter((m) => m.grupa === 2).map((m) => (
              <a key={m.k} className="s-arkusz-poz" aria-current={aktywna === m.k ? "page" : undefined} onClick={() => wybierz(m.k)}>
                <IkonaNav klucz={m.k} pelna={aktywna === m.k} rozmiar={20} />
                {m.label}
              </a>
            ))}
            {dodatki}
          </motion.nav>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ---- 4.5 stopka -------------------------------------------------------- */

/* motyw z logo: rosnąca linia z kropkami – jako grafika w tle stopki */
function LiniaZLogo() {
  const punkty = [
    [0, 88],
    [70, 80],
    [130, 84],
    [200, 62],
    [260, 68],
    [330, 44],
    [400, 50],
    [470, 24],
    [540, 12],
  ];
  return (
    <svg className="s-stopka-linia" viewBox="0 0 560 100" preserveAspectRatio="none" aria-hidden>
      <polyline points={punkty.map((p) => p.join(",")).join(" ")} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      {punkty.slice(1).map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="4" fill="currentColor" />
      ))}
    </svg>
  );
}

/** link w stopce: w aplikacji prawdziwy adres, w warsztacie atrapa */
function LinkStopki({ nazwa, linki }: { nazwa: string; linki?: Record<string, string> }) {
  const href = linki?.[nazwa];
  return href ? <Link href={href}>{nazwa}</Link> : <a>{nazwa}</a>;
}

export function StopkaPlus({ jasneLogo, linki }: { jasneLogo: boolean; linki?: Record<string, string> }) {
  return (
    <footer className="s-stopka-plus">
      <LiniaZLogo />
      <div className="s-stopka-haslo">
        <div>
          <LogoPoziome jasne={jasneLogo} wysokosc={24} />
          <p className="p-n">Sprawdzamy tysiące zakładów. Zostawiamy tylko najmocniejsze.</p>
        </div>
        <dl className="s-stopka-liczby">
          <div>
            <dt>1600+</dt>
            <dd>zakładów sprawdzamy każdego dnia</dd>
          </div>
          <div>
            <dt>0</dt>
            <dd>typów bez uzasadnienia – przy każdym widzisz, co za nim stoi</dd>
          </div>
          <div>
            <dt>50+</dt>
            <dd>rozgrywek z całego świata przeglądamy co tydzień</dd>
          </div>
        </dl>
      </div>
      <div className="s-stopka-kolumny">
        <div>
          <h4>Typy</h4>
          <ul>
            <li><LinkStopki nazwa="Zawodnicy" linki={linki} /></li>
            <li><LinkStopki nazwa="Drużyny" linki={linki} /></li>
            <li><LinkStopki nazwa="Kupony" linki={linki} /></li>
            <li><LinkStopki nazwa="Mecze" linki={linki} /></li>
          </ul>
        </div>
        <div>
          <h4>Sprawdź nas</h4>
          <ul>
            <li><LinkStopki nazwa="Wyniki" linki={linki} /></li>
            <li><LinkStopki nazwa="Jak czytać typy" linki={linki} /></li>
          </ul>
        </div>
        <div>
          <h4>Zasady</h4>
          <ul>
            <li>Tylko dla pełnoletnich</li>
            <li>Graj u legalnych bukmacherów</li>
            <li>Stawiaj tyle, ile możesz stracić</li>
          </ul>
        </div>
      </div>
      <div className="s-stopka-dol">
        <span>© 2026 FootStats</span>
        <span className="s-18">
          <b>18+</b> Graj odpowiedzialnie
        </span>
      </div>
    </footer>
  );
}

function Stopka({ wariant, jasneLogo }: { wariant: string; jasneLogo: boolean }) {
  if (wariant === "b2") return <StopkaPlus jasneLogo={jasneLogo} />;
  if (wariant === "b") {
    return (
      <footer className="s-stopka-b">
        <div>
          <LogoPoziome jasne={jasneLogo} wysokosc={22} />
          <p>Typy na zawodników i drużyny, liczone ze statystyk. Codziennie sprawdzamy ponad 1600 zakładów.</p>
        </div>
        <div>
          <h4>Typy</h4>
          <ul>
            <li>Zawodnicy</li>
            <li>Drużyny</li>
            <li>Kupony</li>
            <li>Mecze</li>
          </ul>
        </div>
        <div>
          <h4>Sprawdź nas</h4>
          <ul>
            <li>Skuteczność</li>
            <li>Jak czytać typy</li>
          </ul>
        </div>
        <div className="s-stopka-b-dol">
          <span>© 2026 FootStats</span>
          <span className="s-18">
            <b>18+</b> Graj odpowiedzialnie, u legalnych bukmacherów
          </span>
        </div>
      </footer>
    );
  }
  return (
    <footer className="s-stopka-a">
      <LogoPoziome jasne={jasneLogo} wysokosc={20} />
      <nav>
        <a>Skuteczność</a>
        <a>Jak czytać typy</a>
      </nav>
      <span className="s-18">
        <b>18+</b> Graj odpowiedzialnie
      </span>
    </footer>
  );
}

/* ---- strona warsztatu --------------------------------------------------- */

const SEKCJE: { klucz: string; nr: string; tytul: string; opis: string; warianty: WariantAtomu[] }[] = [
  {
    klucz: "komputer",
    nr: "4.1",
    tytul: "Menu na komputerze",
    opis: "Te same pozycje co dziś (Zawodnicy, Drużyny, Kupony, Mecze | Skuteczność, Jak to działa). Kliknij pozycje – aktywny znacznik przesuwa się między nimi. Przewiń okno: menu zostaje u góry.",
    warianty: [
      {
        id: "a2",
        nazwa: "A+ · Kreska dopracowana",
        opis: "liczby dzisiejszych typów przy pozycjach, pasek zwęża się po przewinięciu, kreska-podpowiedź przy najechaniu, cienki pasek ładowania po kliknięciu, większe logo.",
      },
      { id: "a", nazwa: "A · Kreska", opis: "pełna szerokość, aktywna pozycja podkreślona kreską akcji (jak Superbet i Polymarket); najspokojniejsze." },
      { id: "b", nazwa: "B · Pastylka", opis: "pływający pasek z przesuwanym tłem pod aktywną pozycją – dzisiejszy styl, dopracowany." },
      { id: "c", nazwa: "C · Z boku", opis: "pasek boczny z ikonami i grupami (jak lewa kolumna Superbetu); dużo miejsca na treść w poziomie." },
    ],
  },
  {
    klucz: "telefon",
    nr: "4.2",
    tytul: "Menu na telefonie",
    opis: "Na telefonie liczy się kciuk. Kliknij „Więcej” albo ikonę menu.",
    warianty: [
      { id: "a", nazwa: "A · Dolny pasek", opis: "4 główne pozycje + „Więcej” na dole ekranu, jak w aplikacjach Sofascore i Superbetu; wszystko w zasięgu kciuka." },
      { id: "b", nazwa: "B · Menu u góry", opis: "ikona menu w rogu, lista rozwija się z góry – jak dziś, ale czytelniej." },
      { id: "c", nazwa: "C · Kupon w środku", opis: "dolny pasek z wyróżnionym Kuponem na środku – najważniejsza akcja zawsze pod kciukiem." },
    ],
  },
  {
    klucz: "swiezosc",
    nr: "4.3",
    tytul: "Świeżość danych",
    opis: "Jeden znak przy menu mówi, czy kursy są aktualne. Najedź na niego, żeby zobaczyć wyjaśnienie. Przy awarii dochodzi pasek nad treścią.",
    warianty: [
      { id: "swieze", nazwa: "Świeże", opis: "zielona kropka i godzina ostatniego przeliczenia." },
      { id: "stare", nazwa: "Sprzed kilku godzin", opis: "bursztyn: sprawdź kurs u bukmachera przed postawieniem." },
      { id: "awaria", nazwa: "Awaria", opis: "czerwony znak + pasek nad treścią, bez straszenia i bez szczegółów technicznych." },
    ],
  },
  {
    klucz: "stopka",
    nr: "4.4",
    tytul: "Stopka",
    opis: "Na dole każdej strony.",
    warianty: [
      {
        id: "b2",
        nazwa: "B+ · Kolumny dopracowane",
        opis: "hasło (korzyść dla gracza) i trzy prawdziwe liczby, w tle rosnąca linia z kropkami z logo, kolumny Typy / Sprawdź nas / Zasady, na dole © i 18+.",
      },
      { id: "a", nazwa: "A · Jedna linia", opis: "logo, dwa linki i 18+ w jednym rzędzie – nie zabiera miejsca." },
      { id: "b", nazwa: "B · Kolumny", opis: "zdanie o produkcie, linki w grupach, 18+ i odpowiedzialna gra na dole." },
    ],
  },
];

export type StartSzkieletu = Record<string, string | undefined>;

export function Szkielet({ dane, start }: { dane: DaneElementow; start: StartSzkieletu }) {
  const [motyw, setMotyw] = useState<Motyw>(start.m === "jasny" ? "jasny" : "ciemny");
  const [wybory, setWybory] = useState<Record<string, string>>(() =>
    Object.fromEntries(SEKCJE.map((x) => [x.klucz, x.warianty.some((w) => w.id === start[x.klucz]) ? start[x.klucz]! : x.warianty[0].id])),
  );
  const [aktywnaK, setAktywnaK] = useState("zawodnicy");
  const [aktywnaT, setAktywnaT] = useState("zawodnicy");
  const [paleta, setPaleta] = useState<"komputer" | "telefon" | null>(null);

  useEffect(() => {
    window.history.replaceState(null, "", `?${new URLSearchParams({ m: motyw, ...wybory })}`);
  }, [motyw, wybory]);

  // Ctrl+K otwiera szukanie w podglądzie komputera
  useEffect(() => {
    const klaw = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaleta("komputer");
      }
    };
    window.addEventListener("keydown", klaw);
    return () => window.removeEventListener("keydown", klaw);
  }, []);

  const zmienMotyw = () => setMotyw((m) => (m === "ciemny" ? "jasny" : "ciemny"));
  const liczby: Partial<Record<KluczNav, number>> = {
    zawodnicy: dane.wszystkie.filter((t) => !t.druzynowy).length,
    druzyny: dane.wszystkie.filter((t) => t.druzynowy).length,
    mecze: new Set(dane.wszystkie.map((t) => t.mecz)).size,
  };
  const stan = wybory.swiezosc as Stan;

  const scena = (klucz: string, w: string) => {
    if (klucz === "komputer" || klucz === "swiezosc") {
      const wariantMenu = klucz === "komputer" ? w : wybory.komputer;
      const st = klucz === "swiezosc" ? (w as Stan) : "swieze";
      return (
        <div style={{ position: "relative" }}>
          <div className="s-okno">
            {wariantMenu === "a2" ? (
              <MenuKomputerPlus
                jasneLogo={motyw === "ciemny"}
                aktywna={aktywnaK}
                ustaw={setAktywnaK}
                liczby={liczby}
                prawa={<PrawaStrona motyw={motyw} zmienMotyw={zmienMotyw} stan={st} szukaj={() => setPaleta("komputer")} />}
              >
                <Tresc dane={dane} aktywna={aktywnaK} stan={st} />
                <Stopka wariant={wybory.stopka} jasneLogo={motyw === "ciemny"} />
              </MenuKomputerPlus>
            ) : (
            <MenuKomputer
              jasneLogo={motyw === "ciemny"}
              wariant={wariantMenu}
              aktywna={aktywnaK}
              ustaw={setAktywnaK}
              prawa={
                <PrawaStrona bok={wariantMenu === "c"} motyw={motyw} zmienMotyw={zmienMotyw} stan={st} szukaj={() => setPaleta("komputer")} />
              }
            >
              <Tresc dane={dane} aktywna={aktywnaK} stan={st} />
              <Stopka wariant={wybory.stopka} jasneLogo={motyw === "ciemny"} />
            </MenuKomputer>
            )}
          </div>
          <AnimatePresence>{paleta === "komputer" && klucz === "komputer" && <Paleta dane={dane} zamknij={() => setPaleta(null)} />}</AnimatePresence>
        </div>
      );
    }
    if (klucz === "telefon") {
      return (
        <div className="s-telefon-rama">
          <div style={{ position: "relative", height: 740 }}>
            <MenuTelefon
              wariant={w}
              aktywna={aktywnaT}
              ustaw={setAktywnaT}
              motyw={motyw}
              zmienMotyw={zmienMotyw}
              stan={stan}
              szukaj={() => setPaleta("telefon")}
            >
              <Tresc dane={dane} aktywna={aktywnaT} stan={stan} />
              <Stopka wariant={wybory.stopka} jasneLogo={motyw === "ciemny"} />
            </MenuTelefon>
            <AnimatePresence>{paleta === "telefon" && <Paleta dane={dane} zamknij={() => setPaleta(null)} />}</AnimatePresence>
          </div>
        </div>
      );
    }
    return (
      <div className="s-okno" style={{ height: "auto" }}>
        <Stopka wariant={w} jasneLogo={motyw === "ciemny"} />
      </div>
    );
  };

  return (
    <MotionConfig reducedMotion="user">
      <div className="p-pulpit">
        <div className="p-pulpit-wnetrze">
          <div className="p-pulpit-tytul">
            Etap 4 <span>· menu i szkielet strony</span>
          </div>
          <div className="p-wybor">
            <span>motyw</span>
            <div className="p-segmenty" role="group">
              {(["ciemny", "jasny"] as const).map((m) => (
                <button key={m} type="button" aria-pressed={motyw === m} onClick={() => setMotyw(m)}>
                  {m === "ciemny" ? "Ciemny" : "Jasny"}
                </button>
              ))}
            </div>
          </div>
          <div className="p-wybor" style={{ flexWrap: "wrap" }}>
            <span>skocz do</span>
            {SEKCJE.map((x) => (
              <a key={x.klucz} href={`#atom-${x.nr}`} style={{ color: "#aeb4b6", fontSize: 12 }}>
                {x.nr}
              </a>
            ))}
          </div>
        </div>
        <div className="p-pulpit-opis">Szukanie z każdego miejsca: Ctrl+K (albo przycisk „Szukaj” w podglądzie). Wybory zapisują się w adresie strony.</div>
      </div>
      <div className="p-ekran" data-p-motyw={motyw} data-p-paleta={PALETA[motyw]} data-p-font="2c">
        <div className="p-tresc" style={{ maxWidth: 1180 }}>
          {SEKCJE.map((x) => (
            <Sekcja
              key={x.klucz}
              nr={x.nr}
              tytul={x.tytul}
              opis={x.opis}
              warianty={x.warianty}
              wybrany={wybory[x.klucz]}
              zmien={(id) => setWybory((v) => ({ ...v, [x.klucz]: id }))}
            >
              {scena(x.klucz, wybory[x.klucz])}
            </Sekcja>
          ))}
        </div>
      </div>
    </MotionConfig>
  );
}
