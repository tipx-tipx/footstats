"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useId, useRef, useState } from "react";

import type { DaneSystemowe } from "../../_dane/systemowe";
import { NapisLogo } from "../LogoPoziome";
import { IkonaMotyw } from "../szkielet/ikonyNav";
import { MenuKomputerPlus, MenuTelefon, PrawaStrona } from "../szkielet/Szkielet";
import { StronaGlowna } from "../strony/StronaGlowna";

/*
 * S.1 Logowanie v2 (po „słabe” z 01.10): bez liczb, profesjonalnie,
 * z charakterem marki. Jedyna grafika to znak z logo – piłka (łuk ze szwami)
 * i wyrastająca z niej linia wykresu z kropkami – narysowany wektorowo, żeby
 * mógł być duży i ostry. Komunikaty zawsze jako ramka z tytułem i opisem:
 * co się stało i co zrobić.
 */

export type StanLogowania = "zwykly" | "sprawdzam" | "blad" | "caps" | "siec" | "wylogowano" | "sesja" | "sukces";

export const STANY_LOGOWANIA: [StanLogowania, string][] = [
  ["zwykly", "Zwykły"],
  ["blad", "Złe hasło"],
  ["caps", "Caps Lock"],
  ["siec", "Brak połączenia"],
  ["wylogowano", "Po wylogowaniu"],
  ["sesja", "Sesja wygasła"],
  ["sprawdzam", "Sprawdzanie"],
  ["sukces", "Zalogowano"],
];

const HASLO_DEMO = "footstats";

/* ---- znak marki: jedno pióro dla całej rodziny ------------------------- */

// geometria w układzie 400 × 340: piłka (środek 170,170, r 150) jak w logo,
// łuk otwarty z prawej-dołu, tam wychodzi linia wykresu
const LUK_OD_DOLU = "M109 307 A150 150 0 1 1 303.6 101.9";
const SZWY = [
  // pięciokąt w środku
  "M140 84 L181.8 114.4 L165.9 163.6 L114.1 163.6 L98.2 114.4 Z",
  // szwy od wierzchołków na zewnątrz
  "M140 84 L140 33",
  "M181.8 114.4 L230.4 98.6",
  "M165.9 163.6 L195.8 204.9",
  "M114.1 163.6 L84.2 204.9",
  "M98.2 114.4 L49.6 98.6",
  // sąsiednie sześciokąty
  "M140 33 L207.6 35 L230.4 98.6 L249.4 163.5 L195.8 204.9 L140 243 L84.2 204.9 L30.6 163.5 L49.6 98.6 L72.4 35 Z",
  "M207.6 35 L240 -10 M249.4 163.5 L320 180 M140 243 L140 330 M30.6 163.5 L-30 180 M72.4 35 L40 -10",
];
const WYKRES: [number, number][] = [
  [102, 300],
  [186, 214],
  [236, 252],
  [288, 176],
  [372, 86],
];
// szwy kończą się na linii wykresu (jak w logo) – przycinamy je wielokątem nad linią
const NAD_LINIA = "M-40 -40 L440 -40 L440 40 L372 86 L288 176 L236 252 L186 214 L102 300 L-40 360 Z";

/*
 * Kolejność jak pióro rysujące logo: łuk piłki jednym pociągnięciem (od dołu,
 * tam gdzie startuje wykres, dookoła do prawej-góry), szwy od środka na
 * zewnątrz, potem wykres odcinek po odcinku – każda kropka wskakuje dokładnie
 * w chwili, gdy linia do niej dochodzi. Raz, przy wejściu. Przy ograniczonym
 * ruchu – od razu gotowe.
 *
 * Rodzina: `logo` (gruba kreska, mały rozmiar), `duzy` (tło i ilustracje),
 * koniec `blad` (wykres urywa się czerwoną pustą kropką), `brak` (urywa się
 * szarą przerywaną kropką – 404 i brak internetu).
 */
