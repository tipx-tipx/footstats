"use client";

import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { useEffect, useState } from "react";

import "../../atomy.css";
import "../../atomy2.css";
import "../../elementy.css";
import "../../szkielet.css";
import "../../strony.css";
import "../../systemowe.css";

import type { DaneSystemowe } from "../../_dane/systemowe";
import { Sekcja, type WariantAtomu } from "../atomy/wspolne";
import { IkonaSzukaj } from "../szkielet/ikonyNav";
import { MenuKomputerPlus, MenuTelefon, Paleta, PrawaStrona, StopkaPlus } from "../szkielet/Szkielet";
import { WierszA } from "../elementy/mecz";
import { IkonaBezSieci } from "./Polaczenie";
import { Komunikat, Logowanie, STANY_LOGOWANIA, ZnakRysowany, type StanLogowania } from "./Logowanie";

/*
 * Strony systemowe. Zasada głosu marki: co się stało, dlaczego, co zrobić –
 * i zawsze droga dalej (nigdy ślepy zaułek). 404, błąd i brak internetu żyją
 * w zatwierdzonym menu, żeby można było po prostu pójść gdzie indziej.
 * Logowanie jest bez menu (jeszcze nie wpuściliśmy).
 */

type Motyw = "ciemny" | "jasny";
const PALETA: Record<Motyw, string> = { ciemny: "b1", jasny: "p3" };

const SEKCJE: { klucz: string; nr: string; tytul: string; opis: string; warianty: WariantAtomu[] }[] = [
  {
    klucz: "login",
    nr: "S.1",
    tytul: "Logowanie",
    opis: "Logujesz się na tle samego produktu, jak w Superbecie, Sofascore i Polymarkecie. Każdy komunikat to ramka z ikoną, tytułem i opisem: co się stało i co zrobić. Przełączaj stany nad oknem. Hasło do próby: footstats.",
    warianty: [
      {
        id: "nad",
        nazwa: "Nad aplikacją – wybrany",
        opis: "wybrany 01.10 („to jest sztos”) i dopracowany: pod spodem rozmyta strona Zawodnicy, okno z rysującym się logo (telefon: arkusz od dołu). Po poprawnym haśle (footstats) okno odpływa, a tło wyostrza się do pełnej strony – po 3 s pokaz wraca. Pełny ekran: /projekt/logowanie.",
      },
    ],
  },
  {
    klucz: "404",
    nr: "S.2",
    tytul: "Nie ma takiej strony (404)",
    opis: "Dopracowane: obok tekstu znak z logo, w którym wykres urywa się pustą kropką (ta sama rodzina co błąd i brak internetu). Adres, w który kliknąłeś, szukanie z wpisanym słowem z adresu, dwie drogi dalej i najbliższe mecze z typami (nasz wiersz meczu). Mecz, który się skończył: prawdziwy mecz z migawki z wynikami naszych typów i przejściem do Wyników.",
    warianty: [{ id: "a", nazwa: "Rzeczowo – wybrany", opis: "nagłówek mówi wprost, co się stało. Przełącz przypadek nad oknem." }],
  },
  {
    klucz: "blad",
    nr: "S.3",
    tytul: "Błąd po naszej stronie",
    opis: "Wersja 2: rzeczowy, profesjonalny tekst, obok znak z logo z przerwaną linią wykresu. „Spróbuj ponownie” bez przeładowania całej strony, identyfikator błędu do skopiowania. Gdy druga próba też nie wyjdzie – ramka z wyjaśnieniem, co dalej.",
    warianty: [{ id: "a", nazwa: "Błąd", opis: "kliknij „Spróbuj ponownie”, żeby zobaczyć powtórzony błąd." }],
  },
  {
    klucz: "offline",
    nr: "S.4",
    tytul: "Brak internetu",
    opis: "Najczęściej strona już jest wczytana – wtedy wystarczy pasek nad treścią z godziną, z której są typy, i sam znika, gdy zasięg wraca. Pełna strona tylko wtedy, gdy nie ma czego pokazać.",
    warianty: [
      { id: "pasek", nazwa: "Pasek nad treścią", opis: "strona działa dalej na tym, co już ma: ikona braku sieci, godzina danych i zapewnienie, że odświeżymy sami. Po powrocie zielony pasek „Znowu online” znika po 3 s (pokaż nad oknem)." },
      { id: "pelna", nazwa: "Pełna strona", opis: "gdy nic nie zdążyło się wczytać: znak z urwanym wykresem, „Spróbuj teraz” i samoczynna próba co 10 s z paskiem odliczania." },
    ],
  },
];

