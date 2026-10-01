"use client";

import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import { fmtKurs, fmtLinia } from "@/lib/format";
import { legKey, zakresOsiagalny, zlozKupon, type Profil } from "@/lib/kuponBuilder";
import type { LegPool } from "@/lib/types";

import type { DruzynaV } from "../../_dane/przygotuj";
import { Krzyzyk, Ptaszek } from "../atomy/wspolne";
import { Blysk } from "../atomy/wyniki-ruch";
import { Segment } from "../atomy2/filtry2";
import { IkonaRynku } from "../elementy/ikonyRynkow";
import { Herb } from "../Herb";
import { LogoPoziome } from "../LogoPoziome";

/*
 * Prototyp strony Kupony (decyzje 01.10): jeden edytowalny kupon, cel na żywo,
 * Zamień / Zablokuj / Usuń, najsłabsze ogniwo, kupon z meczu, kupon w adresie
 * strony, karta do udostępnienia. Bez „Gram ten kupon”, bez linków do
 * bukmachera, bez automatycznego pamiętania. Wygrana brutto.
 *
 * Kupon składa lib/kuponBuilder (ten sam co w aplikacji) – w przeglądarce,
 * 5–9 ms na przebudowę, więc miarka przebudowuje kupon przy każdym ruchu.
 */

const TERAZ = Date.UTC(2026, 8, 30, 20, 40) / 1000;
const MIN_CEL = 1.5;
const MAX_CEL = 25;
const KRESKI = [1.5, 1.75, 2, 2.5, 3, 3.5, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25];
const DUZE = new Set([2, 3, 5, 10, 20]);
const STAWKI = [10, 20, 50, 100];

type Kiedy = "doba" | "2dni" | "wszystkie";
type Rodzaj = "wszystko" | "zawodnicy" | "druzyny";

const GODZ = new Intl.DateTimeFormat("pl-PL", { timeZone: "Europe/Warsaw", hour: "2-digit", minute: "2-digit" });
const DZIEN = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Warsaw" });
const TYDZ = ["Nd", "Pn", "Wt", "Śr", "Czw", "Pt", "Sob"];

function kiedyMecz(ts: number) {
  const d = DZIEN.format(new Date(ts * 1000));
  const dzis = DZIEN.format(new Date(TERAZ * 1000));
  const jutro = DZIEN.format(new Date((TERAZ + 86400) * 1000));
  const dd = new Date(`${d}T12:00:00Z`);
  const dzien = d === dzis ? "Dziś" : d === jutro ? "Jutro" : `${TYDZ[dd.getUTCDay()]} ${dd.getUTCDate()}.${String(dd.getUTCMonth() + 1).padStart(2, "0")}`;
  return { godzina: GODZ.format(new Date(ts * 1000)), dzien };
}

const zl = (v: number) => `${v.toFixed(2).replace(".", ",")} zł`;
const p = (l: LegPool) => l.p_pokaz ?? l.p_model;
const zaklad = (l: LegPool) => ({
  rynek: l.rynek.replace(/\s*drużyny\s*/, " ").trim(),
  strona: l.strona === "ponizej" ? "poniżej" : "powyżej",
  linia: fmtLinia(l.linia),
});

const xZ = (c: number) => (Math.log(c) - Math.log(MIN_CEL)) / (Math.log(MAX_CEL) - Math.log(MIN_CEL));
const zX = (x: number) => Math.exp(Math.log(MIN_CEL) + x * (Math.log(MAX_CEL) - Math.log(MIN_CEL)));
/** położenie w % zaokrąglone po naszemu – serwer i przeglądarka inaczej
 *  wypisują długie ułamki w stylach, co psuło hydratację */
const proc = (x: number) => `${(x * 100).toFixed(3)}%`;
const zaokraglij = (c: number) => (c < 3 ? Math.round(c * 10) / 10 : c < 10 ? Math.round(c * 2) / 2 : Math.round(c));

export type StartKreatora = Record<string, string | undefined>;

type Stan = {
  stawka: number;
  cel: number;
  styl: Profil;
  kiedy: Kiedy;
  rodzaj: Rodzaj;
  jedenZMeczu: boolean;
  mecz: number | null;
  zablokowane: string[];
  wykluczone: string[];
  /** ręcznie ułożone nogi (po „Zamień” / „Dodaj”) – null = kupon składa model */
  reczne: string[] | null;
  /** nogi, które mają zostać po „Usuń” (niewidoczne przypięcie) – zmiana celu,
   *  stylu albo filtrów je czyści, bo wtedy użytkownik prosi o nowy kupon */
  utrwalone: string[];
};

