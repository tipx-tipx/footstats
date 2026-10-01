"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useId, useRef, useState } from "react";

import { IkonaMotyw } from "../szkielet/ikonyNav";
import { MenuKomputerPlus, MenuTelefon, PrawaStrona } from "../szkielet/Szkielet";
import { Komunikat } from "./Komunikat";
import { LogoAnimowane } from "./znak";

// warsztat i strony systemowe importują te nazwy stąd
export { Komunikat } from "./Komunikat";
export { KONIEC_ZNAKU, LogoAnimowane, ZnakRysowany } from "./znak";

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
  powrot,
}: {
  stan: StanLogowania;
  onWejscie?: () => void;
  autoFokus?: boolean;
  /** aplikacja: prawdziwe sprawdzenie hasła; bez tego – hasło pokazowe warsztatu */
  zaloguj?: (haslo: string) => Promise<WynikLogowania>;
  /** „sesja wygasła”: dokąd wróci po zalogowaniu (np. „strona meczu”); brak = typy na dziś */
  powrot?: string;
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
            {powrot ? (
              <>
                Zaloguj się ponownie – wrócisz tam, gdzie byłeś: <b>{powrot}</b>.
              </>
            ) : (
              "Zaloguj się ponownie – wrócisz do typów na dziś."
            )}
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
  autoFokus,
  tlo,
  liczbyMenu,
  zaloguj,
  poWejsciu,
  powrot,
}: {
  telefon: boolean;
  jasneLogo: boolean;
  stan: StanLogowania;
  motyw: "ciemny" | "jasny";
  zmienMotyw: () => void;
  autoFokus: boolean;
  /** co leży pod rozmytym oknem: aplikacja – szkielet strony (bez hasła typy nie mogą trafić do HTML), warsztat – strona główna */
  tlo?: React.ReactNode;
  liczbyMenu?: { zawodnicy?: number; druzyny?: number };
  zaloguj?: (haslo: string) => Promise<WynikLogowania>;
  /** aplikacja: po otwarciu bramy – przejście tam, skąd przyszedł */
  poWejsciu?: () => void;
  /** opis miejsca powrotu do komunikatu „sesja wygasła” */
  powrot?: string;
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
  const liczby = liczbyMenu ?? {};
  const strona = tlo ?? null;
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
            <Formularz stan={podejscie ? "zwykly" : stan} onWejscie={() => setOtwarte(true)} autoFokus={autoFokus} zaloguj={zaloguj} powrot={powrot} />
            <StopkaLogowania krotka />
          </motion.section>
        )}
      </AnimatePresence>
    </div>
  );
}

/** aplikacja (/login): to samo okno, prawdziwe hasło, szkielet strony pod spodem */
export { NadAplikacja as LogowanieNadAplikacja };
