"use client";

import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import { fmtKurs, fmtLinia } from "@/lib/format";
import { SILA_TYPU, silaTypu } from "@/lib/slownik";

import type { DzienV, TypV } from "../../_dane/przygotuj";
import { Ptaszek } from "../atomy/wspolne";
import { PrzewijanyRzad } from "./PrzewijanyRzad";

/* ======================================================================
   LOGO BUKMACHERA – maska w kolorze tekstu (mono) albo oryginał
   ====================================================================== */

const LOGA: Record<string, { maska: string; kolor: string; proporcja: number; skala: number }> = {
  Superbet: { maska: "/bukmacherzy/superbet-maska.png", kolor: "/bukmacherzy/superbet.png", proporcja: 271 / 48, skala: 0.74 },
  // maska Betclica to sam napis (bez czerwonego prostokąta), więc jest niższa
  Betclic: { maska: "/bukmacherzy/betclic-maska.png", kolor: "/bukmacherzy/betclic.png", proporcja: 122 / 30, skala: 0.95 },
};

export function Logo({ nazwa, wysokosc = 14, kolor = false }: { nazwa: string; wysokosc?: number; kolor?: boolean }) {
  const l = LOGA[nazwa];
  if (!l) return <span style={{ fontSize: 11, fontWeight: 600 }}>{nazwa}</span>;
  const h = Math.round(wysokosc * l.skala * 10) / 10;
  if (kolor) {
    // oryginał w kolorze marki – wersja do porównania
    const hk = nazwa === "Betclic" ? wysokosc : h;
    const pk = nazwa === "Betclic" ? 142 / 48 : l.proporcja;
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={l.kolor} alt={nazwa} width={Math.round(hk * pk)} height={hk} style={{ display: "block" }} />;
  }
  return (
    <span
      role="img"
      aria-label={nazwa}
      className="d-logo"
      style={{ width: Math.round(h * l.proporcja), height: h, ["--maska" as string]: `url(${l.maska})` }}
    />
  );
}

/* ======================================================================
   2.1 KAFELEK KURSU – poziomy, dopracowany
   ====================================================================== */

export type Kurs = {
  kurs: number | null;
  bukmacher: string;
  /** kurs, od którego typ ma sens – pokazywany, gdy bukmachera jeszcze nie ma */
  uczciwy?: number | null;
  zmiana?: "gora" | "dol" | null;
};

export function KafelekD({
  k,
  wybrany = false,
  onClick,
  logoKolor = false,
  blysk,
}: {
  k: Kurs;
  wybrany?: boolean;
  onClick?: () => void;
  logoKolor?: boolean;
  /** klucz zmiany kursu – nowy klucz = błysk (2.8) */
  blysk?: string;
}) {
  if (k.kurs === null) {
    return (
      <span
        className="d-kurs"
        data-brak="true"
        title={k.uczciwy ? `Bukmacher jeszcze nie wystawił kursu. Typ ma sens od ${fmtKurs(k.uczciwy)}.` : "Brak kursu"}
      >
        <Logo nazwa={k.bukmacher} kolor={logoKolor} />
        <span className="d-kurs-od">
          {k.uczciwy ? (
            <>
              od <b>{fmtKurs(k.uczciwy)}</b>
            </>
          ) : (
            "brak kursu"
          )}
        </span>
      </span>
    );
  }

  const kolorBlysku = k.zmiana === "gora" ? "var(--ok)" : k.zmiana === "dol" ? "var(--nie)" : "transparent";

  return (
    <button
      type="button"
      className="d-kurs"
      aria-pressed={wybrany}
      aria-label={`${k.bukmacher}, kurs ${fmtKurs(k.kurs)}${wybrany ? ", w kuponie" : ""}`}
      onClick={onClick}
    >
      {blysk && k.zmiana && (
        <motion.span
          key={blysk}
          className="d-kurs-blysk"
          aria-hidden
          initial={{ boxShadow: `inset 0 0 0 1.5px ${kolorBlysku}`, backgroundColor: `color-mix(in srgb, ${kolorBlysku} 22%, transparent)` }}
          animate={{ boxShadow: "inset 0 0 0 1.5px rgba(0,0,0,0)", backgroundColor: "rgba(0,0,0,0)" }}
          transition={{ duration: 1.6, ease: "easeOut" }}
        />
      )}
      <Logo nazwa={k.bukmacher} kolor={logoKolor && !wybrany} />
      <span className="d-kurs-prawa">
        <AnimatePresence initial={false}>
          {wybrany && (
            <motion.span
              className="d-kurs-ptaszek"
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0, opacity: 0 }}
              transition={{ type: "spring", stiffness: 520, damping: 28 }}
            >
              <Ptaszek rozmiar={11} />
            </motion.span>
          )}
        </AnimatePresence>
        {k.zmiana && (
          <span className="d-kurs-strzalka" data-kier={k.zmiana} aria-label={k.zmiana === "gora" ? "wzrósł" : "spadł"}>
            {k.zmiana === "gora" ? "▲" : "▼"}
          </span>
        )}
        <span className="d-kurs-liczba">{fmtKurs(k.kurs)}</span>
      </span>
    </button>
  );
}

