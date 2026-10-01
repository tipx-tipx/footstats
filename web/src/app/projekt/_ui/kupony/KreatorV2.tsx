"use client";

import { useTeraz } from "../czas";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fmtKurs, fmtLinia } from "@/lib/format";
import { legKey, zlozKupon, type Profil } from "@/lib/kuponBuilder";
import type { LegPool } from "@/lib/types";

import type { DruzynaV } from "../../_dane/przygotuj";
import { Krzyzyk, Ptaszek } from "../atomy/wspolne";
import { Blysk } from "../atomy/wyniki-ruch";
import { IkonaRynku } from "../elementy/ikonyRynkow";
import { Herb } from "../Herb";
import { LogoPoziome } from "../LogoPoziome";
import { PrzewijanyRzad } from "../atomy2/PrzewijanyRzad";

/*
 * Strona Kupony v2 (01.10, po „bardzo duży chaos”):
 *  - JEDEN kupon na ekranie (startuje jako kupon dnia),
 *  - zamiast miarki: 5 kafli celu – każdy mówi, ile wygrasz i jaka szansa,
 *  - ustawienia schowane za jedną linijką podsumowania,
 *  - noga czysta; akcje dopiero po dotknięciu, zamiennik najsłabszej W NIEJ,
 *  - jeden przycisk „Udostępnij”; krótki link w środku.
 */

const CELE = [2, 3, 5, 10, 20];
const STAWKI = [10, 20, 50, 100];
const STYLE: Profil[] = ["bezpieczny", "zbalansowany", "agresywny"];
type Kiedy = "doba" | "2dni" | "wszystkie";
type Rodzaj = "wszystko" | "zawodnicy" | "druzyny";
const KIEDY: Kiedy[] = ["doba", "2dni", "wszystkie"];
const RODZAJ: Rodzaj[] = ["wszystko", "zawodnicy", "druzyny"];

const GODZ = new Intl.DateTimeFormat("pl-PL", { timeZone: "Europe/Warsaw", hour: "2-digit", minute: "2-digit" });
const DZIEN = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Warsaw" });
const TYDZ = ["Nd", "Pn", "Wt", "Śr", "Czw", "Pt", "Sob"];

function kiedyMecz(ts: number, TERAZ: number) {
  const d = DZIEN.format(new Date(ts * 1000));
  const dzis = DZIEN.format(new Date(TERAZ * 1000));
  const jutro = DZIEN.format(new Date((TERAZ + 86400) * 1000));
  const dd = new Date(`${d}T12:00:00Z`);
  const dzien = d === dzis ? "Dziś" : d === jutro ? "Jutro" : `${TYDZ[dd.getUTCDay()]} ${dd.getUTCDate()}.${String(dd.getUTCMonth() + 1).padStart(2, "0")}`;
  return { godzina: GODZ.format(new Date(ts * 1000)), dzien };
}

const zl = (v: number) => `${v.toFixed(2).replace(".", ",")} zł`;
const zlKrotko = (v: number) => (v >= 100 ? `${Math.round(v)} zł` : zl(v));
const p = (l: LegPool) => l.p_pokaz ?? l.p_model;
const szansaKuponu = (legi: LegPool[]) => legi.reduce((a, l) => a * p(l), 1);
const sredniaNaTyp = (legi: LegPool[]) => (legi.length ? legi.reduce((a, l) => a + p(l), 0) / legi.length : 0);

/**
 * 01.10: „szansa 3%” na kaflu sprzedaje fatalnie, choć każdy typ w kuponie
 * jest mocny – niska szansa całości bierze się z MNOŻENIA. Na wierzchu:
 * średnia szansa typu + słowo poziomu ryzyka. Dokładna szansa całości zostaje
 * uczciwie na jedno dotknięcie („?” w nagłówku kuponu).
 */
function ryzyko(szansaCalosci: number): { slowo: string; kolor: "ok" | "neutral" | "czeka" } {
  if (szansaCalosci >= 0.35) return { slowo: "pewniejszy", kolor: "ok" };
  if (szansaCalosci >= 0.15) return { slowo: "zbalansowany", kolor: "neutral" };
  if (szansaCalosci >= 0.06) return { slowo: "ryzykowny", kolor: "czeka" };
  return { slowo: "dla odważnych", kolor: "czeka" };
}

const typow = (n: number) => `${n} ${n === 1 ? "typ" : n < 5 ? "typy" : "typów"}`;
const zaklad = (l: LegPool) => ({
  rynek: l.rynek.replace(/\s*drużyny\s*/, " ").trim(),
  strona: l.strona === "ponizej" ? "poniżej" : "powyżej",
  linia: fmtLinia(l.linia),
});

/* ---- stan + KRÓTKI link --------------------------------------------- */