const T = { luk: 0, lukCzas: 0.75, szwy: 0.5, wykres: 0.86, odcinek: 0.17 };
const GRUBOSC = {
  logo: { luk: 18, szwy: 14, wykres: 16, kropka: 24 },
  duzy: { luk: 8, szwy: 6, wykres: 8, kropka: 13 },
};

export function ZnakRysowany({
  className,
  styl = "duzy",
  koniec = "pelny",
  start = 0,
  tempo = 1,
  szer,
  wys,
}: {
  className?: string;
  styl?: keyof typeof GRUBOSC;
  koniec?: "pelny" | "blad" | "brak";
  start?: number;
  /** >1 = wolniej (tło rysuje się spokojniej niż logo) */
  tempo?: number;
  szer?: number;
  wys?: number;
}) {
  const id = useId().replace(/:/g, "");
  // initial zawsze ten sam (serwer = przeglądarka, bez rozjazdu hydracji);
  // przy ograniczonym ruchu znak rysuje się w zerowym czasie
  const reduced = useReducedMotion();
  const g = GRUBOSC[styl];
  const d = (s: number) => (reduced ? 0 : start + s * tempo);
  const czasRys = reduced ? 0 : tempo;
  const pelny = koniec === "pelny";
  // przy urwanym wykresie rysujemy dwa odcinki, trzeci jest przerywany
  const punkty = pelny ? WYKRES : WYKRES.slice(0, 3);
  const odcinki = punkty.slice(1).map((p, i) => [punkty[i], p] as const);
  const naRaz = (s: number) => ({ delay: d(s), duration: 0.01 });
  return (
    <svg className={className} width={szer} height={wys} viewBox="0 0 400 340" fill="none" aria-hidden overflow="visible">
      <defs>
        <clipPath id={`${id}-kolo`}>
          <circle cx="170" cy="170" r="146" />
        </clipPath>
        <clipPath id={`${id}-nad`}>
          <path d={NAD_LINIA} />
        </clipPath>
      </defs>
      <motion.path
        className="zn-luk"
        d={LUK_OD_DOLU}
        stroke="currentColor"
        strokeWidth={g.luk}
        strokeLinecap="round"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: 1, opacity: 1 }}
        transition={{ pathLength: { delay: d(T.luk), duration: T.lukCzas * czasRys, ease: [0.65, 0, 0.35, 1] }, opacity: naRaz(T.luk) }}
      />
      <g clipPath={`url(#${id}-kolo)`}>
        <g className="zn-szwy" clipPath={`url(#${id}-nad)`} stroke="currentColor" strokeWidth={g.szwy} strokeLinejoin="round" strokeLinecap="round">
          {SZWY.map((p, i) => (
            <motion.path
              key={i}
              d={p}
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ pathLength: 1, opacity: 1 }}
              transition={{
                pathLength: { delay: d(T.szwy + i * 0.045), duration: (i === 0 ? 0.32 : 0.26) * tempo, ease: "easeOut" },
                opacity: naRaz(T.szwy + i * 0.045),
              }}
            />
          ))}
        </g>
      </g>
      {odcinki.map(([a, b], i) => (
        <motion.line
          key={i}
          className="zn-wykres"
          x1={a[0]}
          y1={a[1]}
          x2={b[0]}
          y2={b[1]}
          stroke="var(--marka)"
          strokeWidth={g.wykres}
          strokeLinecap="round"
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ pathLength: { delay: d(T.wykres + i * T.odcinek), duration: T.odcinek * czasRys, ease: "linear" }, opacity: naRaz(T.wykres + i * T.odcinek) }}
        />
      ))}
      {punkty.slice(1).map(([x, y], i) => (
        <motion.circle
          key={i}
          className="zn-kropka"
          cx={x}
          cy={y}
          r={g.kropka}
          fill="var(--marka)"
          style={{ transformBox: "fill-box", transformOrigin: "center" }}
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ delay: d(T.wykres + (i + 1) * T.odcinek) - 0.02, type: "spring", stiffness: 640, damping: 18 }}
        />
      ))}
      {!pelny && (
        <>
          {/* urwany odcinek: kreski tam, gdzie wykres miał iść dalej */}
          <motion.line
            x1={250}
            y1={232}
            x2={279}
            y2={189}
            stroke="currentColor"
            strokeOpacity="0.5"
            strokeWidth={g.szwy}
            strokeDasharray={`${g.szwy * 0.4} ${g.szwy * 2}`}
            strokeLinecap="round"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: d(T.wykres + 2 * T.odcinek + 0.15), duration: 0.3 }}
          />
          <motion.circle
            cx={288}
            cy={176}
            r={g.kropka - 1}
            fill="var(--tlo)"
            stroke={koniec === "blad" ? "var(--nie)" : "currentColor"}
            strokeOpacity={koniec === "blad" ? 1 : 0.6}
            strokeWidth={g.szwy * 0.7}
            strokeDasharray={koniec === "brak" ? `${g.szwy * 0.8} ${g.szwy * 0.9}` : undefined}
            style={{ transformBox: "fill-box", transformOrigin: "center" }}
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: d(T.wykres + 2 * T.odcinek + 0.35), type: "spring", stiffness: 520, damping: 20 }}
          />
        </>
      )}
      {/* ostatnia kropka raz „odbija” – wykres doszedł na górę */}
      {pelny && (
        <motion.circle
          cx={372}
          cy={86}
          r={g.kropka}
          stroke="var(--marka)"
          strokeWidth={g.szwy * 0.6}
          style={{ transformBox: "fill-box", transformOrigin: "center" }}
          initial={{ scale: 1, opacity: 0 }}
          animate={reduced ? { opacity: 0 } : { scale: [1, 2.4], opacity: [0.6, 0] }}
          transition={{ delay: d(T.wykres + 4 * T.odcinek + 0.1), duration: 0.8, ease: "easeOut" }}
        />
      )}
    </svg>
  );
}