/* ======================================================================
   2.2 SZANSA – liczba i słowo, dopracowana
   ====================================================================== */

export function SzansaD({ p, mala = false }: { p: number; mala?: boolean }) {
  const [otwarty, setOtwarty] = useState(false);
  const sila = silaTypu(p);
  const na100 = Math.round(p * 100);
  const id = useId();
  const rama = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!otwarty) return;
    const zamknij = (e: MouseEvent) => {
      if (rama.current && !rama.current.contains(e.target as Node)) setOtwarty(false);
    };
    const esc = (e: globalThis.KeyboardEvent) => e.key === "Escape" && setOtwarty(false);
    document.addEventListener("mousedown", zamknij);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", zamknij);
      document.removeEventListener("keydown", esc);
    };
  }, [otwarty]);

  return (
    <div className="d-szansa" data-mala={mala ? "true" : undefined}>
      <span className="d-szansa-liczba" aria-label={`szansa ${na100} procent`}>
        {na100}
        <small>%</small>
      </span>
      {!mala && (
        <span className="d-szansa-slowo" data-poziom={sila.kod} ref={rama} style={{ position: "relative" }}>
          {sila.label}
          <button
            type="button"
            className="d-info"
            aria-expanded={otwarty}
            aria-controls={id}
            aria-label="Co znaczy ta liczba"
            onClick={() => setOtwarty((o) => !o)}
            onMouseEnter={() => setOtwarty(true)}
            onMouseLeave={() => setOtwarty(false)}
          >
            ?
          </button>
          <AnimatePresence>
            {otwarty && (
              <motion.span
                id={id}
                role="tooltip"
                className="d-dymek"
                style={{ top: "calc(100% + 8px)", left: 0 }}
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.16 }}
              >
                <p>
                  Na 100 takich typów wchodzi około <b>{na100}</b>.
                </p>
                <p>
                  {SILA_TYPU.map((s) => `${s.label.replace(" szansa", "")} ${s.zakres}`).join(" · ")}
                </p>
              </motion.span>
            )}
          </AnimatePresence>
        </span>
      )}
    </div>
  );
}

/* ======================================================================
   2.3 KRATKI – dopracowane (minuty, nie zagrał, najnowszy, dymek)
   ====================================================================== */

const MALO_MINUT = 45;

export function KratkiD({ t }: { t: TypV }) {
  const [dymek, setDymek] = useState<number | null>(null);
  const trafil = (v: number) => (t.strona === "ponizej" ? v < t.linia : v > t.linia);
  // decyzja 30.09: od NAJNOWSZEGO (z lewej) do najstarszego – czyta się jak
  // lista wyników w aplikacji: pierwsze, co widać, to ostatni mecz
  const mecze = t.historia
    .map((v, i) => ({
      v,
      min: t.minuty[i] ?? 90,
      rywal: t.rywale[i] ?? "–",
      data: t.daty[i] ?? "",
      kadra: !!t.kadra[i],
    }))
    .reverse();
  const zagrane = mecze.filter((m) => m.min > 0);
  const ile = zagrane.filter((m) => trafil(m.v)).length;
  const ost5 = zagrane.slice(0, 5);
  const ile5 = ost5.filter((m) => trafil(m.v)).length;
  const strona = t.strona === "ponizej" ? "pod" : "ponad";
  const d = dymek !== null ? mecze[dymek] : null;

  return (
    <div className="d-historia">
      <div className="d-hist-glowa">
        <span className="d-hist-wynik">
          {ile}/{zagrane.length}
          <span>
            {strona} {fmtLinia(t.linia)}
          </span>
        </span>
        <span className="d-hist-l5">
          ostatnie 5: <b>{ile5}/{ost5.length}</b>
          {mecze.length > zagrane.length && <> · {mecze.length - zagrane.length}× nie zagrał</>}
        </span>
      </div>
      <div className="d-kratki" onMouseLeave={() => setDymek(null)}>
        {mecze.map((m, i) => {
          const nieGral = m.min === 0;
          return (
            <motion.button
              type="button"
              key={i}
              className="d-kratka"
              data-trafil={!nieGral && trafil(m.v) ? "true" : undefined}
              data-malo-minut={!nieGral && m.min < MALO_MINUT ? "true" : undefined}
              data-nie-gral={nieGral ? "true" : undefined}
              data-najnowsza={i === 0 ? "true" : undefined}
              aria-label={`${m.rywal} ${m.data}: ${nieGral ? "nie zagrał" : `${m.v}, ${m.min} min`}`}
              onMouseEnter={() => setDymek(i)}
              onFocus={() => setDymek(i)}
              onClick={() => setDymek((x) => (x === i ? null : i))}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.04 + i * 0.03, type: "spring", stiffness: 420, damping: 30 }}
            >
              {nieGral ? <span className="d-ng">NZ</span> : m.v}
            </motion.button>
          );
        })}
        <AnimatePresence>
          {d && dymek !== null && (
            <motion.span
              key={dymek}
              role="tooltip"
              className="d-dymek"
              style={{ top: 38, left: Math.min(dymek * 34, 150), width: 190 }}
              initial={{ opacity: 0, y: -3 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.12 }}
            >
              <p>
                <b>vs {d.rywal}</b> · {d.data}
                {d.kadra ? " · reprezentacja" : ""}
              </p>
              <p>
                {d.min === 0
                  ? "nie zagrał – nie liczymy"
                  : `${d.v} · ${d.min} min${d.min < MALO_MINUT ? " (krótko na boisku)" : ""}`}
              </p>
            </motion.span>
          )}
        </AnimatePresence>
      </div>
      <div className="d-hist-os">
        <span>ostatni mecz</span>
        <span>starsze</span>
      </div>
    </div>
  );
}

