"use client";

import { AnimatePresence, LayoutGroup, MotionConfig, animate, motion, useReducedMotionConfig } from "framer-motion";
import { useEffect, useId, useRef, useState } from "react";

import "../../atomy.css";
import "../../atomy2.css";
import "../../elementy.css";
import "../../szkielet.css";
import "../../strony.css";
import "../../ruch.css";

import { fmtLinia } from "@/lib/format";

import type { DaneStron } from "../../_dane/strony";
import { Sekcja, type WariantAtomu } from "../atomy/wspolne";
import { LogoPoziome } from "../LogoPoziome";
import { SLOWNIKI, type Charakter, type Slownik } from "./slownik";

/*
 * Etap 6 – ruch. Jeden słownik (3 czasy, 3 krzywe, 3 sprężyny) i momenty,
 * w których ruch niesie znaczenie danych. Scena działa na prawdziwych typach
 * z migawki; wyniki rozliczenia w pokazie są przykładowe (podpisane).
 */

type Motyw = "ciemny" | "jasny";
const PALETA: Record<Motyw, string> = { ciemny: "b1", jasny: "p3" };
const kursTxt = (k: number) => k.toFixed(2).replace(".", ",");

/* ---- liczba, która przelicza się od starej do nowej ------------------------ */

function Liczba({ v, s, format = (x: number) => String(Math.round(x)) }: { v: number; s: Slownik; format?: (x: number) => string }) {
  const reduced = useReducedMotionConfig();
  const [pokaz, setPokaz] = useState(v);
  const poprzednia = useRef(v);
  useEffect(() => {
    if (reduced) {
      poprzednia.current = v;
      return;
    }
    const a = animate(poprzednia.current, v, { duration: s.licznik, ease: s.krzywa.hamuje, onUpdate: setPokaz });
    poprzednia.current = v;
    return () => a.stop();
  }, [v, s, reduced]);
  // ograniczony ruch: od razu nowa wartość
  return <>{format(reduced ? v : pokaz)}</>;
}

/* ---- 6.1 słownik: tor z kropką dla każdego czasu i sprężyny ----------------- */

function Tor({ przejscie, klucz }: { przejscie: object; klucz: number }) {
  return (
    <span className="ru-tor" aria-hidden>
      <motion.i key={klucz} initial={{ left: "0%" }} animate={{ left: "calc(100% - 12px)" }} transition={przejscie} />
    </span>
  );
}

function SlownikRuchu({ s }: { s: Slownik }) {
  const [klucz, setKlucz] = useState(0);
  const wiersze: { nazwa: string; wartosc: string; do: string; przejscie: object }[] = [
    { nazwa: "Czas szybki", wartosc: `${s.czas.szybki} s`, do: "najechanie, naciśnięcie, zmiana koloru", przejscie: { duration: s.czas.szybki, ease: s.krzywa.hamuje } },
    { nazwa: "Czas zwykły", wartosc: `${s.czas.zwykly} s`, do: "rozwinięcie, dymek, podmiana treści", przejscie: { duration: s.czas.zwykly, ease: s.krzywa.hamuje } },
    { nazwa: "Czas wolny", wartosc: `${s.czas.wolny} s`, do: "rysowanie wykresu i znaku, otwarcie bramy logowania", przejscie: { duration: s.czas.wolny, ease: s.krzywa.rysuje } },
    { nazwa: "Sprężyna znacznika", wartosc: `${s.sprezyna.znacznik.stiffness}/${s.sprezyna.znacznik.damping}`, do: "kreska menu, tło przełącznika, wybrana półka", przejscie: s.sprezyna.znacznik },
    { nazwa: "Sprężyna panelu", wartosc: `${s.sprezyna.panel.stiffness}/${s.sprezyna.panel.damping}`, do: "okno, arkusz od dołu, kupon", przejscie: s.sprezyna.panel },
    { nazwa: "Sprężyna wyskoku", wartosc: `${s.sprezyna.wyskok.stiffness}/${s.sprezyna.wyskok.damping}`, do: "✓ wyboru, ✕ pudła, kropki", przejscie: s.sprezyna.wyskok },
    { nazwa: "Sprężyna radości", wartosc: `${s.sprezyna.radosc.stiffness}/${s.sprezyna.radosc.damping}`, do: "tylko: dolot do kuponu i ✓ trafionego typu", przejscie: s.sprezyna.radosc },
  ];
  return (
    <div className="ru-slownik">
      <div className="ru-slownik-tabela">
        {wiersze.map((w) => (
          <div key={w.nazwa} className="ru-sl-wiersz">
            <b>{w.nazwa}</b>
            <code>{w.wartosc}</code>
            <span>{w.do}</span>
            <Tor przejscie={w.przejscie} klucz={klucz} />
          </div>
        ))}
      </div>
      <div className="ru-slownik-stopka">
        <button type="button" className="a-guzik" data-t="drugi" data-r="s" onClick={() => setKlucz((k) => k + 1)}>
          ▶ Odtwórz wszystkie
        </button>
        <span>Krzywe: hamowanie (wejście, rozwinięcie), ruszanie (wyjście), rysowanie (wykresy, znak). Wyjście trwa ok. 70% wejścia.</span>
      </div>
    </div>
  );
}