function zAdresu(s: StartKreatora): Stan {
  const lista = (v?: string) => (v ? v.split(",").filter(Boolean) : []);
  return {
    stawka: Number(s.st) || 10,
    cel: Math.min(Math.max(Number(s.cel) || 5, MIN_CEL), MAX_CEL),
    styl: (["bezpieczny", "zbalansowany", "agresywny"] as const).find((x) => x === s.styl) ?? "zbalansowany",
    kiedy: (["doba", "2dni", "wszystkie"] as const).find((x) => x === s.kiedy) ?? "wszystkie",
    rodzaj: (["wszystko", "zawodnicy", "druzyny"] as const).find((x) => x === s.rodzaj) ?? "wszystko",
    jedenZMeczu: s.m1 !== "0",
    mecz: s.mecz ? Number(s.mecz) : null,
    zablokowane: lista(s.z),
    wykluczone: lista(s.w),
    reczne: s.r ? lista(s.r) : null,
    utrwalone: lista(s.u),
  };
}

function doAdresu(s: Stan) {
  const q = new URLSearchParams({
    cel: String(s.cel),
    styl: s.styl,
    kiedy: s.kiedy,
    rodzaj: s.rodzaj,
    st: String(s.stawka),
  });
  if (!s.jedenZMeczu) q.set("m1", "0");
  if (s.mecz) q.set("mecz", String(s.mecz));
  if (s.zablokowane.length) q.set("z", s.zablokowane.join(","));
  if (s.wykluczone.length) q.set("w", s.wykluczone.join(","));
  if (s.reczne) q.set("r", s.reczne.join(","));
  if (s.utrwalone.length) q.set("u", s.utrwalone.join(","));
  return q;
}

/* ---- ikony akcji ------------------------------------------------------ */