/** czas, w którym znak kończy się rysować (do zgrania napisu i reszty) */
export const KONIEC_ZNAKU = T.wykres + 4 * T.odcinek;

/* ---- komunikat: tytuł + opis, zawsze z ikoną i kolorem znaczenia ------- */

type Rodzaj = "blad" | "uwaga" | "info" | "ok";

function IkonaKomunikatu({ rodzaj }: { rodzaj: Rodzaj }) {
  return (
    <span className="sy-kom-ikona" aria-hidden>
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        {rodzaj === "ok" ? (
          <path d="M2.5 6.3 5 8.6l4.5-5" />
        ) : rodzaj === "info" ? (
          <path d="M6 5.4V9M6 3v.01" />
        ) : (
          <path d="M6 2.6v4M6 9v.01" />
        )}
      </svg>
    </span>
  );
}

export function Komunikat({ rodzaj, tytul, children, maly = false }: { rodzaj: Rodzaj; tytul: string; children?: React.ReactNode; maly?: boolean }) {
  return (
    <motion.div
      className="sy-kom"
      data-rodzaj={rodzaj}
      data-maly={maly || undefined}
      role={rodzaj === "blad" ? "alert" : "status"}
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="sy-kom-w">
        <IkonaKomunikatu rodzaj={rodzaj} />
        <div>
          <b>{tytul}</b>
          {children && <p>{children}</p>}
        </div>
      </div>
    </motion.div>
  );
}

/* ---- formularz ---------------------------------------------------------- */

function IkonaOko({ otwarte }: { otwarte: boolean }) {
  return otwarte ? (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <path d="M3 3l18 18M10.6 5.1A9.8 9.8 0 0 1 12 5c7 0 10 7 10 7a17 17 0 0 1-3.2 4.2M6.6 6.6A16.6 16.6 0 0 0 2 12s3 7 10 7c1.8 0 3.4-.5 4.7-1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ) : (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" strokeLinejoin="round" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function IkonaKlodka() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <rect x="3" y="7" width="10" height="7" rx="2" />
      <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" strokeLinecap="round" />
    </svg>
  );
}

