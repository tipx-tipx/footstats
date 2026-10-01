"use client";

import { useEffect, useMemo, useState } from "react";

import { fmtKurs, fmtLinia } from "@/lib/format";

import type { DaneFundamentow, LigaV, TypV } from "../_dane/przygotuj";
import { FlagaLigi, Herb, type TrybHerbow } from "./Herb";
import { LogoPoziome } from "./LogoPoziome";
import { Poprzeczka } from "./Poprzeczka";

type Motyw = "ciemny" | "jasny";
type Szerokosc = "pelna" | "telefon";

export type Wariant = { id: string; nazwa: string; opis: string };

/** Co porównujemy na danej stronie warsztatu – strona (serwer) podaje listy. */
export type KonfigWarsztatu = {
  etap: string;
  podtytul: string;
  palety: Record<Motyw, Wariant[]>;
  fonty: Wariant[];
  /** false = herby ustalone (wariant B: prawdziwe z tarczą jako zapasem) */
  przelacznikHerbow: boolean;
};

const MENU = ["Zawodnicy", "Drużyny", "Kupony", "Mecze"];
const MENU_ZAUFANIE = ["Skuteczność", "Jak to działa"];

function Segmenty<T extends string>({
  wartosc,
  opcje,
  zmien,
}: {
  wartosc: T;
  opcje: [T, string][];
  zmien: (v: T) => void;
}) {
  return (
    <div className="p-segmenty" role="group">
      {opcje.map(([v, etykieta]) => (
        <button key={v} type="button" aria-pressed={wartosc === v} onClick={() => zmien(v)}>
          {etykieta}
        </button>
      ))}
    </div>
  );
}

/* ---- elementy ekranu --------------------------------------------------- */

function WierszMeczu({ m, herby }: { m: LigaV["mecze"][number]; herby: TrybHerbow }) {
  return (
    <div className="p-mecz">
      <div className="p-czas">
        <span>{m.godzina}</span>
      </div>
      <div className="p-druzyny">
        <div className="p-druzyna">
          <Herb d={m.gosp} tryb={herby} />
          <span>{m.gosp.nazwa}</span>
        </div>
        <div className="p-druzyna">
          <Herb d={m.gosc} tryb={herby} />
          <span>{m.gosc.nazwa}</span>
        </div>
      </div>
      <div className="p-okazje">
        {m.okazje > 0 ? (
          <>
            <b>{m.okazje}</b>
            <span>{m.okazje === 1 ? "typ" : m.okazje < 5 ? "typy" : "typów"}</span>
          </>
        ) : (
          <span className="p-brak">bez typów</span>
        )}
      </div>
    </div>
  );
}

function KartaTypu({ t, herby }: { t: TypV; herby: TrybHerbow }) {
  const strona = t.strona === "ponizej" ? "poniżej" : "powyżej";
  return (
    <article className="p-karta">
      <div className="p-karta-meta">
        <Herb d={t.druzyna} tryb={herby} rozmiar={16} />
        <span>
          {t.druzyna.nazwa} – {t.rywal.nazwa}
        </span>
        <span style={{ marginLeft: "auto", flex: "none" }}>
          {t.dzien}, {t.godzina}
        </span>
      </div>
      <div className="p-karta-glowa">
        <div style={{ minWidth: 0 }}>
          <h3 className="p-n p-kto">{t.kto}</h3>
          <div className="p-kto-pod">
            {t.pozycja} · {t.druzyna.nazwa}
          </div>
        </div>
        <div className="p-szansa">
          <b className="p-n">{Math.round(t.szansa * 100)}%</b>
          <small>nasza szansa</small>
        </div>
      </div>
      <div className="p-zaklad">
        <div className="p-zaklad-co">
          {t.rynek} <span>{strona}</span> {fmtLinia(t.linia)}
        </div>
        <button type="button" className="p-kurs">
          <small>{t.bukmacher}</small>
          <b className="p-n">{fmtKurs(t.kurs)}</b>
        </button>
      </div>
      <Poprzeczka historia={t.historia} rywale={t.rywale} linia={t.linia} strona={t.strona} />
    </article>
  );
}

