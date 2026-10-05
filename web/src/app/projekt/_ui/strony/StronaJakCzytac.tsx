"use client";

import { Lnk } from "../linki";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import type { DaneStron } from "../../_dane/strony";
import { Logo } from "../atomy2/podstawowe";
import { KartaA } from "../elementy/karta";

/*
 * Etap 5.8 – „Jak czytać typy” (zamiast „Jak to działa”, decyzja 01.10).
 * Rdzeń: PRAWDZIWA karta typu z podpisanymi częściami – słowniczek na
 * przykładzie, nie opis modelu. Do tego lejek z liczbami (bez kafli
 * z ikonkami – zakaz z listy AI slopu), słowniczek pojęć z małymi
 * przykładami z naszych elementów i najczęstsze pytania.
 * Każde zdanie musi być prawdą o produkcie (bez obietnic wygranej).
 */

type Czesc = { id: string; nazwa: string; selektor: string; tekst: React.ReactNode };

const CZESCI: Czesc[] = [
  {
    id: "kto",
    nazwa: "Kto",
    selektor: ".a-typ-kto",
    tekst: "Zawodnik albo drużyna, której dotyczy zakład. Obok herb jego drużyny.",
  },
  {
    id: "zaklad",
    nazwa: "Zakład",
    selektor: ".el-zaklad-wiersz",
    tekst: (
      <>
        Rynek i linia – dokładnie tak, jak w ofercie bukmachera. <b>Powyżej 0,5</b> znaczy „co najmniej 1”, <b>powyżej 1,5</b> – „co najmniej 2”.
      </>
    ),
  },
  {
    id: "szansa",
    nazwa: "Szansa",
    selektor: ".d-szansa",
    tekst: "Jak często według nas taki zakład wchodzi. Liczymy ją z historii zawodnika, rywala i składu – nie z kursu. Nawet wysoka szansa to wciąż kilka pudeł na dziesięć.",
  },
  {
    id: "kurs",
    nazwa: "Kurs",
    selektor: ".d-kurs",
    tekst: "Kurs z chwili, gdy typ trafił na listę – najwyższy z dwóch bukmacherów, przy nim logo tego, który płaci więcej. Kursy sprawdzamy co pół godziny – przed postawieniem zerknij, czy się nie zmienił.",
  },
  {
    id: "historia",
    nazwa: "Ostatnie mecze",
    selektor: ".d-historia",
    tekst: (
      <>
        Kratka = jeden mecz, od najnowszego. Zielona – zakład by wszedł, szara – nie. <b>„8/10”</b> to najprostszy argument: w 8 z 10 ostatnich meczów linia została przebita.
      </>
    ),
  },
  {
    id: "powody",
    nazwa: "Za i przeciw",
    selektor: ".el-powody",
    tekst: "Konkretne fakty, które podniosły albo obniżyły szansę: rywal, sędzia, skład, mecz u siebie. Pokazujemy też te przeciw.",
  },
];

/* ---- lejek: trzy kroki jako linia z liczbami ------------------------------- */

function Lejek({ typow, dzien }: { typow: number; dzien: string }) {
  const kroki = [
    { liczba: "1600+", co: "zakładów sprawdzamy dziennie", opis: "każdą linię na zawodników i drużyny z oferty dwóch bukmacherów" },
    { liczba: "10", co: "ostatnich meczów przy każdym", opis: "do tego rywal, sędzia i skład – wszystko, co zmienia szansę" },
    { liczba: String(typow), co: `typów zostaje na ${dzien.toLowerCase()}`, opis: "tylko najmocniejsze, każdy z uzasadnieniem" },
  ];
  return (
    <ol className="jc-lejek">
      {kroki.map((k, i) => (
        <li key={i}>
          <span className="jc-lejek-kropka" aria-hidden />
          <b className="p-n">{k.liczba}</b>
          <span className="jc-lejek-co">{k.co}</span>
          <small>{k.opis}</small>
        </li>
      ))}
    </ol>
  );
}

/* ---- rozbiór karty -------------------------------------------------------- */