export type WynikLogowania = "ok" | "zle" | "limit" | "siec";

function Formularz({
  stan,
  onWejscie,
  autoFokus = false,
  zaloguj,
}: {
  stan: StanLogowania;
  onWejscie?: () => void;
  autoFokus?: boolean;
  /** aplikacja: prawdziwe sprawdzenie hasła; bez tego – hasło pokazowe warsztatu */
  zaloguj?: (haslo: string) => Promise<WynikLogowania>;
}) {
  const id = useId();
  const pole = useRef<HTMLInputElement>(null);
  // komputer: kursor od razu w polu; telefon: nie – klawiatura nie wyskakuje sama
  useEffect(() => {
    if (autoFokus) pole.current?.focus({ preventScroll: true });
  }, [autoFokus]);
  const reduced = useReducedMotion();
  const zHaslem = ["blad", "caps", "siec", "sprawdzam", "sukces"].includes(stan);
  const [haslo, setHaslo] = useState(zHaslem ? "footstats24" : "");
  const [pokaz, setPokaz] = useState(false);
  const [blad, setBlad] = useState<null | "haslo" | "siec" | "puste" | "limit">(stan === "blad" ? "haslo" : stan === "siec" ? "siec" : null);
  const [caps, setCaps] = useState(stan === "caps");
  const [faza, setFaza] = useState<"nic" | "sprawdzam" | "wchodze">(stan === "sprawdzam" ? "sprawdzam" : stan === "sukces" ? "wchodze" : "nic");
  const [potrzasnij, setPotrzasnij] = useState(0);
  const [baner, setBaner] = useState<StanLogowania | null>(stan === "wylogowano" || stan === "sesja" ? stan : null);

  useEffect(() => {
    if (faza !== "wchodze" || stan === "sukces") return;
    // chwila na „Zalogowano”, potem brama się otwiera (albo, bez rodzica, pokaz wraca)
    const t = setTimeout(() => {
      if (onWejscie) return onWejscie();
      setFaza("nic");
      setHaslo("");
    }, onWejscie ? 520 : 2000);
    return () => clearTimeout(t);
  }, [faza, stan, onWejscie]);

  const wyslij = (e: React.FormEvent) => {
    e.preventDefault();
    if (faza !== "nic") return;
    if (!haslo) {
      setBlad("puste");
      setPotrzasnij((x) => x + 1);
      return;
    }
    setFaza("sprawdzam");
    setBlad(null);
    setBaner(null);
    const wynik = zaloguj ? zaloguj(haslo) : new Promise<WynikLogowania>((ok) => setTimeout(() => ok(haslo === HASLO_DEMO ? "ok" : "zle"), 700));
    void wynik.then((w) => {
      if (w === "ok") return setFaza("wchodze");
      setFaza("nic");
      setBlad(w === "zle" ? "haslo" : w);
      setPotrzasnij((x) => x + 1);
    });
  };
  const klawisz = (e: React.KeyboardEvent) => setCaps(e.getModifierState("CapsLock"));

  return (
    <form className="sy-form" onSubmit={wyslij} noValidate>
      <AnimatePresence initial={false}>
        {baner === "wylogowano" && (
          <Komunikat key="w" rodzaj="ok" tytul="Wylogowano">
            Sesja została zakończona. Zaloguj się ponownie, gdy zechcesz wrócić do typów.
          </Komunikat>
        )}
        {baner === "sesja" && (
          <Komunikat key="s" rodzaj="info" tytul="Sesja wygasła">
            Zaloguj się ponownie – wrócisz do strony, którą oglądałeś: <b>Mecze › Ireland – Austria</b>.
          </Komunikat>
        )}
        {blad === "haslo" && (
          <Komunikat key="h" rodzaj="blad" tytul="Nieprawidłowe hasło">
            Wpisz je dokładnie tak, jak od nas dostałeś – wielkość liter ma znaczenie.
          </Komunikat>
        )}
        {blad === "limit" && (
          <Komunikat key="l" rodzaj="blad" tytul="Za dużo prób">
            Odczekaj kwadrans i spróbuj ponownie – to zabezpieczenie przed zgadywaniem hasła.
          </Komunikat>
        )}
        {blad === "siec" && (
          <Komunikat key="n" rodzaj="blad" tytul="Brak połączenia">
            Nie udało się połączyć z serwerem. Sprawdź internet i spróbuj ponownie.
          </Komunikat>
        )}
      </AnimatePresence>

      <label htmlFor={`${id}-haslo`} className="sy-etykieta">
        Hasło dostępu
      </label>
      <motion.div
        key={potrzasnij}
        className="sy-pole"
        data-blad={blad === "haslo" || blad === "puste" || undefined}
        animate={potrzasnij && !reduced ? { x: [0, -7, 7, -4, 4, 0] } : undefined}
        transition={{ duration: 0.36 }}
      >
        <span className="sy-pole-ikona">
          <IkonaKlodka />
        </span>
        <input
          ref={pole}
          id={`${id}-haslo`}
          type={pokaz ? "text" : "password"}
          value={haslo}
          autoComplete="current-password"
          placeholder="Wpisz hasło"
          aria-invalid={blad === "haslo" || undefined}
          onChange={(e) => {
            setHaslo(e.target.value);
            setBlad(null);
          }}
          onKeyDown={klawisz}
          onKeyUp={klawisz}
          disabled={faza !== "nic"}
        />
        <button type="button" className="sy-oko" aria-label={pokaz ? "Ukryj hasło" : "Pokaż hasło"} aria-pressed={pokaz} onClick={() => setPokaz((p) => !p)}>
          <IkonaOko otwarte={pokaz} />
        </button>
      </motion.div>
      <AnimatePresence initial={false}>
        {blad === "puste" && (
          <Komunikat key="p" rodzaj="blad" tytul="Wpisz hasło" maly>
            Pole jest puste – wpisz hasło, które od nas dostałeś.
          </Komunikat>
        )}
        {caps && (
          <Komunikat key="c" rodzaj="uwaga" tytul="Włączony Caps Lock" maly>
            Hasło rozróżnia wielkie i małe litery.
          </Komunikat>
        )}
      </AnimatePresence>

      <button type="submit" className="a-guzik sy-wejdz" data-t="glowny" data-r="l" data-faza={faza} disabled={faza !== "nic"} aria-busy={faza === "sprawdzam"}>
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span key={faza} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.16 }} className="sy-wejdz-tresc">
            {faza === "sprawdzam" ? (
              <>
                <span className="d-krecik" aria-hidden /> Sprawdzam hasło
              </>
            ) : faza === "wchodze" ? (
              <>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                  <path d="M3.5 8.4 6.6 11.3 12.5 5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Zalogowano – otwieram typy
              </>
            ) : (
              "Zaloguj się"
            )}
          </motion.span>
        </AnimatePresence>
      </button>
      <p className="sy-bez-hasla">
        Nie masz hasła? <span>Otrzymasz je od nas razem z dostępem.</span>
      </p>
    </form>
  );
}

