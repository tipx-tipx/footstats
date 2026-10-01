"use client";

import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";

import "../../atomy.css";
import "../../atomy2.css";
import "../../elementy.css";
import "../../szkielet.css";

import { LogoPoziome } from "../LogoPoziome";
import { przelaczMotyw, useCiemny } from "../motyw";
import { RUCH } from "../ruch/slownik";
import { IkonaMotyw, IkonaNav, IkonaSzukaj, IkonaWyloguj, type KluczNav } from "./ikonyNav";
import { PasekPolaczenia, usePolaczenie } from "../systemowe/Polaczenie";
import { PaletaAplikacji, type IndeksSzukania } from "./PaletaAplikacji";
import { StopkaPlus, Swiezosc, type Stan } from "./Szkielet";

/*
 * Etap 7.2 – szkielet PRAWDZIWEJ aplikacji na zatwierdzonych klockach
 * z etapu 4 (menu A+ z kreską, dolny pasek na telefonie, stopka B+,
 * świeżość). W warsztacie te same style żyją w ramkach podglądu; tu:
 * prawdziwe linki, aktywna pozycja z adresu, przewijanie całej strony,
 * prawdziwy motyw (html[data-theme]) i wylogowanie.
 */

const MENU: { k: KluczNav; label: string; href: string; grupa: 1 | 2 }[] = [
  { k: "zawodnicy", label: "Zawodnicy", href: "/", grupa: 1 },
  { k: "druzyny", label: "Drużyny", href: "/druzyny", grupa: 1 },
  { k: "kupony", label: "Kupony", href: "/kupony", grupa: 1 },
  { k: "mecze", label: "Mecze", href: "/mecze", grupa: 1 },
  { k: "skutecznosc", label: "Wyniki", href: "/model", grupa: 2 },
  { k: "jak", label: "Jak czytać typy", href: "/jak-to-dziala", grupa: 2 },
];

export { przelaczMotyw, useCiemny };

export const LINKI_STOPKI: Record<string, string> = Object.fromEntries(MENU.map((m) => [m.label, m.href]));

const aktywnaZAdresu = (sciezka: string): KluczNav | "" => {
  const m = [...MENU].reverse().find((x) => (x.href === "/" ? sciezka === "/" : sciezka.startsWith(x.href)));
  return m?.k ?? "";
};

/* ---- świeżość: z czasu ostatniego cyklu ---------------------------------- */