function useKartaZPodswietleniem(aktywna: string | null) {
  const rama = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const r = rama.current;
    if (!r) return;
    r.querySelectorAll("[data-jc-swieci]").forEach((e) => e.removeAttribute("data-jc-swieci"));
    const c = CZESCI.find((x) => x.id === aktywna);
    if (!c) return;
    const el = r.querySelector(c.selektor);
    el?.setAttribute("data-jc-swieci", "");
  }, [aktywna]);
  return rama;
}

function Przewodnik({ karta, telefon }: { karta: DaneStron["kartyStrony"][number]; telefon: boolean }) {
  const [i, setI] = useState(0);
  const [kier, setKier] = useState(1);
  const c = CZESCI[i];
  const rama = useKartaZPodswietleniem(c.id);
  const idz = (j: number) => {
    if (j < 0 || j >= CZESCI.length || j === i) return;
    setKier(j > i ? 1 : -1);
    setI(j);
  };
  const ostatni = i === CZESCI.length - 1;
  return (
    <div className="jc-przewodnik">
      <div className="jc-karta" ref={rama} data-swieci="">
        <KartaA t={karta} otwarta />
      </div>
      <div
        className="jc-krok"
        role="group"
        aria-roledescription="przewodnik"
        aria-label={`Część ${i + 1} z ${CZESCI.length}: ${c.nazwa}`}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
          e.preventDefault();
          idz(e.key === "ArrowRight" ? i + 1 : i - 1);
        }}
      >
        <div className="jc-krok-glowa">
          <span className="jc-krok-ile">
            {i + 1} z {CZESCI.length}
          </span>
          <span className="jc-krok-kropki">
            {CZESCI.map((x, j) => (
              <button key={x.id} type="button" aria-label={`${j + 1}. ${x.nazwa}`} aria-current={j === i || undefined} data-byl={j < i || undefined} onClick={() => idz(j)}>
                <i />
              </button>
            ))}
          </span>
          <span className="sk-panel-strzalki">
            <button type="button" aria-label="Poprzednia część" disabled={i === 0} onClick={() => idz(i - 1)}>
              ‹
            </button>
            <button type="button" aria-label="Następna część" disabled={ostatni} onClick={() => idz(i + 1)}>
              ›
            </button>
          </span>
        </div>
        <AnimatePresence mode="wait" custom={kier} initial={false}>
          <motion.div
            key={c.id}
            custom={kier}
            initial={{ opacity: 0, x: 12 * kier }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -12 * kier }}
            transition={{ duration: 0.18 }}
            drag="x"
            dragConstraints={{ left: 0, right: 0 }}
            dragElastic={0.25}
            onDragEnd={(_, info) => {
              // przesunięcie palcem: w lewo – dalej, w prawo – wstecz
              if (info.offset.x < -50) idz(i + 1);
              else if (info.offset.x > 50) idz(i - 1);
            }}
            className="jc-krok-tresc"
          >
            <b className="jc-krok-nazwa p-n">{c.nazwa}</b>
            <p className="jc-krok-tekst">{c.tekst}</p>
            {ostatni && (
              <div className="jc-krok-dalej">
                <Lnk href="/" className="a-guzik" data-t="glowny" data-r="m">
                  Zobacz typy na dziś <span className="d-strzalka">→</span>
                </Lnk>
                <a className="a-guzik" data-t="cichy" data-r="m" href="#jc-slowa">
                  Słowniczek ↓
                </a>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
        <small className="jc-krok-podpowiedz">{telefon ? "przesuń palcem w bok, żeby przejść dalej" : "strzałki ← → na klawiaturze też działają"}</small>
      </div>
    </div>
  );
}

/* ---- słowniczek -------------------------------------------------------------- */

function Kreski({ wzor }: { wzor: number[] }) {
  return (
    <span className="st-passa-kreski" aria-hidden>
      {wzor.map((k, i) => (
        <i key={i} data-s={k ? "ok" : "nie"} />
      ))}
    </span>
  );
}

type Pojecie = { id: string; nazwa: string; tekst: React.ReactNode; przyklad: React.ReactNode };