/* ---- logo animowane ------------------------------------------------------ */

export function LogoAnimowane({ jasne, wysokosc = 44, start = 0 }: { jasne: boolean; wysokosc?: number; start?: number }) {
  const reduced = useReducedMotion();
  return (
    <span className="sy-logo-anim" role="img" aria-label="FootStats">
      <ZnakRysowany styl="logo" start={start} szer={Math.round((wysokosc * 400) / 340)} wys={wysokosc} className="sy-logo-anim-znak" />
      <motion.span
        className="sy-logo-anim-napis"
        initial={{ clipPath: "inset(0 100% 0 0)", x: -6 }}
        animate={{ clipPath: "inset(0 0% 0 0)", x: 0 }}
        transition={reduced ? { duration: 0 } : { delay: start + KONIEC_ZNAKU - 0.28, duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
      >
        <NapisLogo jasne={jasne} wysokosc={Math.round(wysokosc * 0.5)} />
      </motion.span>
    </span>
  );
}

/* ---- nagłówek i stopka -------------------------------------------------- */

function StopkaLogowania({ krotka = false }: { krotka?: boolean }) {
  return (
    <footer className="sy-l-stopka">
      <span>
        <i>18+</i> Graj odpowiedzialnie. Typy nie gwarantują wygranej.
      </span>
      {!krotka && <span>© 2026 FootStats</span>}
    </footer>
  );
}

function PrzyciskMotywu({ motyw, zmienMotyw }: { motyw: "ciemny" | "jasny"; zmienMotyw: () => void }) {
  return (
    <button type="button" className="sy-motyw s-ikona-guzik" aria-label={motyw === "ciemny" ? "Włącz jasny motyw" : "Włącz ciemny motyw"} onClick={zmienMotyw}>
      <IkonaMotyw ciemny={motyw === "ciemny"} />
    </button>
  );
}

/* ---- logowanie nad aplikacją (wybrane 01.10: „to jest sztos”) ---------- */

/*
 * Jak Superbet, Sofascore, Polymarket: logujesz się na tle samego produktu.
 * Pod spodem prawdziwa strona Zawodnicy w zatwierdzonym menu – rozmyta, żeby
 * bez hasła nie dało się odczytać typów; na wierzchu okno (telefon: arkusz od
 * dołu, jak kupon). Po poprawnym haśle „brama się otwiera”: okno odpływa,
 * zasłona znika, a tło wyostrza się do pełnej strony.
 *
 * Przy składaniu: rozmycie ukrywa typy tylko wizualnie – na produkcji pod
 * spodem szkielet strony albo wczorajsze rozliczone typy (PLAN.md 01.10).
 */
function NadAplikacja({
  telefon,
  jasneLogo,
  stan,
  motyw,
  zmienMotyw,
  dane,
  autoFokus,
  tlo,
  liczbyMenu,
  zaloguj,
  poWejsciu,
}: {
  telefon: boolean;
  jasneLogo: boolean;
  stan: StanLogowania;
  motyw: "ciemny" | "jasny";
  zmienMotyw: () => void;
  dane?: DaneSystemowe;
  autoFokus: boolean;
  /** aplikacja: szkielet strony zamiast dzisiejszych typów (bez hasła nie mogą trafić do HTML) */
  tlo?: React.ReactNode;
  liczbyMenu?: { zawodnicy?: number; druzyny?: number };
  zaloguj?: (haslo: string) => Promise<WynikLogowania>;
  /** aplikacja: po otwarciu bramy – przejście tam, skąd przyszedł */
  poWejsciu?: () => void;
}) {
  const reduced = useReducedMotion();
  const [otwarte, setOtwarte] = useState(false);
  const [podejscie, setPodejscie] = useState(0);
  // pokaz: po otwarciu bramy wracamy do logowania, żeby dało się obejrzeć jeszcze raz
  useEffect(() => {
    if (!otwarte) return;
    // aplikacja: brama otwarta → strona; warsztat: pokaz wraca po 3 s
    const t = setTimeout(() => {
      if (poWejsciu) return poWejsciu();
      setOtwarte(false);
      setPodejscie((x) => x + 1);
    }, poWejsciu ? 650 : 3200);
    return () => clearTimeout(t);
  }, [otwarte, poWejsciu]);

  const nic = () => undefined;
  const liczby = liczbyMenu ?? (dane ? { zawodnicy: dane.strony.wszystkie.filter((t) => !t.druzynowy).length, druzyny: dane.strony.wszystkie.filter((t) => t.druzynowy).length } : {});
  const strona = tlo ?? (dane ? <StronaGlowna wariant="c" dane={dane.strony} telefon={telefon} /> : null);
  const czas = reduced ? { duration: 0 } : { duration: 0.6, ease: [0.22, 1, 0.36, 1] as const };

  return (
    <div className="sy-ln" data-telefon={telefon || undefined} data-otwarte={otwarte || undefined}>
      <motion.div
        className="sy-ln-tlo"
        aria-hidden={!otwarte}
        inert={!otwarte}
        initial={false}
        animate={otwarte ? { filter: "blur(0px) saturate(1)", scale: 1 } : { filter: "blur(8px) saturate(0.9)", scale: 1.02 }}
        transition={czas}
      >
        {telefon ? (
          <MenuTelefon wariant="a" aktywna="zawodnicy" ustaw={nic} motyw={motyw} zmienMotyw={nic} stan="swieze" szukaj={nic}>
            {strona}
          </MenuTelefon>
        ) : (
          <MenuKomputerPlus aktywna="zawodnicy" ustaw={nic} liczby={liczby} jasneLogo={jasneLogo} prawa={<PrawaStrona motyw={motyw} zmienMotyw={nic} stan="swieze" szukaj={nic} />}>
            {strona}
          </MenuKomputerPlus>
        )}
      </motion.div>
      <motion.div className="sy-ln-zaslona" initial={{ opacity: 0 }} animate={{ opacity: otwarte ? 0 : 1 }} transition={reduced ? { duration: 0 } : { duration: otwarte ? 0.45 : 0.5 }} />
      <AnimatePresence>
        {!otwarte && (
          <motion.section
            key={podejscie}
            className="sy-ln-okno"
            role="dialog"
            aria-modal="true"
            aria-labelledby="sy-ln-tytul"
            initial={telefon ? { y: "100%" } : { opacity: 0, y: 18, scale: 0.98 }}
            animate={telefon ? { y: 0 } : { opacity: 1, y: 0, scale: 1 }}
            exit={telefon ? { y: "100%", transition: { duration: 0.35, ease: [0.4, 0, 1, 1] } } : { opacity: 0, y: -12, scale: 0.97, transition: { duration: 0.3, ease: [0.4, 0, 1, 1] } }}
            transition={{ delay: podejscie ? 0.1 : 0.25, type: "spring", stiffness: 380, damping: 34 }}
          >
            {telefon && <span className="sy-ln-uchwyt" aria-hidden />}
            <header className="sy-ln-glowa">
              <LogoAnimowane jasne={jasneLogo} wysokosc={telefon ? 30 : 34} start={podejscie ? 0.2 : 0.45} />
              <PrzyciskMotywu motyw={motyw} zmienMotyw={zmienMotyw} />
            </header>
            <div className="sy-l-naglowek" id="sy-ln-tytul">
              <h1 className="p-n">Zaloguj się</h1>
              <p>
                <span>Wpisz hasło, które od nas dostałeś.</span> <span>Typy na dziś czekają pod spodem.</span>
              </p>
            </div>
            <Formularz stan={podejscie ? "zwykly" : stan} onWejscie={() => setOtwarte(true)} autoFokus={autoFokus} zaloguj={zaloguj} />
            <StopkaLogowania krotka />
          </motion.section>
        )}
      </AnimatePresence>
    </div>
  );
}

/** aplikacja (/login): to samo okno, prawdziwe hasło, szkielet strony pod spodem */
export { NadAplikacja as LogowanieNadAplikacja };

export function Logowanie({
  telefon,
  jasneLogo,
  stan,
  motyw,
  zmienMotyw,
  dane,
  autoFokus = false,
}: {
  telefon: boolean;
  jasneLogo: boolean;
  stan: StanLogowania;
  motyw: "ciemny" | "jasny";
  zmienMotyw: () => void;
  dane: DaneSystemowe;
  /** kursor w polu od razu – tylko na pełnym ekranie komputera */
  autoFokus?: boolean;
}) {
  return <NadAplikacja telefon={telefon} jasneLogo={jasneLogo} stan={stan} motyw={motyw} zmienMotyw={zmienMotyw} dane={dane} autoFokus={autoFokus} />;
}