function Wynik({ rodzaj }: { rodzaj: "ok" | "nie" | "zwrot" | "czeka" }) {
  const ikony = {
    ok: <path d="M2.5 6.5 5 9l4.5-6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />,
    nie: <path d="m3 3 6 6M9 3 3 9" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />,
    zwrot: <path d="M9.5 6A3.5 3.5 0 1 1 8.4 3.5M9.5 1.8v2.4H7.1" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />,
    czeka: (
      <>
        <circle cx="6" cy="6" r="4.2" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M6 3.8V6l1.5 1" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </>
    ),
  };
  const tekst = { ok: "weszło", nie: "nie weszło", zwrot: "zwrot", czeka: "czeka" };
  return (
    <span className={`p-wynik p-wynik-${rodzaj}`}>
      <svg viewBox="0 0 12 12" aria-hidden>
        {ikony[rodzaj]}
      </svg>
      {tekst[rodzaj]}
    </span>
  );
}

const KOLORY: [string, string][] = [
  ["--tlo", "tło"],
  ["--pow1", "karta"],
  ["--pow2", "kafelek"],
  ["--pow3", "najechanie"],
  ["--t1", "tekst"],
  ["--t2", "tekst 2"],
  ["--t3", "opis"],
  ["--akcja", "akcja"],
  ["--marka", "marka"],
  ["--ok", "weszło"],
  ["--nie", "nie weszło"],
  ["--czeka", "czeka"],
];