function IZamien() {
  return (
    <svg width="13" height="13" viewBox="0 0 14 14" aria-hidden>
      <path d="M2.5 5h8l-2.5-2.5M11.5 9h-8l2.5 2.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function IKlodka({ zamknieta }: { zamknieta: boolean }) {
  return (
    <svg width="13" height="13" viewBox="0 0 14 14" aria-hidden>
      <rect x="3" y="6.5" width="8" height="6" rx="1.3" fill={zamknieta ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.5" />
      <path d={zamknieta ? "M4.8 6.5V4.8a2.2 2.2 0 0 1 4.4 0v1.7" : "M4.8 6.5V4.8a2.2 2.2 0 0 1 4.3-.6"} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

/* ---- miarka celu ------------------------------------------------------ */

function Miarka({
  cel,
  zmien,
  zasieg,
}: {
  cel: number;
  zmien: (c: number) => void;
  zasieg: { min: number; max: number } | null;
}) {
  const rama = useRef<HTMLDivElement>(null);
  const [ciagnie, setCiagnie] = useState(false);
  const ustaw = (x: number) => {
    const r = rama.current?.getBoundingClientRect();
    if (!r) return;
    const c = zaokraglij(zX(Math.min(Math.max((x - r.left) / r.width, 0), 1)));
    zmien(Math.min(Math.max(c, MIN_CEL), MAX_CEL));
  };
  const klawisze = (e: KeyboardEvent) => {
    const krok = cel < 3 ? 0.1 : cel < 10 ? 0.5 : 1;
    if (e.key === "ArrowRight" || e.key === "ArrowUp") {
      e.preventDefault();
      zmien(Math.min(MAX_CEL, zaokraglij(cel + krok)));
    }
    if (e.key === "ArrowLeft" || e.key === "ArrowDown") {
      e.preventDefault();
      zmien(Math.max(MIN_CEL, zaokraglij(cel - krok)));
    }
  };
  const lewo = zasieg ? Math.max(0, xZ(Math.max(zasieg.min, MIN_CEL))) : 0;
  const prawo = zasieg ? Math.min(1, xZ(Math.min(zasieg.max, MAX_CEL))) : 1;

  return (
    <div
      ref={rama}
      className="k-miarka"
      role="slider"
      tabIndex={0}
      aria-label="Kurs, który chcesz osiągnąć"
      aria-valuemin={MIN_CEL}
      aria-valuemax={MAX_CEL}
      aria-valuenow={cel}
      aria-valuetext={`×${fmtKurs(cel)}`}
      onKeyDown={klawisze}
      onPointerDown={(e: PointerEvent) => {
        (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
        setCiagnie(true);
        ustaw(e.clientX);
      }}
      onPointerMove={(e) => ciagnie && ustaw(e.clientX)}
      onPointerUp={() => setCiagnie(false)}
      onPointerCancel={() => setCiagnie(false)}
    >
      {/* cele poza zasięgiem przy tych ustawieniach – przygaszone */}
      {zasieg && (
        <>
          <div style={{ position: "absolute", inset: `0 ${proc(1 - lewo)} 0 0`, background: "var(--pow1)", opacity: 0.7 }} aria-hidden />
          <div style={{ position: "absolute", inset: `0 0 0 ${proc(prawo)}`, background: "var(--pow1)", opacity: 0.7 }} aria-hidden />
        </>
      )}
      <div className="k-miarka-kreski" aria-hidden>
        {KRESKI.map((k) => (
          <span key={k}>
            <i className="k-kreska" data-duza={DUZE.has(k) ? "true" : undefined} style={{ left: proc(xZ(k)) }} />
            {DUZE.has(k) && (
              <em className="k-kreska-etykieta" style={{ left: proc(xZ(k)), fontStyle: "normal" }}>
                ×{k}
              </em>
            )}
          </span>
        ))}
      </div>
      <motion.div
        className="k-miarka-znacznik"
        animate={{ left: proc(xZ(cel)) }}
        transition={ciagnie ? { duration: 0 } : { type: "spring", stiffness: 420, damping: 36 }}
      >
        <b>×{fmtKurs(cel)}</b>
      </motion.div>
    </div>
  );
}

/* ---- kreator ---------------------------------------------------------- */

export function Kreator({
  pula,
  herby,
  telefon,
  start,
}: {
  pula: LegPool[];
  herby: Record<string, DruzynaV>;
  telefon: boolean;
  start: StartKreatora;
}) {
  const [s, setS] = useState<Stan>(() => zAdresu(start));
  const [zamiana, setZamiana] = useState<string | null>(null);
  const [dodaj, setDodaj] = useState(false);
  const [karta, setKarta] = useState(false);
  const [skopiowano, setSkopiowano] = useState(false);
  const kreatorRef = useRef<HTMLDivElement>(null);

  // kupon w adresie strony – link = ten sam kupon (bez zapamiętywania)
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    for (const k of ["cel", "styl", "kiedy", "rodzaj", "st", "m1", "mecz", "z", "w", "r", "u"]) q.delete(k);
    for (const [k, v] of doAdresu(s)) q.set(k, v);
    window.history.replaceState(null, "", `?${q}`);
  }, [s]);

  const poKluczu = useMemo(() => new Map(pula.map((l) => [legKey(l), l])), [pula]);

  const pulaFiltr = useMemo(
    () =>
      pula.filter((l) => {
        if (l.kickoff_ts <= TERAZ) return false; // rozpoczęte wypadają same
        if (s.kiedy === "doba" && l.kickoff_ts - TERAZ > 86400) return false;
        if (s.kiedy === "2dni" && l.kickoff_ts - TERAZ > 2 * 86400) return false;
        if (s.rodzaj === "druzyny" && l.podmiot_typ !== "druzyna") return false;
        if (s.rodzaj === "zawodnicy" && l.podmiot_typ === "druzyna") return false;
        if (s.mecz && l.mecz_id !== s.mecz) return false;
        return true;
      }),
    [pula, s.kiedy, s.rodzaj, s.mecz],
  );

  const maxNaMecz = s.mecz ? 4 : s.jedenZMeczu ? 1 : 4;
  const zasieg = useMemo(() => zakresOsiagalny(pulaFiltr, 2, s.mecz ? 3 : 8, maxNaMecz, s.styl), [pulaFiltr, maxNaMecz, s.styl, s.mecz]);

  const wynik = useMemo(() => {
    if (s.reczne) {
      const legi = s.reczne.map((k) => poKluczu.get(k)).filter((l): l is LegPool => !!l);
      return { legi, kurs: legi.reduce((a, l) => a * l.kurs, 1), alternatywa: undefined, reczny: true };
    }
    const zloz = (klucze: string[]) =>
      zlozKupon(pulaFiltr, s.cel * 0.88, s.cel * 1.12, {
        profil: s.styl,
        minLegi: 2,
        maxLegi: s.mecz ? 3 : undefined,
        maxNaMecz,
        przypiete: [...new Set(klucze)].map((k) => poKluczu.get(k)).filter((l): l is LegPool => !!l),
        wykluczone: new Set(s.wykluczone),
        teraz: TERAZ,
      });
    // najpierw z nogami, które miały zostać; gdy się nie da domknąć celu – bez nich
    const k = (s.utrwalone.length ? zloz([...s.zablokowane, ...s.utrwalone]) : null) ?? zloz(s.zablokowane);
    if (!k) return null;
    return { legi: k.legi, kurs: k.kurs_laczny, alternatywa: k.alternatywa, reczny: false };
  }, [s, pulaFiltr, poKluczu, maxNaMecz]);

  const legi = useMemo(() => (wynik ? wynik.legi.slice().sort((a, b) => a.kickoff_ts - b.kickoff_ts) : []), [wynik]);
  const kurs = wynik?.kurs ?? 0;
  const szansa = legi.reduce((a, l) => a * p(l), 1);
  const najslabsza = legi.length ? legi.reduce((m, l) => (p(l) < p(m) ? l : m), legi[0]) : null;
  const koniec = legi.length ? kiedyMecz(Math.max(...legi.map((l) => l.kickoff_ts))) : null;

  // błysk kursu łącznego: poprzednia wartość zapamiętana wzorcem „stan z
  // poprzedniego renderu” (bez efektu – React to zaleca przy zmianie wejścia)
  const [sledzony, setSledzony] = useState<{ teraz: number; przed: number | null }>({ teraz: kurs, przed: null });
  if (sledzony.teraz !== kurs) setSledzony({ teraz: kurs, przed: sledzony.teraz });
  const poprzedniKurs = sledzony.przed;

  const zmien = useCallback((z: Partial<Stan>, zostawReczne = false) => {
    setS((x) => ({
      ...x,
      ...z,
      reczne: zostawReczne ? (z.reczne ?? x.reczne) : (z.reczne ?? null),
      utrwalone: z.utrwalone ?? (zostawReczne ? x.utrwalone : []),
    }));
    setZamiana(null);
  }, []);

  const klucze = legi.map(legKey);

  const kandydaciZamiany = (l: LegPool) => {
    const inneMecze = new Set(legi.filter((x) => x !== l).map((x) => x.mecz_id));
    return pulaFiltr
      .filter(
        (c) =>
          !klucze.includes(legKey(c)) &&
          !s.wykluczone.includes(legKey(c)) &&
          c.podmiot_id !== l.podmiot_id &&
          (!s.jedenZMeczu || s.mecz || !inneMecze.has(c.mecz_id)) &&
          c.kurs >= l.kurs * 0.8 &&
          c.kurs <= l.kurs * 1.3,
      )
      .sort((a, b) => p(b) - p(a))
      .slice(0, 3);
  };

  const zamien = (stara: LegPool, nowa: LegPool) =>
    zmien(
      {
        wykluczone: [...s.wykluczone, legKey(stara)],
        reczne: klucze.map((k) => (k === legKey(stara) ? legKey(nowa) : k)),
      },
      true,
    );

  // „Usuń”: pozostałe nogi zostają, kupon dobiera tylko brakującą; wypada cały
  // zawodnik/drużyna – inny typ na tę samą drużynę wyglądałby jak „nie usunęło się”
  const usun = (l: LegPool) =>
    zmien({
      wykluczone: [...s.wykluczone, ...pula.filter((c) => c.podmiot_id === l.podmiot_id).map(legKey)],
      zablokowane: s.zablokowane.filter((k) => k !== legKey(l)),
      utrwalone: klucze.filter((k) => k !== legKey(l)),
    });

  const zablokuj = (l: LegPool) => {
    const k = legKey(l);
    zmien({ zablokowane: s.zablokowane.includes(k) ? s.zablokowane.filter((x) => x !== k) : [...s.zablokowane, k] }, true);
  };

  const alt = wynik?.alternatywa;
  const altStara = alt ? wynik!.legi[alt.zamiast_idx] : null;

  /* kupon dnia: zbalansowany ×3,5–5,5, najbliższa doba (albo wszystkie) */
  const kuponDnia = useMemo(() => {
    const dostepne = pula.filter((l) => l.kickoff_ts > TERAZ);
    const doba = dostepne.filter((l) => l.kickoff_ts - TERAZ <= 86400);
    const opcje = { profil: "zbalansowany" as const, minLegi: 2, maxNaMecz: 1, teraz: TERAZ };
    return zlozKupon(doba, 3.2, 5.5, opcje) ?? zlozKupon(dostepne, 3.5, 5.5, opcje);
  }, [pula]);

  /* kupon z meczu: mecze z największą liczbą typów */
  const mecze = useMemo(() => {
    const m = new Map<number, { nazwa: string; ile: number }>();
    for (const l of pula) if (l.kickoff_ts > TERAZ) m.set(l.mecz_id, { nazwa: l.mecz, ile: (m.get(l.mecz_id)?.ile ?? 0) + 1 });
    return [...m.entries()].filter(([, v]) => v.ile >= 2).sort((a, b) => b[1].ile - a[1].ile).slice(0, 4);
  }, [pula]);

  const kopiujLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setSkopiowano(true);
      setTimeout(() => setSkopiowano(false), 1800);
    } catch {
      /* brak dostępu do schowka – link i tak jest w pasku adresu */
    }
  };

  const herb = (l: LegPool) => herby[l.podmiot_typ === "druzyna" ? l.podmiot : l.druzyna];

  return (
    <div className="k-strona">
      <header className="k-naglowek">
        <h1 className="p-n">Kupony</h1>
        <p>
          Złóż kupon pod wygraną, jaką chcesz. <small>Kursy z 22:28.</small>
        </p>
      </header>

      {/* ---- kupon dnia ---- */}
      {kuponDnia && (
        <section className="k-dnia" aria-label="Kupon dnia">
          <div className="k-dnia-glowa">
            <div>
              <small>Kupon dnia</small>
              <div className="k-dnia-kurs">
                ×{fmtKurs(kuponDnia.kurs_laczny)}
                <span>szansa {Math.round(kuponDnia.legi.reduce((a, l) => a * p(l), 1) * 100)}%</span>
              </div>
            </div>
            <button
              type="button"
              className="a-guzik"
              data-t="glowny"
              data-r="m"
              onClick={() => {
                const dzienny = kuponDnia.legi.every((l) => l.kickoff_ts - TERAZ <= 86400);
                zmien({ cel: zaokraglij(kuponDnia.kurs_laczny), styl: "zbalansowany", kiedy: dzienny ? "doba" : "wszystkie", jedenZMeczu: true, mecz: null, zablokowane: [], wykluczone: [] });
                kreatorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
            >
              Dopasuj
            </button>
          </div>
          <div className="k-dnia-nogi">
            {kuponDnia.legi
              .slice()
              .sort((a, b) => a.kickoff_ts - b.kickoff_ts)
              .map((l) => {
                const z = zaklad(l);
                const k = kiedyMecz(l.kickoff_ts);
                return (
                  <div key={legKey(l)} className="k-dnia-noga">
                    <time>{k.godzina}</time>
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
        </section>
      )}

      {/* ---- kreator ---- */}
      <section className="k-kreator" ref={kreatorRef} aria-label="Złóż kupon">
        <div className="k-cel-glowa">
          <h2 className="p-n">Ile chcesz wygrać?</h2>
          <span>Stawiasz</span>
          <span className="k-stawki" role="radiogroup" aria-label="Stawka">
            {STAWKI.map((v) => (
              <button key={v} type="button" className="el-kwota" aria-pressed={s.stawka === v} onClick={() => zmien({ stawka: v }, true)}>
                {v} zł
              </button>
            ))}
          </span>
          <span style={{ width: "100%" }}>
            Wygrywasz <b>{zl(s.stawka * (kurs || s.cel))}</b>
          </span>
        </div>

        <Miarka cel={s.cel} zmien={(c) => zmien({ cel: c })} zasieg={zasieg} />

        <div className="k-ustawienia">
          <Segment
            wartosc={s.styl}
            zmien={(v) => zmien({ styl: v as Profil })}
            opcje={[
              ["bezpieczny", "Bezpieczniejszy"],
              ["zbalansowany", "Zbalansowany"],
              ["agresywny", "Odważny"],
            ]}
          />
          <Segment
            wartosc={s.kiedy}
            zmien={(v) => zmien({ kiedy: v as Kiedy })}
            opcje={[
              ["doba", "Najbliższa doba"],
              ["2dni", "2 dni"],
              ["wszystkie", "Wszystkie dni"],
            ]}
          />
          <Segment
            wartosc={s.rodzaj}
            zmien={(v) => zmien({ rodzaj: v as Rodzaj })}
            opcje={[
              ["wszystko", "Wszystko"],
              ["zawodnicy", "Zawodnicy"],
              ["druzyny", "Drużyny"],
            ]}
          />
          {!s.mecz && (
            <button type="button" className="e-przelacznik" aria-pressed={s.jedenZMeczu} onClick={() => zmien({ jedenZMeczu: !s.jedenZMeczu })}>
              Maks. 1 typ z meczu
            </button>
          )}
        </div>

        {s.mecz && (
          <div className="e-aktywne" style={{ marginTop: -6 }}>
            <span className="e-aktywny">
              Kupon z meczu: {mecze.find(([id]) => id === s.mecz)?.[1].nazwa ?? "wybrany mecz"}
              <button type="button" className="d-chip-usun" aria-label="Wyłącz kupon z meczu" onClick={() => zmien({ mecz: null })}>
                <Krzyzyk rozmiar={8} />
              </button>
            </span>
            <span>U bukmachera to Bet Builder – kurs łączny może być inny niż suma pojedynczych.</span>
          </div>
        )}

        {/* ---- kupon ---- */}
        {!wynik || legi.length === 0 ? (
          <div className="d-pusty">
            <div className="p-n" style={{ fontSize: 17 }}>
              Nie da się złożyć kuponu ×{fmtKurs(s.cel)}
            </div>
            <p>
              {zasieg
                ? `Z tymi ustawieniami da się złożyć kupon od ×${fmtKurs(Math.max(zasieg.min, 1.01))} do ×${fmtKurs(zasieg.max)}.`
                : "Przy tych ustawieniach jest za mało typów."}
            </p>
            {zasieg && (
              <button
                type="button"
                className="a-guzik"
                data-t="drugi"
                data-r="m"
                onClick={() => zmien({ cel: zaokraglij(Math.min(Math.max(s.cel, zasieg.min * 1.05), zasieg.max * 0.9)) })}
              >
                Ustaw najbliższy możliwy
              </button>
            )}
          </div>
        ) : (
          <>
            <div className="k-kupon-glowa">
              <div>
                <div className="k-kurs-laczny">
                  <Blysk tekst={`×${fmtKurs(kurs)}`} kier={poprzedniKurs === null || poprzedniKurs === kurs ? null : kurs > poprzedniKurs ? "gora" : "dol"} />
                </div>
                <div className="k-kupon-meta">
                  {legi.length} {legi.length < 5 ? "typy" : "typów"} · rozstrzygnie się: <b>{koniec?.dzien}, {koniec?.godzina}</b>
                  {" · "}pewne składy{" "}
                  <b title="Składy ogłaszane są ok. godzinę przed meczem – wtedy przeliczamy typy">
                    {legi.filter((l) => l.swieze_sklady).length}/{legi.length}
                  </b>
                  {wynik.reczny && " · ułożony ręcznie"}
                </div>
              </div>
              <div className="k-szansa-kuponu">
                <b>{Math.round(szansa * 100)}%</b>
                <small>szansa, że wejdzie cały</small>
              </div>
            </div>

            {/* najsłabsze ogniwo z gotową zamianą (z budowniczego) */}
            {alt && altStara && !wynik.reczny && (
              <motion.div className="k-ogniwo" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}>
                <div>
                  <b>
                    Zamień {altStara.podmiot} na {alt.podmiot}
                  </b>
                  <small>
                    {zaklad(alt).rynek.toLowerCase()} {zaklad(alt).strona} {zaklad(alt).linia} · kurs łączny ×{fmtKurs(alt.kurs_po)} · szansa{" "}
                    {Math.round(szansa * 100)}% → {Math.round((szansa / p(altStara)) * p(alt) * 100)}%
                  </small>
                </div>
                <button type="button" className="a-guzik" data-t="drugi" data-r="s" onClick={() => zamien(altStara, alt)}>
                  Zamień
                </button>
              </motion.div>
            )}

            <LayoutGroup>
              <div className="k-os">
                <AnimatePresence initial={false} mode="popLayout">
                  {legi.map((l) => {
                    const k = legKey(l);
                    const z = zaklad(l);
                    const kiedy = kiedyMecz(l.kickoff_ts);
                    const zabl = s.zablokowane.includes(k);
                    const slaba = najslabsza === l && legi.length > 2;
                    return (
                      <motion.div
                        key={k}
                        layout
                        className="k-noga"
                        data-zablokowana={zabl || undefined}
                        data-najslabsza={slaba || undefined}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: 10 }}
                        transition={{ layout: { type: "spring", stiffness: 420, damping: 38 }, duration: 0.2 }}
                      >
                        <div className="k-noga-czas">
                          {kiedy.godzina}
                          <small>{kiedy.dzien}</small>
                        </div>
                        <span className="k-noga-kropka" />
                        <div className="k-noga-karta">
                          <div className="k-noga-gora">
                            <div style={{ minWidth: 0 }}>
                              <div className="k-noga-kto">
                                {herb(l) && <Herb d={herb(l)!} tryb="prawdziwy" rozmiar={16} />}
                                <span>{l.podmiot}</span>
                              </div>
                              <div className="k-noga-zaklad">
                                <IkonaRynku rynek={l.rynek} rozmiar={14} />
                                <b>{z.rynek}</b>
                                <span>{z.strona}</span>
                                <b>{z.linia}</b>
                              </div>
                              <div className="k-noga-mecz">{l.mecz}</div>
                              {slaba && <div className="k-najslabsza-etykieta" style={{ marginTop: 4 }}>najsłabsze ogniwo – najniższa szansa w kuponie</div>}
                            </div>
                            <div className="k-noga-kurs">
                              <b>{fmtKurs(l.kurs)}</b>
                              <small>{Math.round(p(l) * 100)}%</small>
                            </div>
                          </div>
                          <div className="k-noga-akcje">
                            <button type="button" className="k-akcja" aria-expanded={zamiana === k} onClick={() => setZamiana((x) => (x === k ? null : k))}>
                              <IZamien /> Zamień
                            </button>
                            <button type="button" className="k-akcja" aria-pressed={zabl} onClick={() => zablokuj(l)} title="Zablokowany typ zostaje przy każdej zmianie celu">
                              <IKlodka zamknieta={zabl} /> {zabl ? "Zablokowany" : "Zablokuj"}
                            </button>
                            <button type="button" className="k-akcja" data-usun onClick={() => usun(l)} title="Usuń – kupon sam dobierze inny typ">
                              <Krzyzyk rozmiar={9} /> Usuń
                            </button>
                          </div>
                          <AnimatePresence initial={false}>
                            {zamiana === k && (
                              <motion.div
                                className="k-zamiany"
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: "auto", opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                style={{ overflow: "hidden" }}
                              >
                                <small>Podobny kurs, zamiast {l.podmiot}:</small>
                                {kandydaciZamiany(l).length === 0 && <span className="k-uwaga">Brak typów o podobnym kursie przy tych ustawieniach.</span>}
                                {kandydaciZamiany(l).map((c) => {
                                  const zc = zaklad(c);
                                  const roznica = Math.round((p(c) - p(l)) * 100);
                                  return (
                                    <button key={legKey(c)} type="button" className="k-zamiana" onClick={() => zamien(l, c)}>
                                      <span>
                                        {c.podmiot}{" "}
                                        <small>
                                          {zc.rynek.toLowerCase()} {zc.strona} {zc.linia}
                                        </small>
                                      </span>
                                      <span className="k-roznica" data-plus={roznica >= 0 ? "true" : "false"}>
                                        {roznica >= 0 ? "+" : ""}
                                        {roznica} pp
                                      </span>
                                      <b>{fmtKurs(c.kurs)}</b>
                                    </button>
                                  );
                                })}
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </div>
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
              </div>
            </LayoutGroup>

            <div className="k-dodaj">
              <button type="button" className="a-guzik" data-t="cichy" data-r="s" style={{ justifySelf: "start" }} aria-expanded={dodaj} onClick={() => setDodaj((d) => !d)}>
                + Dodaj typ
              </button>
              <AnimatePresence initial={false}>
                {dodaj && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} style={{ overflow: "hidden" }}>
                    {pulaFiltr
                      .filter((c) => !klucze.includes(legKey(c)) && !legi.some((x) => x.podmiot_id === c.podmiot_id))
                      .sort((a, b) => p(b) - p(a))
                      .slice(0, 5)
                      .map((c) => {
                        const zc = zaklad(c);
                        return (
                          <button
                            key={legKey(c)}
                            type="button"
                            className="k-zamiana"
                            onClick={() => {
                              zmien({ reczne: [...klucze, legKey(c)] }, true);
                              setDodaj(false);
                            }}
                          >
                            <span>
                              {c.podmiot}{" "}
                              <small>
                                {zc.rynek.toLowerCase()} {zc.strona} {zc.linia}
                              </small>
                            </span>
                            <span className="k-roznica">{Math.round(p(c) * 100)}%</span>
                            <b>{fmtKurs(c.kurs)}</b>
                          </button>
                        );
                      })}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* podsumowanie: pasek (komputer) / pastylka (telefon) */}
            <div className="k-pasek">
              <span className="k-pasek-kurs">×{fmtKurs(kurs)}</span>
              <span className="k-pasek-wygrana">
                {s.stawka} zł → {zl(s.stawka * kurs)}
              </span>
              <span className="k-pasek-akcje">
                <button type="button" className="k-pasek-guzik" onClick={kopiujLink}>
                  {skopiowano ? (
                    <>
                      <Ptaszek rozmiar={10} /> Skopiowano
                    </>
                  ) : (
                    "Kopiuj link"
                  )}
                </button>
                <button type="button" className="k-pasek-guzik" onClick={() => setKarta(true)}>
                  Udostępnij
                </button>
              </span>
            </div>
          </>
        )}
      </section>

      {/* ---- kupon z meczu ---- */}
      <section className="k-z-meczu" aria-label="Kupon z meczu">
        <h2 className="p-n" style={{ fontSize: 19 }}>
          Kupon z jednego meczu
        </h2>
        <p className="k-uwaga">Na stronie meczu to jeden przycisk. Tu do przetestowania:</p>
        <div className="k-z-meczu-lista">
          {mecze.map(([id, m]) => (
            <button
              key={id}
              type="button"
              className="a-chip"
              aria-pressed={s.mecz === id}
              onClick={() => {
                zmien({ mecz: id, cel: 3, zablokowane: [], wykluczone: [] });
                kreatorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
            >
              {m.nazwa} <small>{m.ile}</small>
            </button>
          ))}
        </div>
      </section>

      {/* ---- karta do udostępnienia ---- */}
      <AnimatePresence>
        {karta && legi.length > 0 && (
          <motion.div className="k-modal-tlo" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setKarta(false)}>
            <motion.div
              className="k-modal"
              role="dialog"
              aria-label="Karta do udostępnienia"
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
                    {legi.length} typy · szansa {Math.round(szansa * 100)}% · rozstrzygnie się {koniec?.dzien}, {koniec?.godzina}
                  </small>
                </div>
                <div className="k-karta-nogi">
                  {legi.map((l) => {
                    const z = zaklad(l);
                    return (
                      <div key={legKey(l)} className="k-karta-noga">
                        <time>{kiedyMecz(l.kickoff_ts).godzina}</time>
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
                  <span>
                    Złożone na <b>footstats</b>
                    <br />
                    Szansa to nasze wyliczenia, nie gwarancja.
                  </span>
                  <span className="k-18">18+</span>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button type="button" className="a-guzik" data-t="glowny" data-r="m" style={{ flex: 1 }} disabled title="W wersji docelowej obrazek generuje serwer">
                  Pobierz obrazek
                </button>
                <button type="button" className="a-guzik" data-t="drugi" data-r="m" onClick={kopiujLink}>
                  {skopiowano ? "Skopiowano" : "Kopiuj link"}
                </button>
              </div>
              <p className="k-uwaga">Link otwiera ten sam kupon do edycji. Obrazek w formacie 4:5 (Instagram, Discord) zrobi serwer przy składaniu strony.</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
      {telefon && <div style={{ height: 8 }} />}
    </div>
  );
}