/* ---- 6.2 scena: lista typów w akcji ---------------------------------------- */

type Karta = DaneStron["kartyStrony"][number];
type Wynik = "wygrany" | "przegrany";
const WYNIKI_POKAZU: Wynik[] = ["wygrany", "wygrany", "przegrany"];

function ZnakWyniku({ wynik, s }: { wynik: Wynik; s: Slownik }) {
  const reduced = useReducedMotionConfig();
  return (
    <motion.span className="ru-znak" data-wynik={wynik} initial={reduced ? false : { scale: 0.4, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={wynik === "wygrany" ? s.sprezyna.radosc : s.sprezyna.wyskok}>
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <motion.path
          d={wynik === "wygrany" ? "M3 7.4 5.9 10.2 11 4.2" : "M4 4l6 6M10 4l-6 6"}
          initial={reduced ? false : { pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: s.czas.zwykly, ease: s.krzywa.rysuje, delay: 0.08 }}
        />
      </svg>
    </motion.span>
  );
}

function Wiersz({
  k,
  s,
  wybrany,
  przelacz,
  zmianaKursu,
  wynik,
  bylo,
  refKurs,
}: {
  k: Karta;
  s: Slownik;
  wybrany: boolean;
  przelacz: () => void;
  zmianaKursu: number;
  wynik: Wynik | null;
  bylo: number;
  refKurs: (el: HTMLButtonElement | null) => void;
}) {
  const reduced = useReducedMotionConfig();
  const [otwarty, setOtwarty] = useState(false);
  const kurs = k.kurs + zmianaKursu * 0.07;
  const mecze = [...k.historia].reverse().slice(0, 10);
  const rozwin = s.rozwiniecie === "czas" ? { duration: s.czas.zwykly, ease: s.krzywa.hamuje } : s.sprezyna.panel;
  return (
    <div className="ru-wiersz" data-wynik={wynik ?? undefined}>
      {/* rozliczenie: przy trafieniu zielone przeciągnięcie przez wiersz, przy pudle – tylko znak */}
      {wynik === "wygrany" && (
        <motion.span
          className="ru-zalanie"
          aria-hidden
          initial={reduced ? false : { scaleX: 0, opacity: 1 }}
          animate={{ scaleX: 1, opacity: 0.55 }}
          transition={{ scaleX: { duration: s.czas.wolny, ease: s.krzywa.hamuje }, opacity: { delay: s.czas.wolny, duration: s.czas.wolny } }}
        />
      )}
      <div className="ru-wiersz-glowa">
        <span className="ru-status">{wynik ? <ZnakWyniku wynik={wynik} s={s} /> : <small>{k.godzina}</small>}</span>
        <button type="button" className="ru-wiersz-tekst" aria-expanded={otwarty} onClick={() => setOtwarty((o) => !o)}>
          <small>{k.kto}</small>
          <span>
            <b>{k.rynek.replace(/\s*drużyny\s*/, " ").trim()}</b> {k.strona === "ponizej" ? "poniżej" : "powyżej"} <strong>{fmtLinia(k.linia)}</strong>
          </span>
        </button>
        <span className="ru-prawa">
          <AnimatePresence mode="popLayout" initial={false}>
            {wynik ? (
              <motion.span key="bylo" className="ru-bylo" initial={reduced ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: s.czas.zwykly, ease: s.krzywa.hamuje, delay: 0.1 }}>
                <small>było</small>
                <b data-wynik={wynik}>{bylo}</b>
              </motion.span>
            ) : (
              <motion.span key="szansa" className="ru-szansa" exit={{ opacity: 0, y: -6 }} transition={{ duration: s.czas.szybki, ease: s.krzywa.rusza }}>
                {Math.round(k.szansa * 100)}
                <small>%</small>
              </motion.span>
            )}
          </AnimatePresence>
          <button type="button" ref={refKurs} className="ru-kurs" aria-pressed={wybrany} onClick={przelacz} disabled={!!wynik}>
            {/* zmiana kursu: błysk w kolorze kierunku + liczba wjeżdża z dołu (2.8) */}
            {zmianaKursu > 0 && (
              <motion.span
                key={zmianaKursu}
                className="ru-blysk"
                aria-hidden
                initial={{ opacity: 1 }}
                animate={{ opacity: 0 }}
                transition={{ duration: reduced ? 0 : 1.6, ease: "easeOut" }}
              />
            )}
            <AnimatePresence mode="popLayout" initial={false}>
              {wybrany && (
                <motion.span key="v" className="ru-ptaszek" initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }} transition={s.sprezyna.wyskok}>
                  ✓
                </motion.span>
              )}
            </AnimatePresence>
            <span className="ru-kurs-liczba">
              <AnimatePresence mode="popLayout" initial={false}>
                <motion.b key={kurs.toFixed(2)} initial={reduced ? false : { y: 12, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -12, opacity: 0 }} transition={{ duration: s.czas.zwykly, ease: s.krzywa.hamuje }}>
                  {kursTxt(kurs)}
                </motion.b>
              </AnimatePresence>
              {zmianaKursu > 0 && <i className="ru-kier">▲</i>}
            </span>
          </button>
        </span>
      </div>
      <AnimatePresence initial={false}>
        {otwarty && (
          <motion.div className="ru-rozwin" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0, transition: { duration: s.czas.zwykly * 0.7, ease: s.krzywa.rusza } }} transition={rozwin}>
            <div className="ru-rozwin-w">
              <span className="mz-kratki">
                {mecze.map((v, i) => (
                  <i key={i} data-s={(k.strona === "ponizej" ? v < k.linia : v > k.linia) ? "ok" : "nie"}>
                    {v}
                  </i>
                ))}
              </span>
              <small>ostatnie mecze, od najnowszego</small>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Scena({ karty, s, telefon }: { karty: Karta[]; s: Slownik; telefon: boolean }) {
  const reduced = useReducedMotionConfig();
  const id = useId();
  const rama = useRef<HTMLDivElement>(null);
  const kuponRef = useRef<HTMLSpanElement>(null);
  const kursy = useRef<(HTMLButtonElement | null)[]>([]);
  const [polka, setPolka] = useState(0);
  const [wybrane, setWybrane] = useState<boolean[]>([false, false, false]);
  const [wKuponie, setWKuponie] = useState(0);
  const [podskok, setPodskok] = useState(0);
  const [zmiana, setZmiana] = useState(0);
  const [rozliczone, setRozliczone] = useState(false);
  const [loty, setLoty] = useState<{ id: number; x0: number; y0: number; x1: number; y1: number }[]>([]);

  const przelacz = (i: number) => {
    const teraz = !wybrane[i];
    setWybrane((w) => w.map((x, j) => (j === i ? teraz : x)));
    if (!teraz) {
      setWKuponie((n) => n - 1);
      return;
    }
    const r = rama.current?.getBoundingClientRect();
    const a = kursy.current[i]?.getBoundingClientRect();
    const b = kuponRef.current?.getBoundingClientRect();
    if (reduced || !r || !a || !b) {
      setWKuponie((n) => n + 1);
      setPodskok((p) => p + 1);
      return;
    }
    // kropka leci z kursu do kuponu w menu – licznik rośnie, gdy doleci
    setLoty((l) => [...l, { id: Date.now(), x0: a.left - r.left + a.width / 2, y0: a.top - r.top + a.height / 2, x1: b.left - r.left + b.width / 2, y1: b.top - r.top + b.height / 2 }]);
  };

  const wynikiDnia = rozliczone ? WYNIKI_POKAZU : [];
  const weszlo = wynikiDnia.filter((w) => w === "wygrany").length;
  const reset = () => {
    setWybrane([false, false, false]);
    setWKuponie(0);
    setZmiana(0);
    setRozliczone(false);
  };

  return (
    <div className="ru-scena" ref={rama} data-telefon={telefon || undefined}>
      <div className="ru-menu">
        <LogoPoziome jasne wysokosc={18} />
        <span className="ru-menu-poz" data-on="">
          Zawodnicy
        </span>
        <span className="ru-menu-poz">
          Kupony
          <motion.span
            key={podskok}
            ref={kuponRef}
            className="ru-licznik"
            data-pusty={wKuponie === 0 || undefined}
            initial={reduced || podskok === 0 ? false : { scale: s.lot.odbicie ? 1.45 : 1.25 }}
            animate={{ scale: 1 }}
            transition={s.sprezyna.radosc}
          >
            {wKuponie}
          </motion.span>
        </span>
      </div>

      <div className="ru-tresc">
        <div className="ru-dzien">
          <b className="p-n">Jutro</b>
          {rozliczone ? (
            <span>
              weszło <b>{weszlo} z 3</b> ·{" "}
              <b className="ru-proc">
                <Liczba v={Math.round((weszlo / 3) * 100)} s={s} />%
              </b>
            </span>
          ) : (
            <span>3 typy z różnych meczów</span>
          )}
        </div>

        <LayoutGroup id={id}>
          <div className="mz-seg ru-polki" role="radiogroup" aria-label="Półka">
            {["Wysokie szanse", "Wyższe kursy", "Drabinki"].map((n, i) => (
              <button key={n} type="button" role="radio" aria-checked={polka === i} onClick={() => setPolka(i)}>
                {polka === i && <motion.span layoutId="ru-polka" className="mz-seg-tlo" transition={s.sprezyna.znacznik} />}
                <span className="mz-seg-tresc">{n}</span>
              </button>
            ))}
          </div>
        </LayoutGroup>

        <div className="ru-lista">
          {karty.map((k, i) => (
            <Wiersz
              key={k.id}
              k={k}
              s={s}
              wybrany={wybrane[i]}
              przelacz={() => przelacz(i)}
              zmianaKursu={i === 0 ? zmiana : 0}
              wynik={rozliczone ? WYNIKI_POKAZU[i] : null}
              bylo={WYNIKI_POKAZU[i] === "wygrany" ? Math.floor(k.linia) + 2 : 0}
              refKurs={(el) => {
                kursy.current[i] = el;
              }}
            />
          ))}
        </div>
      </div>

      {loty.map((l) => (
        <motion.span
          key={l.id}
          className="ru-lot"
          aria-hidden
          initial={{ x: l.x0, y: l.y0, scale: 1 }}
          animate={{ x: [l.x0, l.x0 + (l.x1 - l.x0) * 0.6, l.x1], y: [l.y0, Math.max(10, Math.min(l.y0, l.y1) - 40), l.y1], scale: [1, 1.15, 0.55] }}
          transition={{ duration: s.lot.czas, ease: s.krzywa.hamuje, times: [0, 0.45, 1] }}
          onAnimationComplete={() => {
            setLoty((x) => x.filter((y) => y.id !== l.id));
            setWKuponie((n) => n + 1);
            setPodskok((p) => p + 1);
          }}
        />
      ))}

      <div className="ru-sterowanie">
        <button type="button" className="a-guzik" data-t="drugi" data-r="s" onClick={() => setZmiana((z) => z + 1)} disabled={rozliczone}>
          Kurs rośnie
        </button>
        <button type="button" className="a-guzik" data-t="drugi" data-r="s" onClick={() => setRozliczone(true)} disabled={rozliczone}>
          Rozlicz mecze
        </button>
        <button type="button" className="a-guzik" data-t="cichy" data-r="s" onClick={reset}>
          Od nowa
        </button>
        <small>Kliknij kurs (do kuponu), nazwę (rozwinięcie), półkę. Wyniki rozliczenia w pokazie są przykładowe.</small>
      </div>
    </div>
  );
}

/* ---- 6.3 przejście między stronami ----------------------------------------- */

function Przejscie({ s }: { s: Slownik }) {
  const [strona, setStrona] = useState<"zawodnicy" | "druzyny">("zawodnicy");
  const [faza, setFaza] = useState<"gotowe" | "czekam" | "szkielet">("gotowe");
  const [pasek, setPasek] = useState(0);
  const id = useId();
  const idz = (k: "zawodnicy" | "druzyny") => {
    if (k === strona) return;
    setPasek((p) => p + 1);
    setFaza("czekam");
    // szkielet dopiero po 300 ms (2.9) – szybkie wczytanie nie mruga
    const t1 = setTimeout(() => setFaza("szkielet"), 300);
    setTimeout(() => {
      clearTimeout(t1);
      setStrona(k);
      setFaza("gotowe");
    }, 900);
  };
  return (
    <div className="ru-przejscie">
      <div className="ru-menu">
        <LogoPoziome jasne wysokosc={18} />
        <LayoutGroup id={id}>
          {(["zawodnicy", "druzyny"] as const).map((k) => (
            <button key={k} type="button" className="ru-menu-poz" data-on={strona === k || undefined} onClick={() => idz(k)}>
              {k === "zawodnicy" ? "Zawodnicy" : "Drużyny"}
              {strona === k && <motion.span layoutId="ru-kreska" className="ru-kreska" transition={s.sprezyna.znacznik} />}
            </button>
          ))}
        </LayoutGroup>
        <AnimatePresence>
          {pasek > 0 && (
            <motion.span
              key={pasek}
              className="ru-ladowanie"
              initial={{ scaleX: 0, opacity: 1 }}
              animate={{ scaleX: [0, 0.7, 1], opacity: [1, 1, 0] }}
              transition={{ duration: 0.9, times: [0, 0.6, 1], ease: s.krzywa.hamuje }}
            />
          )}
        </AnimatePresence>
      </div>
      <div className="ru-strona">
        {faza === "szkielet" ? (
          <div className="ru-szk">
            <div className="d-kosc" style={{ width: 160, height: 22 }} />
            <div className="d-kosc" style={{ width: "100%", height: 52, borderRadius: 10 }} />
            <div className="d-kosc" style={{ width: "100%", height: 52, borderRadius: 10 }} />
          </div>
        ) : faza === "czekam" ? (
          <div className="ru-szk" style={{ opacity: 0.6 }}>
            <Strona k={strona} />
          </div>
        ) : (
          <motion.div key={strona} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: s.czas.zwykly, ease: s.krzywa.hamuje }}>
            <Strona k={strona} />
          </motion.div>
        )}
      </div>
      <p className="ru-opis">Klik w menu: kreska przesuwa się od razu, pasek ładowania biegnie pod menu, stara strona przygasa. Szkielet tylko gdy ładowanie trwa dłużej niż 300 ms. Nowa strona – bez wjazdu z boku, tylko krótkie pojawienie.</p>
    </div>
  );
}