export function LegendaKratek() {
  return (
    <div className="d-hist-legenda">
      <span>
        <i style={{ background: "var(--ok-tlo)", boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--ok) 35%, transparent)" }} />
        {"weszło"}
      </span>
      <span>
        <i style={{ background: "var(--pow2)" }} />
        nie weszło
      </span>
      <span>
        <i
          style={{
            background:
              "repeating-linear-gradient(135deg, var(--pow2) 0 3px, color-mix(in srgb, var(--t1) 14%, transparent) 3px 4px)",
          }}
        />
        mniej niż 45 min
      </span>
      <span>
        <i className="d-ng-probka" />
        NZ – nie zagrał (poza wynikiem)
      </span>
    </div>
  );
}

/* ======================================================================
   2.4 CHIPY DNI – dopracowane
   ====================================================================== */

export function DniD({ dni, wybrany: zewn, zmien }: { dni: DzienV[]; wybrany?: string; zmien?: (klucz: string) => void }) {
  const [wlasny, setWlasny] = useState(dni[0]?.klucz);
  // sterowany z zewnątrz (strona Mecze filtruje listę) albo sam trzyma wybór
  const wybrany = zewn ?? wlasny;
  const setWybrany = (k: string) => (zmien ? zmien(k) : setWlasny(k));
  const lista = useRef<HTMLDivElement>(null);
  const id = useId();

  const wybierz = (klucz: string) => {
    setWybrany(klucz);
    // wybrany dzień zawsze w polu widzenia – także gdy wybrano go strzałką
    lista.current
      ?.querySelector<HTMLElement>(`[data-dzien="${klucz}"]`)
      ?.scrollIntoView({ inline: "nearest", block: "nearest", behavior: "smooth" });
  };

  const klawisze = (e: KeyboardEvent) => {
    const i = dni.findIndex((d) => d.klucz === wybrany);
    const nast = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null;
    if (nast === null || nast < 0 || nast >= dni.length) return;
    e.preventDefault();
    wybierz(dni[nast].klucz);
    lista.current?.querySelector<HTMLElement>(`[data-dzien="${dni[nast].klucz}"]`)?.focus();
  };

  return (
    <LayoutGroup id={id}>
      <div className="d-dni-rama" ref={lista} onKeyDown={klawisze}>
        <PrzewijanyRzad className="d-dni" role="tablist" ariaLabel="Dzień">
          {dni.map((d) => {
            const on = d.klucz === wybrany;
            return (
              <button
                key={d.klucz}
                type="button"
                role="tab"
                data-dzien={d.klucz}
                className="d-dzien d-dotyk"
                aria-selected={on}
                tabIndex={on ? 0 : -1}
                disabled={d.ile === 0}
                onClick={() => wybierz(d.klucz)}
              >
                {on && (
                  <motion.span layoutId="tlo-dnia" className="d-dzien-tlo" transition={{ type: "spring", stiffness: 480, damping: 36 }} />
                )}
                {d.etykieta}
                <small>{d.ile}</small>
              </button>
            );
          })}
        </PrzewijanyRzad>
      </div>
    </LayoutGroup>
  );
}