function Ekran({
  motyw,
  paleta,
  font,
  herby,
  dane,
  dzien,
  ustawDzien,
}: {
  motyw: Motyw;
  paleta: string;
  font: string;
  herby: TrybHerbow;
  dane: DaneFundamentow;
  dzien: string;
  ustawDzien: (d: string) => void;
}) {
  const ligiDnia = useMemo(
    () =>
      dane.ligi
        .map((l) => ({ ...l, mecze: l.mecze.filter((m) => m.dzien === dzien) }))
        .filter((l) => l.mecze.length > 0)
        .sort((a, b) => b.mecze.reduce((s, m) => s + m.okazje, 0) - a.mecze.reduce((s, m) => s + m.okazje, 0))
        .slice(0, 4)
        .map((l) => ({ ...l, mecze: l.mecze.slice(0, 5) })),
    [dane.ligi, dzien],
  );
  const wszystkich = dane.ligi.reduce((s, l) => s + l.mecze.length, 0);
  const uzasadnienie = dane.typy.find((t) => t.uzasadnienie)?.uzasadnienie;

  return (
    <div className="p-ekran" data-p-motyw={motyw} data-p-paleta={paleta} data-p-font={font}>
      <header className="p-pasek">
        <LogoPoziome jasne={motyw === "ciemny"} />
        <nav className="p-menu" aria-label="Menu (podgląd)">
          {MENU.map((m, i) => (
            <a key={m} href="#" aria-current={i === 0 ? "page" : undefined} onClick={(e) => e.preventDefault()}>
              {m}
            </a>
          ))}
          <span className="p-menu-kreska" aria-hidden />
          {MENU_ZAUFANIE.map((m) => (
            <a key={m} href="#" onClick={(e) => e.preventDefault()}>
              {m}
            </a>
          ))}
        </nav>
        <div className="p-swiezosc">
          <i aria-hidden />
          <span>kursy z 22:28</span>
        </div>
      </header>

      <div className="p-tresc">
        <h1 className="p-n p-tytul">Mecze i typy</h1>
        <p className="p-t3" style={{ marginTop: 6 }}>
          {wszystkich} meczów w analizie · {dane.typy.length} najmocniejsze typy poniżej
        </p>

        <div className="p-dni" role="group" aria-label="Dzień">
          {dane.dni.map((d) => (
            <button
              key={d.klucz}
              type="button"
              className="p-dzien"
              aria-pressed={d.klucz === dzien}
              onClick={() => ustawDzien(d.klucz)}
            >
              {d.etykieta}
              <small>{d.ile}</small>
            </button>
          ))}
        </div>

        <div className="p-siatka">
          <div>
            {ligiDnia.map((l) => (
              <section key={l.nazwa} className="p-liga">
                <div className="p-liga-glowa">
                  <FlagaLigi flaga={l.flaga} id={l.id} c1={l.c1} c2={l.c2} tryb={herby} />
                  <b>{l.nazwa}</b>
                  <span>{l.kategoria}</span>
                  <em>{l.mecze.length}</em>
                </div>
                {l.mecze.map((m) => (
                  <WierszMeczu key={m.id} m={m} herby={herby} />
                ))}
              </section>
            ))}
          </div>

          <div>
            {dane.typy.map((t) => (
              <KartaTypu key={t.id} t={t} herby={herby} />
            ))}
            <div className="p-przyciski">
              <button type="button" className="p-guzik p-guzik-glowny">
                Dodaj do kuponu <span>3 typy · ×{fmtKurs(dane.typy.reduce((k, t) => k * t.kurs, 1))}</span>
              </button>
              <button type="button" className="p-guzik p-guzik-drugi">
                Skąd te liczby
              </button>
            </div>
          </div>
        </div>

        <div className="p-arkusz">
          <section>
            <h3>Typografia</h3>
            <div className="p-probka">
              <small>tytuł strony · 30</small>
              <div className="p-n p-tytul-probka" style={{ fontSize: 30 }}>
                Czwartek, 1 października
              </div>
            </div>
            <div className="p-probka">
              <small>nagłówek · 20</small>
              <div className="p-n" style={{ fontSize: 20 }}>
                Żółte kartki: zawodnik zbiera je w 7 z 10 meczów
              </div>
            </div>
            <div className="p-probka">
              <small>tekst · 14</small>
              <p className="p-t2" style={{ maxWidth: 560 }}>
                {uzasadnienie ?? "Średnio 5,2 na mecz (próba: 20 meczów, ostatnie 5 meczów: 6,0)."}
              </p>
            </div>
            <div className="p-probka">
              <small>liczby (równa szerokość cyfr)</small>
              <div className="p-n p-liczby" style={{ fontSize: 22, display: "flex", gap: 22, flexWrap: "wrap" }}>
                <span>1,34</span>
                <span>73%</span>
                <span>×10,00</span>
                <span>0,5</span>
                <span>1:0</span>
                <span>90&apos;</span>
              </div>
            </div>
          </section>
          <section>
            <h3>Kolory</h3>
            <div className="p-probki-kolorow">
              {KOLORY.map(([v, n]) => (
                <div key={v} className="p-kolor">
                  <i style={{ background: `var(${v})` }} />
                  {n}
                </div>
              ))}
            </div>
            <div className="p-wyniki">
              <Wynik rodzaj="ok" />
              <Wynik rodzaj="nie" />
              <Wynik rodzaj="zwrot" />
              <Wynik rodzaj="czeka" />
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

/* ---- pulpit ------------------------------------------------------------ */

export type StartFundamentow = {
  m?: string;
  p?: string;
  f?: string;
  h?: string;
  s?: string;
};

const jedenZ = <const T extends string>(v: string | undefined, dozwolone: readonly T[], domyslna: T): T =>
  dozwolone.includes(v as T) ? (v as T) : domyslna;

export function Fundamenty({
  dane,
  start,
  konfig,
}: {
  dane: DaneFundamentow;
  start: StartFundamentow;
  konfig: KonfigWarsztatu;
}) {
  // stan w adresie: link „?m=ciemny&p=2&f=2b” mówi dokładnie, który wariant
  // właściciel wybrał – bez opisywania go słowami. Paleta idzie NUMEREM, bo
  // ciemne i jasne warianty mają różne nazwy, a przełączanie motywu ma
  // zostawać na tej samej pozycji.
  const ilePalet = Math.max(konfig.palety.ciemny.length, konfig.palety.jasny.length);
  const numery = Array.from({ length: ilePalet }, (_, i) => String(i + 1));
  const [motyw, setMotyw] = useState<Motyw>(jedenZ(start.m, ["ciemny", "jasny"], "ciemny"));
  const [paleta, setPaleta] = useState<string>(jedenZ(start.p, [...numery, "wszystkie"], "1"));
  const [font, setFont] = useState<string>(
    jedenZ(start.f, konfig.fonty.map((f) => f.id), konfig.fonty[0].id),
  );
  const [herby, setHerby] = useState<TrybHerbow>(
    konfig.przelacznikHerbow ? jedenZ(start.h, ["tarcza", "prawdziwy"], "tarcza") : "prawdziwy",
  );
  const [szer, setSzer] = useState<Szerokosc>(jedenZ(start.s, ["pelna", "telefon"], "pelna"));
  const [dzien, setDzien] = useState(dane.dni[0]?.klucz ?? "");

  useEffect(() => {
    const q = new URLSearchParams({ m: motyw, p: paleta, f: font, h: herby, s: szer });
    window.history.replaceState(null, "", `?${q}`);
  }, [motyw, paleta, font, herby, szer]);

  const lista = konfig.palety[motyw];
  const palety = paleta === "wszystkie" ? lista : [lista[Number(paleta) - 1] ?? lista[0]];
  const wybranyFont = konfig.fonty.find((f) => f.id === font) ?? konfig.fonty[0];

  return (
    <>
      <div className="p-pulpit">
        <div className="p-pulpit-wnetrze">
          <div className="p-pulpit-tytul">
            {konfig.etap} <span>· {konfig.podtytul}</span>
          </div>
          <div className="p-wybor">
            <span>motyw</span>
            <Segmenty
              wartosc={motyw}
              zmien={setMotyw}
              opcje={[
                ["ciemny", "Ciemny"],
                ["jasny", "Jasny"],
              ]}
            />
          </div>
          <div className="p-wybor">
            <span>paleta</span>
            <Segmenty
              wartosc={paleta}
              zmien={setPaleta}
              opcje={[
                ...lista.map((w, i): [string, string] => [String(i + 1), w.nazwa]),
                ["wszystkie", "Obok siebie"],
              ]}
            />
          </div>
          {konfig.fonty.length > 1 && (
            <div className="p-wybor">
              <span>fonty</span>
              <Segmenty
                wartosc={font}
                zmien={setFont}
                opcje={konfig.fonty.map((f): [string, string] => [f.id, f.nazwa])}
              />
            </div>
          )}
          {konfig.przelacznikHerbow && (
            <div className="p-wybor">
              <span>herby</span>
              <Segmenty
                wartosc={herby}
                zmien={setHerby}
                opcje={[
                  ["tarcza", "Tarcze w barwach"],
                  ["prawdziwy", "Prawdziwe"],
                ]}
              />
            </div>
          )}
          <div className="p-wybor">
            <span>ekran</span>
            <Segmenty
              wartosc={szer}
              zmien={setSzer}
              opcje={[
                ["pelna", "Komputer"],
                ["telefon", "Telefon"],
              ]}
            />
          </div>
        </div>
        <div className="p-pulpit-opis">
          {palety.map((p) => (
            <div key={p.id}>
              <b>{p.nazwa}</b> – {p.opis}
            </div>
          ))}
          <div>
            <b>{wybranyFont.nazwa}</b> – {wybranyFont.opis}
          </div>
        </div>
      </div>

      <div className="p-obok" data-ile={szer === "pelna" ? palety.length : 1}>
        {palety.map((p) => {
          const ekran = (
            <Ekran
              motyw={motyw}
              paleta={p.id}
              font={wybranyFont.id}
              herby={herby}
              dane={dane}
              dzien={dzien}
              ustawDzien={setDzien}
            />
          );
          return (
            <div key={p.id}>
              {palety.length > 1 && <div className="p-etykieta-ramy">{p.nazwa}</div>}
              {szer === "telefon" ? <div className="p-rama-telefon">{ekran}</div> : ekran}
            </div>
          );
        })}
      </div>
    </>
  );
}