function Strona({ k }: { k: "zawodnicy" | "druzyny" }) {
  return (
    <div className="ru-szk">
      <b className="p-n" style={{ fontSize: 20 }}>
        {k === "zawodnicy" ? "Zawodnicy" : "Drużyny"}
      </b>
      <div className="ru-atrapa">{k === "zawodnicy" ? "Strzały powyżej 0,5 · 73%" : "Rożne powyżej 4,5 · 70%"}</div>
      <div className="ru-atrapa">{k === "zawodnicy" ? "Faule popełnione powyżej 0,5 · 72%" : "Gole poniżej 2,5 · 68%"}</div>
    </div>
  );
}

/* ---- strona warsztatu ----------------------------------------------------------- */

const SEKCJE: { klucz: string; nr: string; tytul: string; opis: string; warianty: WariantAtomu[] }[] = [
  {
    klucz: "charakter",
    nr: "6.1",
    tytul: "Charakter ruchu",
    opis: "Ten sam zestaw scen w dwóch charakterach. Wybór obowiązuje wszystko niżej i potem całą aplikację. Ruch tylko tam, gdzie zmienia się dana – nic nie wjeżdża przy przewijaniu.",
    warianty: [
      { id: "ok", nazwa: "Zatwierdzony", opis: "wybrany 01.10: Precyzyjny w całej aplikacji, a odbicie ze Sprężystego tylko w dwóch momentach, które cieszą – dolot kropki do kuponu (licznik podskakuje) i ✓ trafionego typu. Pudło ✕ wskakuje spokojnie." },
      { id: "a", nazwa: "A · Precyzyjny", opis: "krótko i bez przestrzeliwania – jak Linear i Sofascore. Znacznik dojeżdża równo, ✓ wskakuje bez odbicia, rozwinięcia płyną czasem 0,22 s. Spokój przy długim przeglądaniu listy." },
      { id: "b", nazwa: "B · Sprężysty", opis: "lekkie odbicie w znaczących momentach – jak Superbet: ✓ rozliczenia i licznik kuponu podskakują, znacznik leciutko przestrzeliwuje, rozwinięcia na sprężynie. Więcej „wow”, odrobinę dłużej." },
    ],
  },
  {
    klucz: "scena",
    nr: "6.2",
    tytul: "Lista typów w akcji",
    opis: "Wszystkie momenty naraz, na prawdziwych typach: wybór półki (znacznik), rozwinięcie wiersza, dodanie do kuponu (kropka leci do kuponu w menu, licznik rośnie, gdy doleci), zmiana kursu (błysk i liczba z dołu), rozliczenie (przy trafieniu zielone przeciągnięcie przez wiersz i rysujący się ✓, przy pudle tylko ✕ – bez dramatu), przeliczenie wyniku dnia.",
    warianty: [{ id: "a", nazwa: "Scena", opis: "komputer i telefon obok siebie." }],
  },
  {
    klucz: "przejscie",
    nr: "6.3",
    tytul: "Przejście między stronami",
    opis: "Zatwierdzone klocki z etapów 2 i 4 złożone w jedno: kreska menu, pasek ładowania, szkielet po 300 ms, krótkie pojawienie się treści.",
    warianty: [{ id: "a", nazwa: "Przejście", opis: "kliknij Drużyny / Zawodnicy w podglądzie." }],
  },
  {
    klucz: "slownik",
    nr: "6.4",
    tytul: "Słownik ruchu",
    opis: "Zamiast 16 sprężyn i 15 czasów z etapów 2–5: trzy czasy, trzy krzywe, trzy sprężyny plus jedna „radosna” na dwa momenty. Każda wartość ma jedno zastosowanie. Przy składaniu wchodzą do wszystkich komponentów z jednego pliku.",
    warianty: [{ id: "a", nazwa: "Wartości wybranego charakteru", opis: "kliknij „Odtwórz”, żeby zobaczyć tempo każdej." }],
  },
];

