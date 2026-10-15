"use client";

import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { fmtLinia } from "@/lib/format";

import type { MeczE } from "../../_dane/elementy";
import type { DaneLinii } from "../../_dane/linie";
import { Krzyzyk } from "../atomy/wspolne";
import { IkonaKoszulka, IkonaZegar, Segment } from "../atomy2/filtry2";
import { PrzewijanyRzad } from "../atomy2/PrzewijanyRzad";
import { useTeraz } from "../czas";
import { FlagaLigi, Herb } from "../Herb";
import { bezDubli, DOMYSLNE_LINIE, silaPokrycia, taSamaDruzyna, wybierzLinie, type LiniaS, type Okno, type WarunkiLinii, type WybranaLinia } from "../liniePomiar";
import { IkonaSortu, Kurs, MenuWyboru, Weszlo } from "./StronaMeczu";

/*
 * Mecze › „Najlepsze linie” (15.10, właściciel: „żeby dało się znaleźć jak
 * najszybciej najlepsze kursy z najlepszymi pokryciami”). Wzór: skaner
 * konkurencji (wszystkie mecze dnia w jednej tabeli, najlepsza cena
 * podświetlona), u nas z tym, co strona meczu ma lepsze: okno 10 meczów,
 * „nie zagrał” nie liczy się jako pudło, ogłoszony skład, nasz typ.
 *
 * Ograniczenia (właściciel: „przemyślanie ograniczona”, „bez 1,05”):
 *  - jedna linia na zawodnika i rynek – NAJWYŻSZA, która spełnia progi;
 *  - cena od 1,30 już w pipeline, domyślnie od 1,40 i pokrycie od 80%
 *    (pomiar 15.10: 8–55 linii na dzień przy 13–54 meczach);
 *  - 20 wierszy, dalej „Pokaż kolejne”; pusty wynik podpowiada jeden filtr do
 *    zdjęcia.
 * To statystyka, nie nasz typ – jak na stronie meczu.
 */

const RYNKI: Record<string, string> = {
  shots: "Strzały",
  sot: "Strzały celne",
  shots_outside_box: "Strzały zza pola",
  sot_outside_box: "Celne zza pola",
  headed_shots: "Strzały głową",
  headed_sot: "Celne głową",
  fouls_committed: "Faule popełnione",
  fouls_won: "Faule wywalczone",
  tackles: "Odbiory",
  offsides: "Spalone",
  yellow_card: "Żółta kartka",
};

const SORTY: [Sort, string][] = [
  ["pokrycie", "Pokrycie"],
  ["kurs", "Najwyższy kurs"],
  ["godzina", "Najbliższy mecz"],
];
type Sort = "pokrycie" | "kurs" | "godzina";
const NA_STRONE = 20;

export const odmLinia = (n: number) => (n === 1 ? "linia" : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? "linie" : "linii");
const kursTxt = (k: number) => k.toFixed(2).replace(".", ",");
const norm = (s: string) =>
  s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/ł/g, "l");

type Gracz = { wkrotce: boolean; sklady: boolean; rynek: string; liga: string; tekst: string };
const GRACZ_PUSTY: Gracz = { wkrotce: false, sklady: false, rynek: "", liga: "", tekst: "" };

function IkonaLupa() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" aria-hidden>
      <circle cx="6.5" cy="6.5" r="4.6" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="m10 10 3.2 3.2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function Kratki({ v, min, linia, okno }: { v: number[]; min: number[]; linia: number; okno: Okno }) {
  const mecze = v.slice(0, okno).map((x, i) => ({ x, m: min[i] ?? 90 }));
  return (
    <span className="mz-kratki" aria-label={`ostatnie mecze od najnowszego: ${mecze.map((m) => (m.m > 0 ? m.x : "nie zagrał")).join(", ")}`}>
      {mecze.map((m, i) => (
        <i key={i} data-s={m.m <= 0 ? "nz" : m.x > linia ? "ok" : "nie"}>
          {m.m > 0 ? m.x : ""}
        </i>
      ))}
    </span>
  );
}