const POJECIA: Pojecie[] = [
  {
    id: "linia",
    nazwa: "Linia",
    tekst: "Próg z oferty bukmachera. Zakład „powyżej” wchodzi, gdy wynik jest wyższy niż linia, „poniżej” – gdy niższy.",
    przyklad: (
      <span className="jc-ex">
        strzały <b>powyżej 1,5</b> → wchodzi przy 2, 3, 4…
      </span>
    ),
  },
  {
    id: "weszlo",
    nazwa: "Weszło w 8 z 10",
    tekst: "W ilu z 10 ostatnich meczów zakład by wszedł. Mecze, w których zawodnik nie zagrał, nie liczą się do dziesiątki.",
    przyklad: (
      <span className="jc-ex">
        <Kreski wzor={[1, 1, 0, 1, 1, 1, 0, 1, 1, 1]} /> 8 z 10
      </span>
    ),
  },
  {
    id: "polki",
    nazwa: "Półki",
    tekst: (
      <>
        Typy dzielimy na trzy półki. <b>Wysokie szanse</b> wchodzą najczęściej, ale płacą mniej. <b>Wyższe kursy</b> płacą więcej, wchodzą rzadziej. <b>Drabinki</b> – patrz niżej.
      </>
    ),
    przyklad: (
      <span className="jc-ex jc-ex-polki">
        <i>Wysokie szanse</i>
        <i>Wyższe kursy</i>
        <i>Drabinki</i>
      </span>
    ),
  },
  {
    id: "drabinka",
    nazwa: "Drabinka",
    tekst: "Kilka linii jednego zawodnika jedna nad drugą. Każdy wyższy szczebel płaci więcej, ale wchodzi rzadziej – wybierasz, jak wysoko grasz.",
    // przykład podmieniany na prawdziwą drabinkę z listy (Slowniczek)
    przyklad: null,
  },
  {
    id: "kursy",
    nazwa: "Dwa kursy",
    tekst: "Sprawdzamy Superbet i Betclic. Przy typie pokazujemy wyższy kurs i logo bukmachera, który go daje.",
    przyklad: (
      <span className="jc-ex">
        <Logo nazwa="Superbet" wysokosc={11} /> <Logo nazwa="Betclic" wysokosc={11} />
      </span>
    ),
  },
  {
    id: "zwrot",
    nazwa: "Zwrot",
    tekst: "Bukmacher oddaje stawkę. W Superbecie – gdy zawodnik nie wyjdzie w pierwszym składzie, w Betclicu – gdy nie zagra ani minuty. Przełożony mecz to zwrot, jeśli nie odbędzie się w terminie bukmachera. W Wynikach zwrot nie jest ani trafieniem, ani pudłem.",
    przyklad: (
      <span className="jc-ex">
        <span className="jc-zwrot">↺</span> stawka wraca
      </span>
    ),
  },
  {
    id: "kupon",
    nazwa: "Kupon",
    tekst: "Kilka typów na jednym zakładzie. Kursy się mnożą, więc wygrana rośnie – ale wszystkie typy muszą wejść.",
    przyklad: (
      <span className="jc-ex">
        1,40 × 1,55 × 1,62 = <b>×3,52</b>
      </span>
    ),
  },
];

function PrzykladDrabinki({ d }: { d: DaneStron["drabinka"] }) {
  if (!d) return null;
  return (
    <span className="jc-ex jc-ex-drabinka">
      <small>
        {d.kto} · {d.rynek.toLowerCase()}
      </small>
      {d.szczeble.slice(0, 3).map((x) => (
        <i key={x.linia}>
          {String(x.linia).replace(".", ",")}+ <b>{x.kurs.toFixed(2).replace(".", ",")}</b>
        </i>
      ))}
    </span>
  );
}