/* ---- wspólne ----------------------------------------------------------- */

function Segment<T extends string>({ opcje, wartosc, zmien, etykieta }: { opcje: [T, string][]; wartosc: T; zmien: (v: T) => void; etykieta: string }) {
  return (
    <div className="sy-stany" role="group" aria-label={etykieta}>
      <span>{etykieta}:</span>
      {opcje.map(([k, n]) => (
        <button key={k} type="button" aria-pressed={k === wartosc} onClick={() => zmien(k)}>
          {n}
        </button>
      ))}
    </div>
  );
}

/* ---- S.2 404 ------------------------------------------------------------ */

type Stan404 = "zwykla" | "mecz";

const dataDnia = (k: string) => {
  const d = new Date(`${k}T12:00:00Z`);
  return `${["nd", "pn", "wt", "śr", "cz", "pt", "sb"][d.getUTCDay()]} ${d.getUTCDate()}.${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
};

/* układ wspólny dla 404, błędu i braku internetu: tekst po lewej, znak z logo
   po prawej (na telefonie nad tekstem), pod spodem droga dalej */
export function UkladSys({ znak, children, dol }: { znak: React.ReactNode; children: React.ReactNode; dol?: React.ReactNode }) {
  return (
    <main className="sy-sys">
      <div className="sy-sys-gora">
        <div className="sy-sys-tekst">{children}</div>
        <div className="sy-sys-znak">{znak}</div>
      </div>
      {dol}
    </main>
  );
}

function NieMa({ stan, szukaj, dane }: { stan: Stan404; szukaj: () => void; dane: DaneSystemowe }) {
  if (stan === "mecz" && dane.zakonczony) {
    const z = dane.zakonczony;
    const ok = z.typy.filter((t) => t.wynik === "wygrany").length;
    const n = z.typy.filter((t) => t.wynik !== "zwrot").length;
    return (
      <UkladSys
        znak={<ZnakRysowany koniec="pelny" className="sy-znak-ilu" />}
        dol={
          <section className="sy-mecz-wyniki" aria-label={`Typy z meczu ${z.mecz}`}>
            <header>
              <b>{z.mecz}</b>
              <span>{dataDnia(z.dzien)}</span>
              <em>
                weszło {ok} z {n}
              </em>
            </header>
            {z.typy.map((t, i) => (
              <div key={i} className="sy-mecz-typ" data-wynik={t.wynik}>
                <span className="sy-mecz-znak" aria-label={t.wynik === "wygrany" ? "weszło" : t.wynik === "przegrany" ? "nie weszło" : "zwrot"}>
                  {t.wynik === "wygrany" ? "✓" : t.wynik === "przegrany" ? "✕" : "↺"}
                </span>
                <span className="sy-mecz-opis">
                  <small>{t.kto}</small>
                  <span>
                    <b>{t.rynek.replace(/\s*drużyny\s*/, " ").trim()}</b> {t.strona === "ponizej" ? "poniżej" : "powyżej"} <strong>{String(t.linia).replace(".", ",")}</strong>
                  </span>
                </span>
                <span className="sy-mecz-bylo">
                  <small>było</small>
                  <b>{t.faktyczna ?? "–"}</b>
                </span>
              </div>
            ))}
          </section>
        }
      >
        <p className="sy-adres">
          <span>adres</span> /mecze/15527741
        </p>
        <h1 className="p-n">Ten mecz już się skończył</h1>
        <p className="sy-lead">
          <span>Strona meczu znika po ostatnim gwizdku.</span> <span>Nasze typy z tego meczu zostają w Wynikach.</span>
        </p>
        <div className="sy-akcje">
          <button type="button" className="a-guzik" data-t="glowny" data-r="l">
            Wyniki z {dataDnia(z.dzien)} <span className="d-strzalka">→</span>
          </button>
          <button type="button" className="a-guzik" data-t="drugi" data-r="l">
            Mecze na dziś
          </button>
        </div>
      </UkladSys>
    );
  }
  return (
    <UkladSys
      znak={<ZnakRysowany koniec="brak" className="sy-znak-ilu" />}
      dol={
        dane.najblizsze.length > 0 && (
          <section className="sy-najblizsze el-liga" aria-label="Najbliższe mecze z typami">
            <div className="sy-najblizsze-glowa">
              <b>Najbliższe mecze z typami</b>
              <span>wejdź w mecz albo przejdź do całej listy</span>
            </div>
            {dane.najblizsze.map((m) => (
              <WierszA key={m.id} m={m} wybierz={() => undefined} />
            ))}
          </section>
        )
      }
    >
      <p className="sy-adres">
        <span>adres</span> /zawodnik/lewandowski-r
      </p>
      <h1 className="p-n">Nie ma takiej strony</h1>
      <p className="sy-lead">
        <span>Adres mógł się zmienić albo w linku jest literówka.</span> <span>Poszukaj od razu albo wróć do typów na dziś.</span>
      </p>
      <button type="button" className="sy-szukaj" onClick={szukaj}>
        <IkonaSzukaj r={18} />
        <span className="sy-szukaj-slowo">lewandowski</span>
        <span className="sy-szukaj-podpowiedz">szukaj zawodnika, drużyny, meczu</span>
        <kbd>Ctrl K</kbd>
      </button>
      <div className="sy-akcje">
        <button type="button" className="a-guzik" data-t="glowny" data-r="l">
          Typy na dziś <span className="d-strzalka">→</span>
        </button>
        <button type="button" className="a-guzik" data-t="drugi" data-r="l">
          Wszystkie mecze
        </button>
      </div>
    </UkladSys>
  );
}

/* ---- S.3 błąd ----------------------------------------------------------- */

function Blad() {
  const [proba, setProba] = useState<"nic" | "trwa" | "znowu">("nic");
  const [skopiowano, setSkopiowano] = useState(false);
  useEffect(() => {
    if (proba !== "trwa") return;
    const t = setTimeout(() => setProba("znowu"), 1100);
    return () => clearTimeout(t);
  }, [proba]);
  useEffect(() => {
    if (!skopiowano) return;
    const t = setTimeout(() => setSkopiowano(false), 1600);
    return () => clearTimeout(t);
  }, [skopiowano]);
  return (
    <UkladSys znak={<ZnakRysowany koniec="blad" className="sy-znak-ilu" />}>
      <h1 className="p-n">Nie udało się wczytać strony</h1>
      <p className="sy-lead">
        <span>Wystąpił błąd po naszej stronie.</span> <span>Spróbuj ponownie – zwykle to wystarcza.</span>
      </p>
      <AnimatePresence initial={false}>
        {proba === "znowu" && (
          <div className="sy-blad-kom">
            <Komunikat rodzaj="uwaga" tytul="Błąd się powtarza">
              Spróbuj ponownie za kilka minut. Jeśli problem nie zniknie, przekaż nam identyfikator błędu.
            </Komunikat>
          </div>
        )}
      </AnimatePresence>
      <div className="sy-akcje">
        <button type="button" className="a-guzik" data-t="glowny" data-r="l" aria-busy={proba === "trwa"} disabled={proba === "trwa"} onClick={() => setProba("trwa")}>
          {proba === "trwa" ? (
            <>
              <span className="d-krecik" aria-hidden /> Wczytuję ponownie
            </>
          ) : (
            "Spróbuj ponownie"
          )}
        </button>
        <button type="button" className="a-guzik" data-t="drugi" data-r="l">
          Przejdź do typów
        </button>
      </div>
      <div className="sy-kod">
        <span className="sy-kod-etykieta">Identyfikator błędu</span>
        <code>4f1a9c2e</code>
        <button type="button" onClick={() => setSkopiowano(true)} aria-live="polite">
          {skopiowano ? "✓ Skopiowano" : "Kopiuj"}
        </button>
      </div>
    </UkladSys>
  );
}

/* ---- S.4 brak internetu ------------------------------------------------- */

function BrakInternetu({ wariant, online }: { wariant: string; online: boolean }) {
  // samoczynne ponawianie: odliczanie 10 s, potem próba (w pokazie – bez skutku)
  const [za, setZa] = useState(10);
  const [proba, setProba] = useState(false);
  useEffect(() => {
    if (wariant !== "pelna") return;
    const t = setInterval(() => setZa((s) => (s <= 1 ? 10 : s - 1)), 1000);
    return () => clearInterval(t);
  }, [wariant]);
  useEffect(() => {
    if (!proba) return;
    const t = setTimeout(() => {
      setProba(false);
      setZa(10);
    }, 1100);
    return () => clearTimeout(t);
  }, [proba]);

  if (wariant === "pelna") {
    return (
      <UkladSys znak={<ZnakRysowany koniec="brak" className="sy-znak-ilu" />}>
        <h1 className="p-n">Brak internetu</h1>
        <p className="sy-lead">
          <span>Nie zdążyliśmy wczytać typów.</span> <span>Wczytają się same, gdy złapiesz zasięg.</span>
        </p>
        <div className="sy-akcje">
          <button type="button" className="a-guzik" data-t="glowny" data-r="l" aria-busy={proba} onClick={() => setProba(true)}>
            {proba ? (
              <>
                <span className="d-krecik" aria-hidden /> Sprawdzam połączenie
              </>
            ) : (
              "Spróbuj teraz"
            )}
          </button>
        </div>
        <p className="sy-ponowie" aria-live="off">
          {proba ? "Sprawdzam…" : `Spróbujemy sami za ${za} s`}
          <span className="sy-ponowie-pasek" aria-hidden>
            <i style={{ width: `${((10 - za) / 10) * 100}%` }} />
          </span>
        </p>
      </UkladSys>
    );
  }
  return (
    <main className="st-strona sy-offline">
      <AnimatePresence mode="wait" initial={false}>
        {online ? (
          <motion.div key="on" className="sy-pasek" data-online role="status" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <span className="sy-pasek-ikona" aria-hidden>
              <svg width="14" height="14" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M2.5 6.3 5 8.6l4.5-5" />
              </svg>
            </span>
            <span>
              <b>Znowu online.</b> Typy i kursy odświeżone.
            </span>
          </motion.div>
        ) : (
          <motion.div key="off" className="sy-pasek" role="status" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <span className="sy-pasek-ikona" aria-hidden>
              <IkonaBezSieci />
            </span>
            <span>
              <b>Brak internetu.</b> Widzisz typy i kursy z 22:28 – odświeżymy je sami, gdy wróci zasięg.
            </span>
          </motion.div>
        )}
      </AnimatePresence>
      <div className="st-naglowek" style={{ marginTop: 18 }}>
        <h1 className="p-n">Zawodnicy</h1>
        <p>
          <span>Codziennie sprawdzamy ponad 1600 zakładów.</span> <span>Zostawiamy te, które wchodzą najczęściej.</span>
        </p>
      </div>
      <div className="sy-atrapa" aria-hidden>
        {[0, 1, 2, 3].map((i) => (
          <div key={i} />
        ))}
      </div>
    </main>
  );
}

/* ---- rama strony -------------------------------------------------------- */

export type StartSystemowych = Record<string, string | undefined>;

export function Systemowe({ dane, start }: { dane: DaneSystemowe; start: StartSystemowych }) {
  const [motyw, setMotyw] = useState<Motyw>(start.m === "jasny" ? "jasny" : "ciemny");
  const [wybory, setWybory] = useState<Record<string, string>>(() =>
    Object.fromEntries(SEKCJE.map((x) => [x.klucz, x.warianty.some((w) => w.id === start[x.klucz]) ? start[x.klucz]! : x.warianty[0].id])),
  );
  const [stanLogin, setStanLogin] = useState<StanLogowania>("zwykly");
  const [stan404, setStan404] = useState<Stan404>("zwykla");
  const [online, setOnline] = useState<"off" | "on">("off");
  useEffect(() => {
    if (online !== "on") return;
    const t = setTimeout(() => setOnline("off"), 3500);
    return () => clearTimeout(t);
  }, [online]);
  const [paleta, setPaleta] = useState<string | null>(null);
  const [aktywne, setAktywne] = useState<Record<string, string>>({});

  useEffect(() => {
    window.history.replaceState(null, "", `?${new URLSearchParams({ m: motyw, ...wybory })}`);
  }, [motyw, wybory]);

  const zmienMotyw = () => setMotyw((m) => (m === "ciemny" ? "jasny" : "ciemny"));
  const jasneLogo = motyw === "ciemny";
  const liczby = { zawodnicy: dane.strony.wszystkie.filter((t) => !t.druzynowy).length, druzyny: dane.strony.wszystkie.filter((t) => t.druzynowy).length };

  const tresc = (klucz: string, w: string, telefon: boolean) => {
    const szukaj = () => setPaleta(`${telefon ? "telefon" : "komputer"}-${klucz}`);
    if (klucz === "404") return <NieMa stan={stan404} szukaj={szukaj} dane={dane} />;
    if (klucz === "blad") return <Blad />;
    return <BrakInternetu wariant={w} online={online === "on"} />;
  };

  const scena = (klucz: string, w: string) => {
    if (klucz === "login") {
      return (
        <div className="st-sceny">
          <Segment etykieta="stan" wartosc={stanLogin} zmien={setStanLogin} opcje={STANY_LOGOWANIA} />
          <div className="s-okno sy-okno-login">
            <Logowanie key={`${w}-${stanLogin}`} telefon={false} jasneLogo={jasneLogo} stan={stanLogin} motyw={motyw} zmienMotyw={zmienMotyw} dane={dane} />
          </div>
          <div className="s-telefon-rama">
            <div className="s-telefon sy-telefon-login">
              <Logowanie key={`${w}-${stanLogin}`} telefon jasneLogo={jasneLogo} stan={stanLogin} motyw={motyw} zmienMotyw={zmienMotyw} dane={dane} />
            </div>
          </div>
        </div>
      );
    }
    const aktywna = aktywne[klucz] ?? (klucz === "offline" && w === "pasek" ? "zawodnicy" : "");
    const ustaw = (k: string) => setAktywne((a) => ({ ...a, [klucz]: k }));
    return (
      <div className="st-sceny">
        {klucz === "offline" && w === "pasek" && (
          <Segment
            etykieta="pokaz"
            wartosc={online}
            zmien={setOnline}
            opcje={[
              ["off", "Brak internetu"],
              ["on", "Zasięg wrócił (pasek znika po 3 s)"],
            ]}
          />
        )}
        {klucz === "404" && (
          <Segment
            etykieta="przypadek"
            wartosc={stan404}
            zmien={setStan404}
            opcje={[
              ["zwykla", "Zły adres"],
              ["mecz", "Mecz się skończył"],
            ]}
          />
        )}
        <div style={{ position: "relative" }}>
          <div className="s-okno sy-okno">
            <MenuKomputerPlus
              jasneLogo={jasneLogo}
              aktywna={aktywna}
              ustaw={ustaw}
              liczby={liczby}
              prawa={<PrawaStrona motyw={motyw} zmienMotyw={zmienMotyw} stan={klucz === "offline" && online === "off" ? "offline" : "swieze"} szukaj={() => setPaleta(`komputer-${klucz}`)} />}
            >
              {tresc(klucz, w, false)}
              <StopkaPlus jasneLogo={jasneLogo} />
            </MenuKomputerPlus>
          </div>
          <AnimatePresence>{paleta === `komputer-${klucz}` && <Paleta dane={dane.strony} zamknij={() => setPaleta(null)} />}</AnimatePresence>
        </div>
        <div className="s-telefon-rama">
          <div style={{ position: "relative", height: 700 }}>
            <MenuTelefon wariant="a" aktywna={aktywna} ustaw={ustaw} motyw={motyw} zmienMotyw={zmienMotyw} stan={klucz === "offline" && online === "off" ? "offline" : "swieze"} szukaj={() => setPaleta(`telefon-${klucz}`)}>
              {tresc(klucz, w, true)}
              <StopkaPlus jasneLogo={jasneLogo} />
            </MenuTelefon>
            <AnimatePresence>{paleta === `telefon-${klucz}` && <Paleta dane={dane.strony} zamknij={() => setPaleta(null)} />}</AnimatePresence>
          </div>
        </div>
      </div>
    );
  };

  return (
    <MotionConfig reducedMotion="user">
      <div className="p-pulpit">
        <div className="p-pulpit-wnetrze">
          <div className="p-pulpit-tytul">
            Etap 5 <span>· strony systemowe</span>
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
        </div>
        <div className="p-pulpit-opis">Logowanie, 404, błąd i brak internetu. Menu i stopka z etapu 4. Liczby z migawki 30.09.</div>
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
              wybrany={wybory[x.klucz]}
              zmien={(id) => setWybory((s) => ({ ...s, [x.klucz]: id }))}
            >
              {scena(x.klucz, wybory[x.klucz])}
            </Sekcja>
          ))}
        </div>
      </div>
    </MotionConfig>
  );
}