export function NajlepszeLinie({
  dane,
  mecze,
  telefon,
  otworz,
}: {
  dane: DaneLinii | null;
  /** mecze wybranego dnia (z kursami na zawodników) */
  mecze: MeczE[];
  telefon: boolean;
  otworz?: (id: number, gdzie: { rynek: string; linia: number }) => void;
}) {
  const TERAZ = useTeraz();
  const [prog, setProg] = useState<WarunkiLinii>(DOMYSLNE_LINIE);
  const [roboczy, setRoboczy] = useState<WarunkiLinii>(DOMYSLNE_LINIE);
  const [g, setG] = useState<Gracz>(GRACZ_PUSTY);
  const [sort, setSort] = useState<Sort>("pokrycie");
  const [otwarty, setOtwarty] = useState(false);
  const [szukajOtwarte, setSzukajOtwarte] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const przycisk = useRef<HTMLButtonElement>(null);
  const idRynkow = useId();
  const idListy = useId();

  const poId = useMemo(() => new Map(mecze.map((m) => [m.id, m])), [mecze]);
  const naLiscie = useMemo(() => new Set(dane?.naLiscie ?? []), [dane]);

  // linie dnia: tylko mecze z listy (wybrany dzień, nie zaczęte)
  const dnia: LiniaS[] = useMemo(() => (dane?.linie ?? []).filter((s) => poId.has(s[0]) && poId.get(s[0])!.ts > TERAZ), [dane, poId, TERAZ]);

  const pasuje = (s: LiniaS, x: Gracz) => {
    const m = poId.get(s[0])!;
    const z = dane!.zaw[String(s[1])];
    if (x.wkrotce && m.ts - TERAZ > 3 * 3600) return false;
    if (x.sklady && !(m.sklady && z?.xi)) return false;
    if (x.rynek && s[2] !== x.rynek) return false;
    if (x.liga && m.liga !== x.liga) return false;
    if (x.tekst) {
      const q = norm(x.tekst);
      if (![z?.nazwa ?? "", m.gosp.nazwa, m.gosc.nazwa].some((t) => norm(t).includes(q))) return false;
    }
    return true;
  };

  const nazwa = (id: number) => dane?.zaw[String(id)]?.nazwa ?? "";
  const policz = (w: WarunkiLinii, x: Gracz) => (dane ? bezDubli(wybierzLinie(dnia, dane.forma, w, (s) => pasuje(s, x)), nazwa) : []);

  const wynik = useMemo(() => {
    const lista = policz(prog, g);
    const ts = (w: WybranaLinia) => poId.get(w.s[0])!.ts;
    lista.sort((a, b) =>
      sort === "kurs"
        ? b.cena.kurs - a.cena.kurs || silaPokrycia(b.p) - silaPokrycia(a.p)
        : sort === "godzina"
          ? ts(a) - ts(b) || silaPokrycia(b.p) - silaPokrycia(a.p) || b.cena.kurs - a.cena.kurs
          : silaPokrycia(b.p) - silaPokrycia(a.p) || b.cena.kurs - a.cena.kurs,
    );
    return lista;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dnia, dane, prog, g, sort, TERAZ]);

  // liczniki rynków i lig: przy wszystkich innych filtrach
  const rynki = useMemo(() => {
    const m = new Map<string, number>();
    for (const w of policz(prog, { ...g, rynek: "" })) m.set(w.s[2], (m.get(w.s[2]) ?? 0) + 1);
    return Object.keys(RYNKI).filter((k) => m.has(k)).map((k) => [k, m.get(k)!] as [string, number]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dnia, dane, prog, g.wkrotce, g.sklady, g.liga, g.tekst, TERAZ]);
  const ligi = useMemo(() => {
    const m = new Map<string, { n: number; mecz: MeczE }>();
    for (const w of policz(prog, { ...g, liga: "" })) {
      const mecz = poId.get(w.s[0])!;
      m.set(mecz.liga, { n: (m.get(mecz.liga)?.n ?? 0) + 1, mecz });
    }
    return [...m.entries()].sort((a, b) => b[1].n - a[1].n);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dnia, dane, prog, g.wkrotce, g.sklady, g.rynek, g.tekst, TERAZ]);
  const bezRynku = rynki.reduce((s, [, n]) => s + n, 0);
  const wRoboczym = otwarty ? policz(roboczy, g).length : 0;
  // liczniki przełączników: ile linii zostanie po włączeniu (przy pozostałych filtrach)
  const ileSkladow = policz(prog, { ...g, sklady: true }).length;
  const ileWkrotce = policz(prog, { ...g, wkrotce: true }).length;

  // pusty wynik: który JEDEN warunek zdjąć, żeby coś się pojawiło
  const ratunek = useMemo(() => {
    if (wynik.length || !dane) return null;
    const proby: { opis: string; w: WarunkiLinii; x: Gracz; zastosuj: () => void }[] = [
      { opis: "przy pokryciu od 70%", w: { ...prog, pokrycie: 0.7 }, x: g, zastosuj: () => setProg((p) => ({ ...p, pokrycie: 0.7 })) },
      { opis: "przy kursie od 1,30", w: { ...prog, kurs: 1.3 }, x: g, zastosuj: () => setProg((p) => ({ ...p, kurs: 1.3 })) },
      { opis: "w oknie 5 meczów", w: { ...prog, okno: 5 }, x: g, zastosuj: () => setProg((p) => ({ ...p, okno: 5 })) },
      { opis: "bez „Wkrótce”", w: prog, x: { ...g, wkrotce: false }, zastosuj: () => setG((x) => ({ ...x, wkrotce: false })) },
      { opis: "bez „Pewne składy”", w: prog, x: { ...g, sklady: false }, zastosuj: () => setG((x) => ({ ...x, sklady: false })) },
      { opis: "we wszystkich rynkach", w: prog, x: { ...g, rynek: "" }, zastosuj: () => setG((x) => ({ ...x, rynek: "" })) },
      { opis: "we wszystkich rozgrywkach", w: prog, x: { ...g, liga: "" }, zastosuj: () => setG((x) => ({ ...x, liga: "" })) },
      { opis: "bez szukania", w: prog, x: { ...g, tekst: "" }, zastosuj: () => setG((x) => ({ ...x, tekst: "" })) },
    ];
    const oceny = proby
      .filter((p) => JSON.stringify([p.w, p.x]) !== JSON.stringify([prog, g]))
      .map((p) => ({ ...p, ile: policz(p.w, p.x).length }))
      .filter((p) => p.ile > 0)
      .sort((a, b) => b.ile - a.ile);
    return oceny[0] ?? null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wynik.length, dnia, dane, prog, g, TERAZ]);

  // nowy filtr = lista od początku (licznik „Pokaż kolejne” należy do zestawu filtrów; dzień zmienia `key` całości)
  const kluczListy = `${JSON.stringify(prog)}|${JSON.stringify(g)}|${sort}`;
  const [rozwiniete, setRozwiniete] = useState({ klucz: kluczListy, ile: NA_STRONE });
  const ile = rozwiniete.klucz === kluczListy ? rozwiniete.ile : NA_STRONE;

  useEffect(() => {
    const klaw = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOtwarty(false);
      }
    };
    const klik = (e: MouseEvent) => {
      const c = e.target as Node;
      if (!telefon && panelRef.current && !panelRef.current.contains(c) && !przycisk.current?.contains(c)) setOtwarty(false);
    };
    document.addEventListener("keydown", klaw);
    document.addEventListener("mousedown", klik);
    return () => {
      document.removeEventListener("keydown", klaw);
      document.removeEventListener("mousedown", klik);
    };
  }, [telefon]);

  const zmienioneProgi = (prog.pokrycie !== DOMYSLNE_LINIE.pokrycie ? 1 : 0) + (prog.kurs !== DOMYSLNE_LINIE.kurs ? 1 : 0) + (prog.okno !== DOMYSLNE_LINIE.okno ? 1 : 0);

  if (!dane) {
    return (
      <div className="d-pusty">
        <div className="p-n" style={{ fontSize: 17 }}>
          Linie pojawią się po najbliższym odświeżeniu danych
        </div>
        <p>Liczymy je co kilkadziesiąt minut ze wszystkich meczów z kursami na zawodników.</p>
      </div>
    );
  }

  const pokazPole = !telefon || szukajOtwarte;

  return (
    <div className="e-rama nl">
      {/* rozgrywki – w tym samym miejscu co na liście meczów, liczniki to linie */}
      {ligi.length > 1 && (
        <div className="sm-ligi" role="group" aria-label="Rozgrywki">
          <button type="button" className="sm-liga" aria-pressed={!g.liga} onClick={() => setG((x) => ({ ...x, liga: "" }))}>
            Wszystkie <small>{ligi.reduce((s, [, v]) => s + v.n, 0)}</small>
          </button>
          {ligi.map(([nazwa, { n, mecz }]) => (
            <button key={nazwa} type="button" className="sm-liga" aria-pressed={g.liga === nazwa} onClick={() => setG((x) => ({ ...x, liga: x.liga === nazwa ? "" : nazwa }))}>
              <FlagaLigi flaga={mecz.ligaFlaga} id={mecz.ligaId} c1={mecz.ligaC1} c2={mecz.ligaC2} tryb="prawdziwy" />
              {nazwa}
              <small>{n}</small>
            </button>
          ))}
        </div>
      )}

      {/* pasek: szukaj · przełączniki z licznikami · sortuj · progi z wartościami.
          Jak na stronie meczu: „Sortuj: …” i przycisk, który mówi, co jest ustawione. */}
      <div className="e-pasek f-pasek nl-pasek">
        <div className="e-lewa">
          {pokazPole ? (
            <div className="f-szukaj nl-szukaj">
              <IkonaLupa />
              <input
                type="search"
                value={g.tekst}
                placeholder={telefon ? "Zawodnik, drużyna" : "Szukaj zawodnika albo drużyny"}
                aria-label="Szukaj zawodnika albo drużyny"
                autoFocus={telefon && szukajOtwarte}
                onChange={(e) => setG((x) => ({ ...x, tekst: e.target.value }))}
                onKeyDown={(e) => {
                  if (e.key === "Escape" && telefon && !g.tekst) setSzukajOtwarte(false);
                }}
              />
              {g.tekst && (
                <button type="button" className="f-szukaj-x" aria-label="Wyczyść szukanie" onClick={() => setG((x) => ({ ...x, tekst: "" }))}>
                  <Krzyzyk rozmiar={9} />
                </button>
              )}
            </div>
          ) : (
            <button type="button" className="e-menu-guzik d-dotyk" aria-label="Szukaj zawodnika albo drużyny" onClick={() => setSzukajOtwarte(true)}>
              <IkonaLupa />
            </button>
          )}
          {!(telefon && szukajOtwarte) && (
            <>
              <button
                type="button"
                className="e-przelacznik d-dotyk"
                aria-pressed={g.wkrotce}
                disabled={ileWkrotce === 0 && !g.wkrotce}
                onClick={() => setG((x) => ({ ...x, wkrotce: !x.wkrotce }))}
                title={ileWkrotce === 0 && !g.wkrotce ? "Żaden mecz nie zaczyna się w ciągu 3 godzin" : "Mecze, które zaczynają się w ciągu 3 godzin"}
              >
                <IkonaZegar />
                Wkrótce
                {!g.wkrotce && ileWkrotce > 0 && <small className="nl-ile">{ileWkrotce}</small>}
              </button>
              {/* składy ogłaszane są ok. godzinę przed meczem – wcześniej przełącznik nie ma czego pokazać */}
              {(ileSkladow > 0 || g.sklady) && (
                <button type="button" className="e-przelacznik d-dotyk" aria-pressed={g.sklady} onClick={() => setG((x) => ({ ...x, sklady: !x.sklady }))} title="Tylko zawodnicy z ogłoszonego składu">
                  <IkonaKoszulka />
                  {telefon ? "Składy" : "Pewne składy"}
                  {!g.sklady && <small className="nl-ile">{ileSkladow}</small>}
                </button>
              )}
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
              setG((x) => ({ ...x, tekst: "" }));
            }}
          >
            Anuluj
          </button>
        ) : (
          <div className="e-prawa">
            <MenuWyboru etykieta="Sortuj" ikona={<IkonaSortu />} opcje={SORTY} wartosc={sort} zmien={setSort} />
            <span className="nl-progi-guzik">
              <button
                ref={przycisk}
                type="button"
                className="e-menu-guzik d-dotyk"
                aria-haspopup="dialog"
                aria-expanded={otwarty}
                aria-label={`Progi: pokrycie od ${Math.round(prog.pokrycie * 100)}%, kurs od ${kursTxt(prog.kurs)}, ostatnie ${prog.okno} meczów`}
                title={`Pokrycie od ${Math.round(prog.pokrycie * 100)}%, kurs od ${kursTxt(prog.kurs)}, ostatnie ${prog.okno} meczów – kliknij, żeby zmienić`}
                data-aktywny={zmienioneProgi > 0 ? "true" : undefined}
                onClick={() => {
                  setRoboczy(prog);
                  setOtwarty((o) => !o);
                }}
              >
                <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
                  <path d="M2 3.5h10M4 7h6M6 10.5h2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
                <span className="e-etykieta-sortu">
                  {Math.round(prog.pokrycie * 100)}% · od {kursTxt(prog.kurs)}
                  {prog.okno === 5 && " · 5 meczów"}
                </span>
                {zmienioneProgi > 0 && <span className="a-licznik">{zmienioneProgi}</span>}
              </button>
              {!telefon && panel()}
            </span>
          </div>
        )}
      </div>

      {/* rynki – pojedynczy wybór jak na stronie głównej */}
      {rynki.length > 1 && (
        <LayoutGroup id={idRynkow}>
          <PrzewijanyRzad className="f-rynki" role="tablist" ariaLabel="Rynek">
            {[["", bezRynku] as [string, number], ...rynki].map(([r, n]) => (
              <button
                key={r || "wszystkie"}
                type="button"
                role="tab"
                aria-selected={r === g.rynek}
                className="f-rynek"
                onClick={(e) => {
                  setG((x) => ({ ...x, rynek: r }));
                  e.currentTarget.scrollIntoView({ inline: "nearest", block: "nearest", behavior: "smooth" });
                }}
              >
                {r ? RYNKI[r] : "Wszystkie"}
                <sup>{n}</sup>
                {r === g.rynek && <motion.span layoutId="nl-kreska-rynku" className="a-podkreslenie" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
              </button>
            ))}
          </PrzewijanyRzad>
        </LayoutGroup>
      )}

      {/* podpis tabeli: ile linii; progi tekstem tylko na telefonie, gdzie przycisk ma samą ikonę */}
      <div className="nl-progi" aria-live="polite">
        <b>
          {wynik.length} {odmLinia(wynik.length)}
        </b>
        <span className="nl-progi-tel">
          pokrycie od {Math.round(prog.pokrycie * 100)}% · kurs od {kursTxt(prog.kurs)} · ostatnie {prog.okno} meczów
        </span>
        {zmienioneProgi > 0 && (
          <button type="button" className="e-wyczysc" onClick={() => setProg(DOMYSLNE_LINIE)}>
            Przywróć domyślne progi
          </button>
        )}
      </div>

      {wynik.length === 0 ? (
        <div className="d-pusty">
          <div className="p-n" style={{ fontSize: 17 }}>
            {dnia.length ? "Nic tu nie pasuje" : "Ten dzień nie ma jeszcze linii z kursem"}
          </div>
          <p>
            {ratunek
              ? `${ratunek.opis[0].toUpperCase()}${ratunek.opis.slice(1)} byłoby ${ratunek.ile} ${odmLinia(ratunek.ile)}.`
              : dnia.length
                ? "Zmień progi albo wybierz inny dzień."
                : "Bukmacherzy wystawiają kursy na zawodników zwykle dzień przed meczem."}
          </p>
          {ratunek && (
            <button type="button" className="a-guzik" data-t="drugi" data-r="m" onClick={ratunek.zastosuj}>
              Pokaż {ratunek.ile} {odmLinia(ratunek.ile)}
            </button>
          )}
        </div>
      ) : (
        <LayoutGroup id={idListy}>
          <div className="mz-tabela nl-tabela" role="table" aria-label="Najlepsze linie dnia">
            {!telefon && (
              <div className="mz-tr mz-th nl-tr" role="row">
                <span role="columnheader">Zawodnik</span>
                <span role="columnheader">Linia</span>
                <span role="columnheader">Ostatnie {prog.okno} meczów</span>
                <button type="button" role="columnheader" aria-sort={sort === "pokrycie" ? "descending" : "none"} onClick={() => setSort("pokrycie")}>
                  Weszło {sort === "pokrycie" && "↓"}
                </button>
                <button type="button" role="columnheader" aria-sort={sort === "kurs" ? "descending" : "none"} onClick={() => setSort("kurs")}>
                  Kursy {sort === "kurs" && "↓"}
                </button>
              </div>
            )}
            <AnimatePresence initial={false}>
              {wynik.slice(0, ile).map((w) => {
                const [mid, pid, rynek, linia, sb, bc, inaczej] = w.s;
                const m = poId.get(mid)!;
                const z = dane.zaw[String(pid)];
                const f = dane.forma[`${pid}|${rynek}`];
                const strona = taSamaDruzyna(z.druzyna, m.gosc.nazwa) ? m.gosc : taSamaDruzyna(z.druzyna, m.gosp.nazwa) ? m.gosp : null;
                const mamy = naLiscie.has(`${mid}|${pid}|${rynek}`);
                const lepszySb = w.cena.bukmacher === "Superbet";
                const otworzMecz = () => otworz?.(mid, { rynek, linia });
                return (
                  <motion.div
                    key={`${mid}|${pid}|${rynek}`}
                    layout="position"
                    className="mz-tr nl-tr"
                    role="row"
                    tabIndex={otworz ? 0 : undefined}
                    aria-label={`${z.nazwa}, ${RYNKI[rynek]} powyżej ${fmtLinia(linia)}, ${m.gosp.nazwa} – ${m.gosc.nazwa}, otwórz mecz`}
                    onClick={otworzMecz}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        otworzMecz();
                      }
                    }}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ layout: { type: "spring", stiffness: 420, damping: 38 }, opacity: { duration: 0.15 } }}
                  >
                    <span role="cell" className="mz-kto">
                      {strona ? <Herb d={strona} tryb="prawdziwy" rozmiar={18} /> : <span className="nl-bez-herbu" aria-hidden />}
                      <span className="mz-kto-tekst">
                        <b>{z.nazwa}</b>
                        <small>
                          {m.godzina} · {m.gosp.nazwa} – {m.gosc.nazwa}
                        </small>
                      </span>
                      {mamy && (
                        <span className="mz-na-liscie" title="Mamy na to typ na liście dnia">
                          na liście
                        </span>
                      )}
                    </span>
                    <span role="cell" className="nl-linia">
                      <b>
                        {RYNKI[rynek]} <span className="nl-prog">powyżej {fmtLinia(linia)}</span>
                      </b>
                      <small>
                        {z.pozycja}
                        {m.sklady && z.xi && " · w składzie"}
                      </small>
                    </span>
                    <span role="cell" className="nl-kratki">
                      <Kratki v={f[0]} min={f[1]} linia={linia} okno={prog.okno} />
                    </span>
                    <span role="cell">
                      <Weszlo p={w.p} />
                    </span>
                    <span role="cell" className="mz-kursy">
                      <Kurs k={sb} bukmacher="Superbet" lepszy={lepszySb} />
                      <Kurs k={inaczej ? null : bc} bukmacher="Betclic" lepszy={!lepszySb} uwaga={inaczej ? "Betclic liczy tę statystykę inaczej – ceny nie porównujemy" : undefined} />
                    </span>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>
          {wynik.length > ile && (
            <button type="button" className="f-wiecej" onClick={() => setRozwiniete({ klucz: kluczListy, ile: ile + NA_STRONE })}>
              Pokaż kolejne {Math.min(NA_STRONE, wynik.length - ile)}
              <small>z {wynik.length - ile}</small>
            </button>
          )}
        </LayoutGroup>
      )}

      <p className="mz-przypis">
        Dla każdego zawodnika najwyższa linia, którą przebijał przy tych progach, i najlepsza cena. To statystyka, nie nasz typ. Kratka z kreską = nie zagrał (nie liczy się do wyniku). Kliknij linię, żeby zobaczyć cały mecz.
      </p>

      {telefon && panel()}
    </div>
  );

  // zwykła funkcja, nie komponent – komponent zdefiniowany w środku montowałby się od nowa przy każdym renderze
  function panel() {
    return (
      <AnimatePresence>
        {otwarty && telefon && <motion.div key="tlo" className="d-panel-tlo" onClick={() => setOtwarty(false)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />}
        {otwarty && (
          <motion.div
            key="panel"
            ref={panelRef}
            className="d-panel e-panel nl-panel"
            data-tryb={telefon ? "arkusz" : "dymek"}
            role="dialog"
            aria-label="Progi"
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
                  Progi
                </b>
                <button type="button" className="a-guzik" data-t="cichy" data-r="s" onClick={() => setRoboczy(DOMYSLNE_LINIE)}>
                  Domyślne
                </button>
              </div>
            </div>
            <div className="d-panel-tresc">
              <div>
                <h4>Pokrycie</h4>
                <Segment
                  wartosc={String(roboczy.pokrycie)}
                  zmien={(v) => setRoboczy((x) => ({ ...x, pokrycie: Number(v) }))}
                  opcje={[
                    ["0.7", "od 70%"],
                    ["0.8", "od 80%"],
                    ["0.9", "od 90%"],
                    ["1", "100%"],
                  ]}
                />
              </div>
              <div>
                <h4>Kurs</h4>
                <Segment
                  wartosc={String(roboczy.kurs)}
                  zmien={(v) => setRoboczy((x) => ({ ...x, kurs: Number(v) }))}
                  opcje={[
                    ["1.3", "od 1,30"],
                    ["1.4", "od 1,40"],
                    ["1.6", "od 1,60"],
                    ["2", "od 2,00"],
                  ]}
                />
              </div>
              <div>
                <h4>Ostatnie mecze</h4>
                <Segment
                  wartosc={String(roboczy.okno)}
                  zmien={(v) => setRoboczy((x) => ({ ...x, okno: Number(v) as Okno }))}
                  opcje={[
                    ["10", "10 meczów"],
                    ["5", "5 meczów"],
                  ]}
                />
              </div>
              <p className="nl-panel-uwaga">Liczą się tylko mecze, w których zawodnik grał: z 10 – co najmniej 7, z 5 – co najmniej 4.</p>
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
                  setProg(roboczy);
                  setOtwarty(false);
                }}
              >
                {wRoboczym === 0 ? "Brak linii" : `Pokaż ${wRoboczym} ${odmLinia(wRoboczym)}`}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    );
  }
}