function useSwiezosc(ts: number) {
  // zegar dopiero po zamontowaniu – inaczej serwer i przeglądarka różnią się o sekundy
  const [teraz, setTeraz] = useState<number | null>(null);
  useEffect(() => {
    const t = () => setTeraz(Math.floor(Date.now() / 1000));
    t();
    const i = setInterval(t, 60_000);
    return () => clearInterval(i);
  }, []);
  const godz = new Intl.DateTimeFormat("pl-PL", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Warsaw" }).format(new Date(ts * 1000));
  const wiekH = teraz === null ? 0 : (teraz - ts) / 3600;
  const stan: Stan = wiekH <= 2 ? "swieze" : wiekH <= 24 ? "stare" : "awaria";
  const tekst =
    stan === "swieze"
      ? { przedrostek: "kursy z ", rdzen: godz, opis: `Kursy i typy przeliczone o ${godz}. Odświeżamy co godzinę.` }
      : stan === "stare"
        ? { przedrostek: "kursy sprzed ", rdzen: `${Math.round(wiekH)} h`, opis: `Od ${Math.round(wiekH)} h nie mamy świeżych kursów – sprawdź kurs u bukmachera przed postawieniem.` }
        : { przedrostek: "dane sprzed ", rdzen: `${Math.round(wiekH / 24)} dni`, opis: `Dane nie odświeżają się od ${Math.round(wiekH / 24)} dni. Typy mogą być nieaktualne.` };
  return { stan, tekst, godz };
}

/* ---- szkielet ---------------------------------------------------------------- */

export function SzkieletAplikacji({
  liczby,
  wygenerowanoTs,
  indeks,
  rozgrywek,
  children,
}: {
  liczby: Partial<Record<KluczNav, number>>;
  wygenerowanoTs: number;
  /** wyszukiwarka Ctrl+K: zawodnicy z typami, drużyny, mecze */
  indeks: IndeksSzukania;
  /** stopka: rozgrywki w ofercie na najbliższe 7 dni */
  rozgrywek: number;
  children: React.ReactNode;
}) {
  const sciezka = usePathname();
  const router = useRouter();
  const aktywna = aktywnaZAdresu(sciezka);
  const ciemny = useCiemny();
  const sw = useSwiezosc(wygenerowanoTs);
  const id = useId();
  const [zwezony, setZwezony] = useState(false);
  const [laduje, setLaduje] = useState(0);
  const [wiecej, setWiecej] = useState(false);
  const [szukaj, setSzukaj] = useState(false);
  const [szukajStart, setSzukajStart] = useState("");
  const polaczenie = usePolaczenie();

  // szukanie z treści strony (404: słowo z adresu)
  useEffect(() => {
    const otworz = (e: Event) => {
      setSzukajStart(String((e as CustomEvent).detail ?? ""));
      setSzukaj(true);
    };
    window.addEventListener("footstats:szukaj", otworz);
    return () => window.removeEventListener("footstats:szukaj", otworz);
  }, []);

  // po powrocie zasięgu – świeże typy i kursy
  useEffect(() => {
    if (polaczenie === "wrocil") router.refresh();
  }, [polaczenie, router]);

  // Ctrl+K / ⌘K – szukaj z każdego miejsca
  useEffect(() => {
    const klaw = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSzukajStart("");
        setSzukaj(true);
      }
    };
    window.addEventListener("keydown", klaw);
    return () => window.removeEventListener("keydown", klaw);
  }, []);

  useEffect(() => {
    const zmierz = () => setZwezony(window.scrollY > 12);
    zmierz();
    window.addEventListener("scroll", zmierz, { passive: true });
    return () => window.removeEventListener("scroll", zmierz);
  }, []);

  const klik = (href: string) => {
    setWiecej(false);
    if (href !== sciezka) setLaduje((x) => x + 1);
  };
  const wyloguj = async () => {
    await fetch("/api/login", { method: "DELETE" }).catch(() => null);
    router.replace("/login?stan=wylogowano");
    router.refresh();
  };

  // bez internetu znacznik świeżości mówi wprost, z której godziny są dane
  const swStan: Stan = polaczenie === "brak" ? "offline" : sw.stan;
  const swTekst = polaczenie === "brak" ? { przedrostek: "offline · ", rdzen: sw.godz, opis: `Brak internetu – widzisz typy i kursy z ${sw.godz}.` } : sw.tekst;

  const prawa = (
    <div className="s-prawa">
      <button type="button" className="s-szukaj" onClick={() => {
          setSzukajStart("");
          setSzukaj(true);
        }} aria-label="Szukaj (Ctrl+K)">
        <IkonaSzukaj />
        <span>Szukaj</span>
        <kbd>Ctrl K</kbd>
      </button>
      <Swiezosc stan={swStan} tekst={swTekst} />
      <button type="button" className="s-ikona-guzik" aria-label={ciemny ? "Włącz jasny motyw" : "Włącz ciemny motyw"} onClick={przelaczMotyw}>
        <IkonaMotyw ciemny={ciemny} />
      </button>
      <button type="button" className="s-ikona-guzik" aria-label="Wyloguj" onClick={wyloguj}>
        <IkonaWyloguj />
      </button>
    </div>
  );

  return (
    <div className="nowa ap">
      {/* komputer: menu A+ z kreską */}
      <header className="s-pasek-a s-pasek-plus ap-komp" data-zwezony={zwezony || undefined}>
        <Link href="/" aria-label="FootStats – strona główna" onClick={() => klik("/")}>
          <LogoPoziome jasne={ciemny} wysokosc={zwezony ? 24 : 27} />
        </Link>
        <LayoutGroup id={id}>
          <nav className="s-menu-a" aria-label="Menu">
            {MENU.map((m, i) => (
              <span key={m.k} style={{ display: "contents" }}>
                {i === 4 && <span className="s-separator" aria-hidden />}
                <Link href={m.href} className="s-poz-a s-poz-plus" aria-current={aktywna === m.k ? "page" : undefined} onClick={() => klik(m.href)}>
                  {aktywna === m.k && <motion.span layoutId="kreska-ap" className="s-kreska-a" transition={RUCH.sprezyna.znacznik} />}
                  <span style={{ position: "relative" }}>{m.label}</span>
                  {liczby[m.k] ? <sup className="s-licznik-poz">{liczby[m.k]}</sup> : null}
                </Link>
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
              transition={{ duration: 0.55, ease: RUCH.krzywa.hamuje, opacity: { times: [0, 0.8, 1], duration: 0.55 } }}
            />
          )}
        </AnimatePresence>
      </header>

      {/* telefon: górny pasek */}
      <header className="s-t-gora ap-tel">
        <Link href="/" aria-label="FootStats – strona główna">
          <LogoPoziome jasne={ciemny} wysokosc={22} />
        </Link>
        <div className="s-prawa">
          <Swiezosc stan={swStan} tekst={swTekst} krotko />
          <button type="button" className="s-ikona-guzik" aria-label="Szukaj" onClick={() => {
          setSzukajStart("");
          setSzukaj(true);
        }}>
            <IkonaSzukaj r={18} />
          </button>
        </div>
      </header>

      <PasekPolaczenia stan={polaczenie} godz={sw.godz} />

      {sw.stan === "awaria" && polaczenie !== "brak" && (
        <div className="ap-baner" role="status">
          <div className="s-baner-awarii">
            <span>
              <b>{sw.tekst.opis.split(".")[0]}.</b> Typy poniżej mogą być nieaktualne – wrócimy, gdy tylko źródło zacznie odpowiadać.
            </span>
          </div>
        </div>
      )}

      <div className="ap-tresc">{children}</div>

      <StopkaPlus jasneLogo={ciemny} linki={LINKI_STOPKI} rozgrywek={rozgrywek} />

      {/* telefon: dolny pasek A */}
      <LayoutGroup id={`${id}-t`}>
        <nav className="s-t-dol ap-tel" aria-label="Menu">
          {MENU.slice(0, 4).map((m) => (
            <Link key={m.k} href={m.href} className="s-t-poz" aria-current={aktywna === m.k ? "page" : undefined} onClick={() => klik(m.href)}>
              {aktywna === m.k && <motion.span layoutId="kreska-ap-t" className="s-t-kreska" transition={RUCH.sprezyna.znacznik} />}
              <IkonaNav klucz={m.k} pelna={aktywna === m.k} rozmiar={22} />
              {m.label}
            </Link>
          ))}
          <button type="button" className="s-t-poz" aria-current={aktywna === "skutecznosc" || aktywna === "jak" ? "page" : undefined} aria-expanded={wiecej} onClick={() => setWiecej(true)}>
            {(aktywna === "skutecznosc" || aktywna === "jak") && <motion.span layoutId="kreska-ap-t" className="s-t-kreska" transition={RUCH.sprezyna.znacznik} />}
            <IkonaNav klucz="wiecej" pelna={aktywna === "skutecznosc" || aktywna === "jak"} rozmiar={22} />
            Więcej
          </button>
        </nav>
      </LayoutGroup>

      <AnimatePresence>{szukaj && <PaletaAplikacji indeks={indeks} start={szukajStart} zamknij={() => setSzukaj(false)} />}</AnimatePresence>

      <AnimatePresence>
        {wiecej && (
          <>
            <motion.div key="tlo" className="s-arkusz-tlo ap-arkusz-tlo" onClick={() => setWiecej(false)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            <motion.div key="arkusz" className="s-arkusz ap-arkusz" role="dialog" aria-label="Więcej" initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }} transition={RUCH.sprezyna.panel}>
              <div className="s-arkusz-uchwyt" aria-hidden />
              {MENU.filter((m) => m.grupa === 2).map((m) => (
                <Link key={m.k} href={m.href} className="s-arkusz-poz" aria-current={aktywna === m.k ? "page" : undefined} onClick={() => klik(m.href)}>
                  <IkonaNav klucz={m.k} rozmiar={20} />
                  {m.label}
                </Link>
              ))}
              <button type="button" className="s-arkusz-poz" onClick={przelaczMotyw}>
                <IkonaMotyw ciemny={ciemny} r={20} />
                Motyw
                <small>{ciemny ? "ciemny" : "jasny"}</small>
              </button>
              <button type="button" className="s-arkusz-poz" onClick={wyloguj}>
                <IkonaWyloguj r={20} />
                Wyloguj
              </button>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