function Slowniczek({ drabinka }: { drabinka: DaneStron["drabinka"] }) {
  const pojecia = POJECIA.map((p) => (p.id === "drabinka" ? { ...p, przyklad: <PrzykladDrabinki d={drabinka} /> } : p));
  return (
    <dl className="jc-slownik">
      {pojecia.map((p) => (
        <div key={p.id} id={`pojecie-${p.id}`} className="jc-pojecie">
          <dt>{p.nazwa}</dt>
          <dd>
            <span>{p.tekst}</span>
            {p.przyklad}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/* ---- najczęstsze pytania ---------------------------------------------------- */

const PYTANIA: { p: string; o: React.ReactNode }[] = [
  { p: "Kiedy pojawiają się typy?", o: "Gdy bukmacherzy wystawią kursy – na jutrzejsze mecze zwykle po 18:00. Lista odświeża się co pół godziny, a nowe typy przestają dochodzić półtorej godziny przed meczem, żebyś zdążył spokojnie postawić." },
  { p: "Co, jeśli zawodnik nie zagra?", o: "Zależy od bukmachera. Superbet oddaje stawkę, gdy zawodnik nie wyjdzie w pierwszym składzie – nawet jeśli wejdzie z ławki. Gdy zejdzie w trakcie, Superbet dolicza to, co zrobi jego zmiennik. Betclic oddaje stawkę tylko wtedy, gdy zawodnik nie zagra ani minuty. U nas zwrot nie liczy się ani jako trafiony, ani jako pudło." },
  { p: "A jeśli mecz przełożą?", o: "Superbet oddaje stawkę, gdy mecz nie odbędzie się do północy następnego dnia, Betclic – gdy nie odbędzie się w ciągu 48 godzin. Jeśli zagrają w tym terminie, typ rozliczamy normalnie." },
  { p: "Czy gwarantujecie wygraną?", o: "Nie. Typ to szansa, nie pewność – nawet przy 75% co czwarty taki zakład nie wejdzie. Dlatego w Wynikach zostaje każdy typ, także te nietrafione." },
  { p: "Skąd bierzecie kursy?", o: "Z ofert Superbetu i Betclica, sprawdzanych co pół godziny. Kurs u bukmachera może się zmienić między naszym odświeżeniem a Twoim zakładem – zerknij przed postawieniem." },
  { p: "Jak liczycie skuteczność?", o: "Każdy typ, który był na stronie, rozliczamy po meczu – bez poprawiania wstecz. Drabinka liczy się raz, za pierwszy szczebel. Zwroty pomijamy." },
  { p: "Czym różni się szansa od kursu?", o: "Kurs to cena bukmachera, szansa to nasza ocena z historii i kontekstu meczu. Gdy nasza szansa jest wyraźnie wyższa niż to, co wynika z kursu, bukmacher płaci więcej, niż powinien." },
];

function Pytania() {
  const [otwarte, setOtwarte] = useState<number | null>(0);
  const id = useId();
  return (
    <div className="jc-pytania">
      {PYTANIA.map((x, i) => {
        const on = otwarte === i;
        return (
          <div key={i} className="jc-pytanie" data-on={on || undefined}>
            <button type="button" aria-expanded={on} aria-controls={`${id}-${i}`} onClick={() => setOtwarte(on ? null : i)}>
              <span>{x.p}</span>
              <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
                <path d="M3.5 5.5 7 9l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <AnimatePresence initial={false}>
              {on && (
                <motion.div id={`${id}-${i}`} initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }} style={{ overflow: "hidden" }}>
                  <p>{x.o}</p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}

/* ---- strona ------------------------------------------------------------------ */

export function StronaJakCzytac({ dane, telefon }: { dane: DaneStron; telefon: boolean }) {

  // przykład: najmocniejszy typ na zawodnika z pełną dziesiątką meczów i argumentami
  const karta = useMemo(
    () => {
      // przykład ma pokazać mocny typ: najwięcej trafień w 10 meczach, potem szansa
      const trafienia = (k: (typeof dane.kartyStrony)[number]) => k.historia.slice(-10).filter((v) => (k.strona === "ponizej" ? v < k.linia : v > k.linia)).length;
      return (
        [...dane.kartyStrony]
          .filter((k) => k.podmiotTyp === "zawodnik" && k.historia.length >= 10 && k.powody.length >= 2)
          .sort((a, b) => trafienia(b) - trafienia(a) || b.szansa - a.szansa)[0] ?? dane.kartyStrony[0]
      );
    },
    [dane],
  );
  const dzien = karta?.dzien;
  const typow = dane.kartyStrony.filter((k) => k.dzien === dzien).length;
  return (
    <main className="st-strona jc">
      <div className="st-naglowek">
        <h1 className="p-n">Jak czytać typy</h1>
        <p>
          <span>Co znaczy każda liczba na karcie typu.</span> <span>Na prawdziwym przykładzie z naszej listy.</span>
        </p>
      </div>

      <section aria-labelledby="jc-jak">
        <h2 id="jc-jak" className="st-h2 p-n">
          Skąd się bierze typ
        </h2>
        <Lejek typow={typow} dzien={dzien ?? "dziś"} />
      </section>

      <section aria-labelledby="jc-karta">
        <h2 id="jc-karta" className="st-h2 p-n">
          Karta typu, część po części
        </h2>
        <p className="jc-pod">{telefon ? "Przechodź strzałkami – podświetlona część jest opisana pod kartą." : "Przechodź strzałkami – podświetlona część jest opisana obok."}</p>
        <Przewodnik karta={karta} telefon={telefon} />
      </section>

      <section aria-labelledby="jc-slowa">
        <h2 id="jc-slowa" className="st-h2 p-n">
          Słowniczek
        </h2>
        <Slowniczek drabinka={dane.drabinka} />
      </section>

      <section aria-labelledby="jc-pytania">
        <h2 id="jc-pytania" className="st-h2 p-n">
          Najczęstsze pytania
        </h2>
        <Pytania />
      </section>

      <p className="jc-odpowiedzialnie">
        <span>18+</span> Graj odpowiedzialnie: stawiaj tyle, ile możesz stracić. Typ to nie gwarancja wygranej.
      </p>
    </main>
  );
}

/* ---- „?” w miejscu: podpowiedź przy elemencie (5.9) -------------------------- */

export function Podpowiedz({ pojecie, children }: { pojecie: string; children: React.ReactNode }) {
  const [on, setOn] = useState(false);
  const rama = useRef<HTMLSpanElement>(null);
  const id = useId();
  useEffect(() => {
    if (!on) return;
    const klik = (e: MouseEvent) => !rama.current?.contains(e.target as Node) && setOn(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOn(false);
    document.addEventListener("mousedown", klik);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", klik);
      document.removeEventListener("keydown", esc);
    };
  }, [on]);
  const p = POJECIA.find((x) => x.id === pojecie);
  return (
    <span className="jc-pp" ref={rama}>
      <button type="button" className="jc-pp-przycisk" aria-expanded={on} aria-controls={id} aria-label={`Co to znaczy: ${p?.nazwa}`} onClick={() => setOn((o) => !o)}>
        ?
      </button>
      <AnimatePresence>
        {on && p && (
          <motion.span id={id} role="dialog" className="jc-pp-dymek" initial={{ opacity: 0, y: 4, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 4 }} transition={{ duration: 0.16 }}>
            <b>{p.nazwa}</b>
            <span>{p.tekst}</span>
            {children}
            <Lnk href="/jak-to-dziala" className="jc-pp-wiecej">Więcej w „Jak czytać typy” →</Lnk>
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}

export function PodpowiedziPokaz() {
  return (
    <main className="st-strona jc">
      <div className="st-naglowek">
        <h1 className="p-n">Zawodnicy</h1>
        <p>
          <span>Codziennie sprawdzamy ponad 1600 zakładów.</span> <span>Zostawiamy te, które wchodzą najczęściej.</span>
        </p>
      </div>
      <div className="jc-pp-scena">
        <div className="jc-pp-wiersz">
          <span className="jc-pp-etykieta">przy półkach</span>
          <span className="jc-pp-polki">
            <i data-on="">Wysokie szanse</i>
            <i>Wyższe kursy</i>
            <i>Drabinki</i>
          </span>
          <Podpowiedz pojecie="polki">{null}</Podpowiedz>
        </div>
        <div className="jc-pp-wiersz">
          <span className="jc-pp-etykieta">przy passie</span>
          <span className="st-passa">
            <Kreski wzor={[1, 1, 1, 1, 1, 1, 1, 1, 1, 1]} />
            <span>
              weszło w <b>10 z 10</b> ostatnich meczów
            </span>
          </span>
          <Podpowiedz pojecie="weszlo">{null}</Podpowiedz>
        </div>
        <div className="jc-pp-wiersz">
          <span className="jc-pp-etykieta">przy zwrocie</span>
          <span className="jc-ex">
            <span className="jc-zwrot">↺</span> zwrot
          </span>
          <Podpowiedz pojecie="zwrot">{null}</Podpowiedz>
        </div>
      </div>
    </main>
  );
}