type Stan = {
  stawka: number;
  cel: number;
  styl: Profil;
  kiedy: Kiedy;
  rodzaj: Rodzaj;
  jedenZMeczu: boolean;
  mecz: number | null;
  zablokowane: number[];
  wykluczone: number[];
  reczne: number[] | null;
  utrwalone: number[];
};

const DOMYSLNY: Stan = {
  stawka: 10,
  cel: 5,
  styl: "zbalansowany",
  kiedy: "wszystkie",
  rodzaj: "wszystko",
  jedenZMeczu: true,
  mecz: null,
  zablokowane: [],
  wykluczone: [],
  reczne: null,
  utrwalone: [],
};

/**
 * Cały kupon w JEDNYM krótkim parametrze `k`, np. `k=2szww1a___12.f.g_-_0.5.3`
 * („_” i „.” nie są kodowane w adresie, „~” było – link rósł o %7E)
 * (cel×10, styl, dni, rodzaj, 1 z meczu, stawka, listy id w base36).
 * Docelowo serwer da jeszcze krótszy adres (footstats.pl/k/x7Qa) – tu
 * wystarcza, że link mieści się w wiadomości bez zawijania.
 */
const lista = (a: number[]) => a.map((x) => x.toString(36)).join(".");
const zListy = (s: string) => (s ? s.split(".").map((x) => parseInt(x, 36)).filter((x) => !Number.isNaN(x)) : []);

function doLinku(s: Stan): string {
  const naglowek = [
    Math.round(s.cel * 10).toString(36),
    "bza"[STYLE.indexOf(s.styl)],
    "d2w"[KIEDY.indexOf(s.kiedy)],
    "wzd"[RODZAJ.indexOf(s.rodzaj)],
    s.jedenZMeczu ? "1" : "0",
    s.stawka.toString(36),
  ].join("");
  const czesci = [naglowek, s.mecz ? s.mecz.toString(36) : "", lista(s.zablokowane), lista(s.wykluczone), s.reczne ? lista(s.reczne) : "-", lista(s.utrwalone)];
  while (czesci.length > 1 && (czesci[czesci.length - 1] === "" || czesci[czesci.length - 1] === "-")) czesci.pop();
  return czesci.join("_");
}

function zLinku(k: string | undefined): Stan {
  if (!k) return DOMYSLNY;
  try {
    const [n, mecz = "", z = "", w = "", r = "-", u = ""] = k.split("_");
    const m = n.match(/^([0-9a-z]+?)([bza])([d2w])([wzd])([01])([0-9a-z]+)$/);
    if (!m) return DOMYSLNY;
    return {
      cel: parseInt(m[1], 36) / 10,
      styl: STYLE["bza".indexOf(m[2])],
      kiedy: KIEDY["d2w".indexOf(m[3])],
      rodzaj: RODZAJ["wzd".indexOf(m[4])],
      jedenZMeczu: m[5] === "1",
      stawka: parseInt(m[6], 36),
      mecz: mecz ? parseInt(mecz, 36) : null,
      zablokowane: zListy(z),
      wykluczone: zListy(w),
      reczne: r === "-" ? null : zListy(r),
      utrwalone: zListy(u),
    };
  } catch {
    return DOMYSLNY;
  }
}

/* ---- ikony ------------------------------------------------------------ */