export function Ruch({ dane }: { dane: DaneStron }) {
  const [motyw, setMotyw] = useState<Motyw>("ciemny");
  const [charakter, setCharakter] = useState<Charakter>("ok");
  const [ograniczony, setOgraniczony] = useState(false);
  const s = SLOWNIKI[charakter];
  // trzy typy z różnych meczów, z pełną historią
  const karty = (() => {
    const mecze = new Set<number>();
    return dane.kartyStrony.filter((k) => k.historia.length >= 10 && !mecze.has(k.meczId) && mecze.add(k.meczId)).slice(0, 3);
  })();
  // zmiana charakteru albo trybu ruchu = sceny od nowa
  const klucz = `${charakter}-${ograniczony}`;

  return (
    <MotionConfig reducedMotion={ograniczony ? "always" : "never"}>
      <div className="p-pulpit">
        <div className="p-pulpit-wnetrze">
          <div className="p-pulpit-tytul">
            Etap 6 <span>· ruch</span>
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
            <span>ruch</span>
            <div className="p-segmenty" role="group">
              <button type="button" aria-pressed={!ograniczony} onClick={() => setOgraniczony(false)}>
                Pełny
              </button>
              <button type="button" aria-pressed={ograniczony} onClick={() => setOgraniczony(true)}>
                Ograniczony
              </button>
            </div>
          </div>
        </div>
        <div className="p-pulpit-opis">„Ograniczony” = ustawienie systemu „ogranicz ruch”: zmiany natychmiast, bez przesunięć i lotów.</div>
      </div>
      <div className="p-ekran" data-p-motyw={motyw} data-p-paleta={PALETA[motyw]} data-p-font="2c">
        <div className="p-tresc" style={{ maxWidth: 1320 }}>
          {SEKCJE.map((x) => (
            <Sekcja
              key={x.klucz}
              nr={x.nr}
              tytul={x.tytul}
              opis={x.opis}
              warianty={x.warianty}
              wybrany={x.klucz === "charakter" ? charakter : "a"}
              zmien={(v) => x.klucz === "charakter" && setCharakter(v as Charakter)}
            >
              {x.klucz === "charakter" && (
                <p className="ru-wybrany">
                  Wybrany: <b>{s.nazwa}</b> – sceny poniżej działają w tym charakterze.
                </p>
              )}
              {x.klucz === "scena" && karty.length > 0 && (
                <div className="ru-dwie" key={klucz}>
                  <div className="ru-komp">
                    <Scena karty={karty} s={s} telefon={false} />
                  </div>
                  <div className="ru-tel">
                    <Scena karty={karty} s={s} telefon />
                  </div>
                </div>
              )}
              {x.klucz === "przejscie" && <Przejscie key={klucz} s={s} />}
              {x.klucz === "slownik" && <SlownikRuchu key={klucz} s={s} />}
            </Sekcja>
          ))}
        </div>
      </div>
    </MotionConfig>
  );
}