function IKlodka({ zamknieta, r = 13 }: { zamknieta: boolean; r?: number }) {
  return (
    <svg width={r} height={r} viewBox="0 0 14 14" aria-hidden>
      <rect x="3" y="6.5" width="8" height="6" rx="1.3" fill={zamknieta ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.5" />
      <path d={zamknieta ? "M4.8 6.5V4.8a2.2 2.2 0 0 1 4.4 0v1.7" : "M4.8 6.5V4.8a2.2 2.2 0 0 1 4.3-.6"} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function IUdostepnij() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
      <path d="M7 1.8v7.4M4.3 4.4 7 1.8l2.7 2.6M2.5 8v3.7h9V8" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IStrzalka({ otwarta }: { otwarta: boolean }) {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden style={{ transition: "transform .2s ease", transform: otwarta ? "rotate(180deg)" : "none" }}>
      <path d="m3 4.5 3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ---- „?” – dokładna szansa całego kuponu, na jedno dotknięcie ------------ */

function SzansaCalosci({ szansa }: { szansa: number }) {
  const [otwarte, setOtwarte] = useState(false);
  const na100 = Math.max(1, Math.round(szansa * 100));
  return (
    <span className="k2-pyt" onMouseLeave={() => setOtwarte(false)}>
      <button
        type="button"
        className="d-info"
        aria-expanded={otwarte}
        aria-label="Szansa całego kuponu"
        onClick={() => setOtwarte((o) => !o)}
        onMouseEnter={() => setOtwarte(true)}
      >
        ?
      </button>
      <AnimatePresence>
        {otwarte && (
          <motion.span
            role="tooltip"
            className="d-dymek k2-pyt-dymek"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.14 }}
          >
            <p>
              Szansa, że wejdzie <b>cały kupon: {na100}%</b>.
            </p>
            <p>Każdy typ osobno ma dużo wyższą szansę – kupon wygrywa, gdy wejdą wszystkie naraz.</p>
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}

/* ---- ustawienia: widoczne przyciski z wartością ------------------------ */

/** krotko = etykieta na przycisku w rzędzie (rząd ma się mieścić w jednej linii) */
type Opcja = { v: string; nazwa: string; krotko?: string; opis: string; herby?: [DruzynaV | undefined, DruzynaV | undefined] };
type Pozycja = { klucz: string; wartosc: string; domyslna: string; zmien: (v: string) => void; opcje: Opcja[] };

/**
 * 01.10: rozwijane „Zmień” było nieintuicyjne. Każde ustawienie jest teraz
 * osobnym przyciskiem z AKTUALNĄ wartością („Wszystkie dni ▾”); dotknięcie
 * otwiera krótką listę pod rzędem, każda opcja z jednym zdaniem opisu.
 */
function Ustawienia({ pozycje, otwarte, ustaw }: { pozycje: Pozycja[]; otwarte: string | null; ustaw: (k: string | null) => void }) {
  const rama = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!otwarte) return;
    const klik = (e: MouseEvent) => {
      if (rama.current && !rama.current.contains(e.target as Node)) ustaw(null);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && ustaw(null);
    document.addEventListener("mousedown", klik);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", klik);
      document.removeEventListener("keydown", esc);
    };
  }, [otwarte, ustaw]);
  const aktywna = pozycje.find((x) => x.klucz === otwarte);
  return (
    <div className="k2-ust" ref={rama}>
      <PrzewijanyRzad className="k2-ust-rzad">
        {pozycje.map((x) => {
          const o = x.opcje.find((y) => y.v === x.wartosc) ?? x.opcje[0];
          const domyslna = x.wartosc === x.domyslna;
          return (
            <button
              key={x.klucz}
              type="button"
              className="k2-ust-guzik"
              data-zmieniony={!domyslna || undefined}
              aria-expanded={otwarte === x.klucz}
              onClick={() => ustaw(otwarte === x.klucz ? null : x.klucz)}
            >
              {o.krotko ?? o.nazwa}
              <IStrzalka otwarta={otwarte === x.klucz} />
            </button>
          );
        })}
      </PrzewijanyRzad>
      <AnimatePresence initial={false}>
        {aktywna && (
          <motion.div
            key={aktywna.klucz}
            className="k2-ust-lista"
            role="radiogroup"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.14 }}
          >
            {aktywna.opcje.map((o) => (
              <button
                key={o.v}
                type="button"
                role="radio"
                aria-checked={o.v === aktywna.wartosc}
                className="k2-ust-opcja"
                onClick={() => {
                  aktywna.zmien(o.v);
                  ustaw(null);
                }}
              >
                {o.herby && (
                  <span className="k2-ust-herby" aria-hidden>
                    {o.herby.map((h, i) => (h ? <Herb key={i} d={h} tryb="prawdziwy" rozmiar={18} /> : <i key={i} />))}
                  </span>
                )}
                <span className="k2-ust-tekst">
                  <b>{o.nazwa}</b>
                  <small>{o.opis}</small>
                </span>
                {o.v === aktywna.wartosc && <Ptaszek rozmiar={12} />}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ---- kreator ---------------------------------------------------------- */

export type StartKreatoraV2 = Record<string, string | undefined>;

export function KreatorV2({
  pula,
  herby,
  telefon,
  start,
}: {
  pula: LegPool[];
  herby: Record<string, DruzynaV>;
  telefon: boolean;
  start: StartKreatoraV2;
}) {
  const TERAZ = useTeraz();
  const [s, setS] = useState<Stan>(() => zLinku(start.k));
  const [otwarta, setOtwarta] = useState<number | null>(null);
  const [ustawienia, setUstawienia] = useState<string | null>(null);
  const [dodaj, setDodaj] = useState(false);
  const [karta, setKarta] = useState(false);
  const [skopiowano, setSkopiowano] = useState(false);
  const kuponRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    q.set("k", doLinku(s));
    window.history.replaceState(null, "", `?${q}`);
  }, [s]);

  const poId = useMemo(() => new Map(pula.map((l) => [l.id, l])), [pula]);

  const pulaFiltr = useMemo(
    () =>
      pula.filter((l) => {
        if (l.kickoff_ts <= TERAZ) return false;
        if (s.kiedy === "doba" && l.kickoff_ts - TERAZ > 86400) return false;
        if (s.kiedy === "2dni" && l.kickoff_ts - TERAZ > 2 * 86400) return false;
        if (s.rodzaj === "druzyny" && l.podmiot_typ !== "druzyna") return false;
        if (s.rodzaj === "zawodnicy" && l.podmiot_typ === "druzyna") return false;
        if (s.mecz && l.mecz_id !== s.mecz) return false;
        return true;
      }),
    [pula, s.kiedy, s.rodzaj, s.mecz, TERAZ],
  );

  const maxNaMecz = s.mecz ? 4 : s.jedenZMeczu ? 1 : 4;
  const zbuduj = useCallback(
    (cel: number, pin: number[]) =>
      zlozKupon(pulaFiltr, cel * 0.88, cel * 1.12, {
        profil: s.styl,
        minLegi: 2,
        maxLegi: s.mecz ? 3 : undefined,
        maxNaMecz,
        przypiete: [...new Set(pin)].map((id) => poId.get(id)).filter((l): l is LegPool => !!l),
        wykluczone: new Set(s.wykluczone.map((id) => poId.get(id)).filter((l): l is LegPool => !!l).map(legKey)),
        teraz: TERAZ,
      }),
    [pulaFiltr, s.styl, s.mecz, s.wykluczone, maxNaMecz, poId, TERAZ],
  );

  /**
   * Budowniczy zwraca też „pewniejszy zamiennik” najsłabszej nogi. Pokazywanie
   * go pod kuponem nie miało sensu (01.10: „czemu by od razu nie dać
   * pewniejszego typu?”) – więc wstawiamy go od razu, jeśli kurs łączny dalej
   * mieści się w celu, zamiennik ma wyższą szansę, a noga nie jest trzymana.
   */
  const zbudujNajlepszy = useCallback(
    (cel: number, pin: number[]) => {
      const k = zbuduj(cel, pin);
      if (!k) return null;
      const a = k.alternatywa;
      const stara = a ? k.legi[a.zamiast_idx] : null;
      if (a && stara && !pin.includes(stara.id) && a.kurs_po >= cel * 0.88 && a.kurs_po <= cel * 1.12 && p(a) > p(stara)) {
        const legi = k.legi.map((l, i) => (i === a.zamiast_idx ? (a as LegPool) : l));
        return { legi, kurs: a.kurs_po };
      }
      return { legi: k.legi, kurs: k.kurs_laczny };
    },
    [zbuduj],
  );

  // kafle: podgląd każdego celu (5 przebudów × kilka ms)
  const kafle = useMemo(
    () =>
      CELE.map((c) => {
        const k = zbudujNajlepszy(c, s.zablokowane);
        return {
          cel: c,
          kurs: k?.kurs ?? null,
          szansa: k ? szansaKuponu(k.legi) : null,
          ile: k?.legi.length ?? 0,
          srednia: k ? sredniaNaTyp(k.legi) : 0,
        };
      }),
    [zbudujNajlepszy, s.zablokowane],
  );
  // „polecany” = najlepszy stosunek szansy do wygranej (szansa × kurs)
  const polecany = kafle.reduce<number | null>((best, k) => {
    if (k.kurs === null || k.szansa === null) return best;
    const b = kafle.find((x) => x.cel === best);
    return !b || k.kurs * k.szansa > (b.kurs ?? 0) * (b.szansa ?? 0) ? k.cel : best;
  }, null);

  const wynik = useMemo(() => {
    if (s.reczne) {
      const legi = s.reczne.map((id) => poId.get(id)).filter((l): l is LegPool => !!l);
      return { legi, kurs: legi.reduce((a, l) => a * l.kurs, 1), reczny: true };
    }
    const k =
      (s.utrwalone.length ? zbudujNajlepszy(s.cel, [...s.zablokowane, ...s.utrwalone]) : null) ?? zbudujNajlepszy(s.cel, s.zablokowane);
    return k ? { ...k, reczny: false } : null;
  }, [s, poId, zbudujNajlepszy]);

  const legi = useMemo(() => (wynik ? wynik.legi.slice().sort((a, b) => a.kickoff_ts - b.kickoff_ts) : []), [wynik]);
  const kurs = wynik?.kurs ?? 0;
  const szansa = szansaKuponu(legi);
  const ids = legi.map((l) => l.id);
  const czyDomyslny = !s.reczne && s.cel === DOMYSLNY.cel && s.styl === DOMYSLNY.styl && s.kiedy === DOMYSLNY.kiedy && s.rodzaj === DOMYSLNY.rodzaj && !s.mecz && !s.zablokowane.length && !s.wykluczone.length;

  const [sledzony, setSledzony] = useState<{ teraz: number; przed: number | null }>({ teraz: kurs, przed: null });
  if (sledzony.teraz !== kurs) setSledzony({ teraz: kurs, przed: sledzony.teraz });

  const zmien = useCallback((z: Partial<Stan>, zostawUklad = false) => {
    setS((x) => ({
      ...x,
      ...z,
      reczne: zostawUklad ? (z.reczne ?? x.reczne) : (z.reczne ?? null),
      utrwalone: z.utrwalone ?? (zostawUklad ? x.utrwalone : []),
    }));
    setOtwarta(null);
  }, []);

  const kandydaci = (l: LegPool) => {
    const inneMecze = new Set(legi.filter((x) => x !== l).map((x) => x.mecz_id));
    return pulaFiltr
      .filter(
        (c) =>
          !ids.includes(c.id) &&
          !s.wykluczone.includes(c.id) &&
          !legi.some((x) => x.podmiot_id === c.podmiot_id) &&
          (!s.jedenZMeczu || !!s.mecz || !inneMecze.has(c.mecz_id)) &&
          c.kurs >= l.kurs * 0.8 &&
          c.kurs <= l.kurs * 1.3,
      )
      .sort((a, b) => p(b) - p(a))
      .slice(0, 3);
  };

  const zamien = (stara: LegPool, nowa: LegPool) =>
    zmien({ wykluczone: [...s.wykluczone, stara.id], reczne: ids.map((id) => (id === stara.id ? nowa.id : id)) }, true);
  const usun = (l: LegPool) =>
    zmien({
      wykluczone: [...s.wykluczone, ...pula.filter((c) => c.podmiot_id === l.podmiot_id).map((c) => c.id)],
      zablokowane: s.zablokowane.filter((id) => id !== l.id),
      utrwalone: ids.filter((id) => id !== l.id),
    });
  const zablokuj = (l: LegPool) =>
    zmien({ zablokowane: s.zablokowane.includes(l.id) ? s.zablokowane.filter((x) => x !== l.id) : [...s.zablokowane, l.id] }, true);

  const mecze = useMemo(() => {
    const m = new Map<number, { nazwa: string; ile: number; ts: number }>();
    for (const l of pula) if (l.kickoff_ts > TERAZ) m.set(l.mecz_id, { nazwa: l.mecz, ts: l.kickoff_ts, ile: (m.get(l.mecz_id)?.ile ?? 0) + 1 });
    // mecze, z których da się złożyć kupon (co najmniej 2 typy), po godzinie
    return [...m.entries()].filter(([, v]) => v.ile >= 2).sort((a, b) => a[1].ts - b[1].ts);
  }, [pula, TERAZ]);

  const kopiuj = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setSkopiowano(true);
      setTimeout(() => setSkopiowano(false), 1800);
    } catch {
      /* link i tak jest w pasku adresu */
    }
  };

  const herb = (l: LegPool) => herby[l.podmiot_typ === "druzyna" ? l.podmiot : l.druzyna];

  return (
    <div className="k2">
      <header className="k2-glowa">
        <h1 className="p-n">Kupony</h1>
        <p>Wybierz, ile chcesz wygrać. Resztę dobierzemy z dzisiejszych typów.</p>
      </header>

      {/* ---- 1. cel: kafle ---- */}
      <section className="k2-cel" aria-label="Ile chcesz wygrać">
        <div className="k2-stawka">
          <h2 className="p-n">Ile chcesz wygrać?</h2>
          <span className="k2-stawka-etykieta">stawka</span>
          <div className="k2-stawki" role="radiogroup" aria-label="Stawka">
            {STAWKI.map((v) => (
              <button key={v} type="button" role="radio" aria-checked={s.stawka === v} onClick={() => zmien({ stawka: v }, true)}>
                {v} zł
              </button>
            ))}
          </div>
        </div>
        <div className="k2-kafle" role="radiogroup" aria-label="Ile chcesz wygrać">
          {/* kafle, których nie da się złożyć, znikają (np. mecz ma za mało typów na ×10) */}
          {kafle.filter((k) => k.kurs !== null).map((k) => {
            const on = !s.reczne && Math.abs(s.cel - k.cel) < 0.01;
            return (
              <button
                key={k.cel}
                type="button"
                role="radio"
                aria-checked={on}
                disabled={k.kurs === null}
                className="k2-kafel"
                onClick={() => zmien({ cel: k.cel })}
              >
                {on && <motion.span layoutId="k2-kafel-tlo" className="k2-kafel-tlo" transition={{ type: "spring", stiffness: 480, damping: 36 }} />}
                {polecany === k.cel && kafle.filter((x) => x.kurs !== null).length >= 3 && <span className="k2-polecany">polecany</span>}
                <b>{k.kurs !== null ? zlKrotko(s.stawka * k.kurs) : "–"}</b>
                <small>
                  ×{fmtKurs(k.kurs ?? 0)} · {typow(k.ile)}
                </small>
                {k.szansa !== null && (
                  <span className="k2-ryzyko" data-kolor={ryzyko(k.szansa).kolor}>
                    {ryzyko(k.szansa).slowo}
                  </span>
                )}
              </button>
            );
          })}
        </div>
        <Ustawienia
          otwarte={ustawienia}
          ustaw={setUstawienia}
          pozycje={[
            {
              klucz: "mecz",
              wartosc: s.mecz ? String(s.mecz) : "",
              domyslna: "",
              // wybór meczu = od razu 2–3 najmocniejsze typy z niego (każdy na innego
              // zawodnika/drużynę) – niezależnie od celu, bo nie każdy mecz go osiąga
              zmien: (v) => {
                if (!v) return zmien({ mecz: null });
                const id = Number(v);
                const top: LegPool[] = [];
                for (const l of pula.filter((x) => x.mecz_id === id && x.kickoff_ts > TERAZ).sort((a, b) => p(b) - p(a))) {
                  if (top.length < 3 && !top.some((t) => t.podmiot_id === l.podmiot_id)) top.push(l);
                }
                zmien({ mecz: id, zablokowane: [], wykluczone: [], reczne: top.map((l) => l.id) }, true);
              },
              opcje: [
                { v: "", nazwa: "Wszystkie mecze", krotko: "Każdy mecz", opis: "Kupon z typów z różnych meczów" },
                ...mecze.map(([id, m]) => {
                  const [g, h] = m.nazwa.split(" – ");
                  const k = kiedyMecz(m.ts, TERAZ);
                  return {
                    v: String(id),
                    nazwa: m.nazwa,
                    krotko: `${g.split(" ")[0]} – ${(h ?? "").split(" ")[0]}`,
                    opis: `${k.dzien}, ${k.godzina} · ${m.ile} ${m.ile < 5 ? "typy" : "typów"} · kupon tylko z tego meczu`,
                    herby: [herby[g], herby[h]] as [DruzynaV | undefined, DruzynaV | undefined],
                  };
                }),
              ],
            },
            {
              klucz: "kiedy",
              wartosc: s.kiedy,
              domyslna: "wszystkie",
              zmien: (v) => zmien({ kiedy: v as Kiedy }),
              opcje: [
                { v: "doba", nazwa: "Najbliższa doba", krotko: "Doba", opis: "Tylko mecze w ciągu 24 godzin" },
                { v: "2dni", nazwa: "2 dni", opis: "Mecze dziś i jutro" },
                { v: "wszystkie", nazwa: "Wszystkie dni", krotko: "Każdy dzień", opis: "Też mecze za kilka dni" },
              ],
            },
            {
              klucz: "rodzaj",
              wartosc: s.rodzaj,
              domyslna: "wszystko",
              zmien: (v) => zmien({ rodzaj: v as Rodzaj }),
              opcje: [
                { v: "wszystko", nazwa: "Zawodnicy i drużyny", krotko: "Wszystkie typy", opis: "Wszystkie nasze typy" },
                { v: "zawodnicy", nazwa: "Tylko zawodnicy", krotko: "Zawodnicy", opis: "Strzały, faule, kartki zawodników" },
                { v: "druzyny", nazwa: "Tylko drużyny", krotko: "Drużyny", opis: "Gole, rożne, kartki całych drużyn" },
              ],
            },
            ...(s.mecz ? [] : [{
              klucz: "mecz1",
              wartosc: s.jedenZMeczu ? "1" : "n",
              domyslna: "1",
              zmien: (v: string) => zmien({ jedenZMeczu: v === "1" }),
              opcje: [
                { v: "1", nazwa: "Max 1 typ z meczu", krotko: "1 typ z meczu", opis: "Każdy typ z innego meczu – bezpieczniej" },
                { v: "n", nazwa: "Kilka typów z meczu", krotko: "Kilka z meczu", opis: "Więcej wyboru, ale typy z jednego meczu zależą od siebie" },
              ],
            }]),
            {
              klucz: "styl",
              wartosc: s.styl,
              domyslna: "zbalansowany",
              zmien: (v) => zmien({ styl: v as Profil }),
              opcje: [
                { v: "bezpieczny", nazwa: "Ostrożny dobór", krotko: "Ostrożnie", opis: "Typy z największą szansą" },
                { v: "zbalansowany", nazwa: "Normalny dobór", krotko: "Normalnie", opis: "Szansa i kurs po równo" },
                { v: "agresywny", nazwa: "Odważny dobór", krotko: "Odważnie", opis: "Dopuszcza typy z wyższym kursem" },
              ],
            },
          ]}
        />
      </section>

      {/* ---- 2. kupon ---- */}
      <section className="k2-kupon" ref={kuponRef} aria-label="Kupon">
        {s.mecz && (
          <div className="k2-mecz">
            <span>
              Tylko z meczu <b>{mecze.find(([id]) => id === s.mecz)?.[1].nazwa}</b>. U bukmachera zagrasz to jako Bet Builder.
            </span>
            <button type="button" className="k2-mecz-x" onClick={() => zmien({ mecz: null })}>
              <Krzyzyk rozmiar={8} /> Wszystkie mecze
            </button>
          </div>
        )}

        {!wynik || legi.length === 0 ? (
          <div className="d-pusty">
            <div className="p-n" style={{ fontSize: 17 }}>
              Z tymi ustawieniami nie złożymy kuponu
            </div>
            <p>Wybierz inną wygraną albo poluzuj ustawienia.</p>
          </div>
        ) : (
          <>
            <div className="k2-kupon-glowa">
              <div>
                <small className="k2-etykieta">{czyDomyslny ? "Kupon dnia" : "Twój kupon"}</small>
                <div className="k2-wygrana">
                  <Blysk
                    tekst={zl(s.stawka * kurs)}
                    kier={sledzony.przed === null || sledzony.przed === kurs ? null : kurs > sledzony.przed ? "gora" : "dol"}
                  />
                </div>
                <div className="k2-meta">
                  kurs <b>×{fmtKurs(kurs)}</b> · {typow(legi.length)} · średnio <b>{Math.round(sredniaNaTyp(legi) * 100)}%</b> na typ
                  <span className="k2-ryzyko" data-kolor={ryzyko(szansa).kolor}>
                    {ryzyko(szansa).slowo}
                  </span>
                  <SzansaCalosci szansa={szansa} />
                </div>
              </div>
              {!telefon && (
                <button type="button" className="a-guzik" data-t="drugi" data-r="m" onClick={() => setKarta(true)}>
                  <IUdostepnij /> Udostępnij
                </button>
              )}
            </div>

            <LayoutGroup>
              <ol className="k2-os">
                <AnimatePresence initial={false} mode="popLayout">
                  {legi.map((l) => {
                    const z = zaklad(l);
                    const kd = kiedyMecz(l.kickoff_ts, TERAZ);
                    const zabl = s.zablokowane.includes(l.id);
                    const otw = otwarta === l.id;
                    return (
                      <motion.li
                        key={l.id}
                        layout
                        className="k2-noga"
                        data-otwarta={otw || undefined}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: 8 }}
                        transition={{ layout: { type: "spring", stiffness: 420, damping: 38 }, duration: 0.18 }}
                      >
                        <span className="k2-czas">
                          {kd.godzina}
                          <small>{kd.dzien}</small>
                        </span>
                        <span className="k2-kropka" data-zablokowana={zabl || undefined} aria-hidden />
                        <div className="k2-karta">
                          <button type="button" className="k2-karta-gora" aria-expanded={otw} onClick={() => setOtwarta(otw ? null : l.id)}>
                            <span className="k2-kto">
                              {herb(l) && <Herb d={herb(l)!} tryb="prawdziwy" rozmiar={16} />}
                              <span>{l.podmiot}</span>
                              {zabl && (
                                <span className="k2-klodka" title="Zablokowany – zostaje przy zmianie wygranej">
                                  <IKlodka zamknieta />
                                </span>
                              )}
                            </span>
                            <span className="k2-kurs">{fmtKurs(l.kurs)}</span>
                            <span className="k2-zaklad">
                              <IkonaRynku rynek={l.rynek} rozmiar={14} />
                              <b>{z.rynek}</b> {z.strona} <b>{z.linia}</b>
                            </span>
                            <span className="k2-szansa">{Math.round(p(l) * 100)}%</span>
                          </button>

                          <AnimatePresence initial={false}>
                            {otw && (
                              <motion.div
                                className="k2-rozwin"
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: "auto", opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                transition={{ duration: 0.2 }}
                              >
                                <div className="k2-rozwin-wnetrze">
                                  <small>Zamień na typ o podobnym kursie – dotknij, żeby wstawić</small>
                                  {kandydaci(l).length === 0 && <span className="k-uwaga">Nie ma typów o podobnym kursie.</span>}
                                  {kandydaci(l).map((c) => {
                                    const zc = zaklad(c);
                                    const r = Math.round((p(c) - p(l)) * 100);
                                    return (
                                      <button key={c.id} type="button" className="k2-kandydat" onClick={() => zamien(l, c)}>
                                        <span>
                                          {c.podmiot}
                                          <small>
                                            {zc.rynek.toLowerCase()} {zc.strona} {zc.linia}
                                          </small>
                                        </span>
                                        {/* wpływ na CAŁY kupon – wyższa szansa zwykle = niższa wygrana */}
                                        <em data-plus={r >= 0 ? "true" : "false"}>
                                          {r >= 0 ? "+" : ""}
                                          {r} pp szansy
                                          <small>kupon ×{fmtKurs((kurs / l.kurs) * c.kurs)}</small>
                                        </em>
                                        <b>{fmtKurs(c.kurs)}</b>
                                      </button>
                                    );
                                  })}
                                  <div className="k2-akcje">
                                    <button type="button" onClick={() => zablokuj(l)}>
                                      <IKlodka zamknieta={zabl} /> {zabl ? "Odblokuj" : "Zostaw na stałe"}
                                    </button>
                                    <button type="button" data-usun onClick={() => usun(l)}>
                                      <Krzyzyk rozmiar={9} /> Usuń z kuponu
                                    </button>
                                  </div>
                                </div>
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </div>
                      </motion.li>
                    );
                  })}
                </AnimatePresence>
              </ol>
            </LayoutGroup>

            <div className="k2-dodaj">
              <span className="k2-dodaj-kropka" aria-hidden>
                +
              </span>
              <button type="button" aria-expanded={dodaj} onClick={() => setDodaj((d) => !d)}>
                Dodaj typ
              </button>
              <AnimatePresence initial={false}>
                {dodaj && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} style={{ overflow: "hidden" }}>
                    <div className="k2-rozwin-wnetrze" style={{ paddingTop: 6 }}>
                      {pulaFiltr
                        .filter((c) => !ids.includes(c.id) && !legi.some((x) => x.podmiot_id === c.podmiot_id))
                        .sort((a, b) => p(b) - p(a))
                        .slice(0, 5)
                        .map((c) => {
                          const zc = zaklad(c);
                          return (
                            <button
                              key={c.id}
                              type="button"
                              className="k2-kandydat"
                              onClick={() => {
                                zmien({ reczne: [...ids, c.id] }, true);
                                setDodaj(false);
                              }}
                            >
                              <span>
                                {c.podmiot}
                                <small>
                                  {zc.rynek.toLowerCase()} {zc.strona} {zc.linia}
                                </small>
                              </span>
                              <em>{Math.round(p(c) * 100)}%</em>
                              <b>{fmtKurs(c.kurs)}</b>
                            </button>
                          );
                        })}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </>
        )}
      </section>

      {/* telefon: przyklejona pastylka z wygraną i jednym przyciskiem */}
      {telefon && legi.length > 0 && (
        <div className="k2-pastylka">
          <span>
            <b>{zl(s.stawka * kurs)}</b>
            <small>
              ×{fmtKurs(kurs)} · {typow(legi.length)} · {ryzyko(szansa).slowo}
            </small>
          </span>
          <button type="button" onClick={() => setKarta(true)}>
            <IUdostepnij /> Udostępnij
          </button>
        </div>
      )}

      {/* ---- udostępnianie ---- */}
      <AnimatePresence>
        {karta && legi.length > 0 && (
          <motion.div className="k-modal-tlo" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setKarta(false)}>
            <motion.div
              className="k-modal"
              role="dialog"
              aria-label="Udostępnij kupon"
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 20, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="k-karta">
                <LogoPoziome jasne wysokosc={24} />
                <div className="k-karta-kurs">
                  ×{fmtKurs(kurs)}
                  <small>
                    {legi.length} {legi.length < 5 ? "typy" : "typów"} na jednym kuponie
                  </small>
                </div>
                <div className="k-karta-nogi">
                  {legi.map((l) => {
                    const z = zaklad(l);
                    return (
                      <div key={l.id} className="k-karta-noga">
                        <time>{kiedyMecz(l.kickoff_ts, TERAZ).godzina}</time>
                        <span>
                          {l.podmiot}{" "}
                          <small>
                            {z.rynek.toLowerCase()} {z.strona} {z.linia}
                          </small>
                        </span>
                        <b>{fmtKurs(l.kurs)}</b>
                      </div>
                    );
                  })}
                </div>
                <div className="k-karta-stopka">
                  <span className="k-karta-promo">
                    <b>Typy ze statystyk, nie z przeczucia.</b>
                    Swój kupon złożysz w 10 sekund na footstats.pl
                  </span>
                  <span className="k-18">18+</span>
                </div>
              </div>
              <div className="k2-udostepnij-akcje">
                <button type="button" className="a-guzik" data-t="glowny" data-r="m" disabled title="Obrazek zrobi serwer przy składaniu strony">
                  Zapisz obrazek
                </button>
                <button type="button" className="a-guzik" data-t="drugi" data-r="m" onClick={kopiuj}>
                  {skopiowano ? (
                    <>
                      <Ptaszek rozmiar={10} /> Skopiowano
                    </>
                  ) : (
                    "Kopiuj link"
                  )}
                </button>
              </div>
              <p className="k-uwaga">Link otwiera ten sam kupon do zmiany. Przycisk „Zapisz obrazek” zadziała po złożeniu strony.</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
