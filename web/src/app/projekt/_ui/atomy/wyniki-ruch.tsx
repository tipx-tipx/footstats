"use client";

import { animate, AnimatePresence, motion, useMotionValue, useTransform } from "framer-motion";
import { useEffect, useState } from "react";

import { fmtKurs, fmtLinia } from "@/lib/format";

import type { TypV } from "../../_dane/przygotuj";
import { Krzyzyk, Ptaszek, Zegar, Zwrot } from "./wspolne";

/* ======================================================================
   2.7 STANY ROZLICZENIA
   ====================================================================== */

type Wynik = "ok" | "nie" | "zwrot" | "czeka";

const KOLOR: Record<Wynik, string> = {
  ok: "var(--ok)",
  nie: "var(--nie)",
  zwrot: "var(--zwrot)",
  czeka: "var(--czeka)",
};

const TEKST: Record<Wynik, string> = { ok: "weszło", nie: "nie weszło", zwrot: "zwrot", czeka: "czeka" };

function Ikona({ w, r = 11 }: { w: Wynik; r?: number }) {
  if (w === "ok") return <Ptaszek rozmiar={r} />;
  if (w === "nie") return <Krzyzyk rozmiar={r} />;
  if (w === "zwrot") return <Zwrot rozmiar={r} />;
  return <Zegar rozmiar={r} />;
}

type WierszWyniku = { t: TypV; wynik: Wynik; liczba: number | null; notka: string };

export function ScenaRozliczenia({ wariant, typy }: { wariant: string; typy: TypV[] }) {
  // przykładowe rozstrzygnięcia na prawdziwych typach – tylko do oceny wyglądu
  const wiersze: WierszWyniku[] = [
    { t: typy[0], wynik: "ok", liczba: 3, notka: "" },
    { t: typy[1], wynik: "nie", liczba: 0, notka: "" },
    { t: typy[2], wynik: "zwrot", liczba: null, notka: "nie zagrał" },
    { t: typy[0], wynik: "czeka", liczba: null, notka: typy[0].godzina },
  ];

  return (
    <div className="a-scena">
      <div className="a-podpis">przykładowe wyniki na prawdziwych typach</div>
      {wiersze.map(({ t, wynik, liczba, notka }, i) => {
        const opis = (
          <div className="a-przygas" style={{ minWidth: 0 }}>
            <div className="a-typ-kto">{t.kto}</div>
            <div className="a-typ-co">
              {t.rynek.toLowerCase()} {t.strona === "ponizej" ? "poniżej" : "powyżej"} {fmtLinia(t.linia)}
            </div>
          </div>
        );
        const kurs = (
          <span className="a-kurs-liczba a-przygas" style={{ fontSize: 15 }}>
            {fmtKurs(t.kurs)}
          </span>
        );

        if (wariant === "c") {
          return (
            <div key={i} className="a-wiersz-wyniku" style={{ ["--kolor-wyniku" as string]: KOLOR[wynik] }}>
              {opis}
              {kurs}
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className="a-wynik-liczba">
                  {liczba !== null ? (
                    <>
                      <b>{liczba}</b> / {fmtLinia(t.linia)}
                    </>
                  ) : (
                    notka
                  )}
                </span>
                <span className="a-wynik-kolko" aria-label={TEKST[wynik]}>
                  <Ikona w={wynik} />
                </span>
              </div>
            </div>
          );
        }

        const etykieta = (
          <span className={`p-wynik p-wynik-${wynik}`}>
            <Ikona w={wynik} r={12} />
            {TEKST[wynik]}
          </span>
        );

        return (
          <div
            key={i}
            className="a-wiersz-wyniku"
            data-styl={wariant === "b" ? "b" : undefined}
            data-wynik={wynik}
            style={{ ["--kolor-wyniku" as string]: KOLOR[wynik] }}
          >
            {opis}
            {kurs}
            {etykieta}
          </div>
        );
      })}
    </div>
  );
}

/* ======================================================================
   2.8 ZMIANA LICZBY
   ====================================================================== */

const CYFRY = Array.from({ length: 10 }, (_, i) => i);

/** licznik jak w liczniku kilometrów: każda cyfra przewija się w swojej kolumnie */
function Odometr({ tekst }: { tekst: string }) {
  const znaki = tekst.split("");
  return (
    <span className="a-licznik-cyfr" aria-label={tekst}>
      {znaki.map((z, i) => {
        const klucz = znaki.length - i; // licz od prawej, żeby 9,95 → 10,05 nie tasowało kolumn
        if (!/\d/.test(z)) return <span key={`s${klucz}`}>{z}</span>;
        return (
          <span key={`d${klucz}`} className="a-kolumna-cyfr">
            <motion.span animate={{ y: `${-Number(z)}em` }} transition={{ type: "spring", stiffness: 180, damping: 22 }}>
              {CYFRY.map((c) => (
                <span key={c}>{c}</span>
              ))}
            </motion.span>
          </span>
        );
      })}
    </span>
  );
}

export function Blysk({ tekst, kier }: { tekst: string; kier: "gora" | "dol" | null }) {
  const tlo = kier === "gora" ? "var(--ok-tlo)" : kier === "dol" ? "var(--nie-tlo)" : "transparent";
  return (
    <span className="a-blysk" style={{ position: "relative", isolation: "isolate" }}>
      {/* warstwa błysku montuje się od nowa przy każdej zmianie i gaśnie */}
      <motion.span
        key={`tlo-${tekst}`}
        aria-hidden
        style={{ position: "absolute", inset: 0, borderRadius: 7, background: tlo, zIndex: -1 }}
        initial={{ opacity: 1 }}
        animate={{ opacity: 0 }}
        transition={{ duration: 1.4, ease: "easeOut" }}
      />
      <span style={{ position: "relative", display: "inline-block", overflow: "hidden", lineHeight: 1 }}>
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span
            key={tekst}
            style={{ display: "inline-block" }}
            initial={{ y: kier === "dol" ? "-100%" : "100%", opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: kier === "dol" ? "100%" : "-100%", opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
          >
            {tekst}
          </motion.span>
        </AnimatePresence>
      </span>
      {kier && (
        <span className="a-kurs-zmiana" data-kier={kier} style={{ fontSize: "0.45em" }}>
          {kier === "gora" ? "▲" : "▼"}
        </span>
      )}
    </span>
  );
}

function Odliczanie({ wartosc, format }: { wartosc: number; format: (v: number) => string }) {
  const mv = useMotionValue(wartosc);
  const tekst = useTransform(mv, format);
  useEffect(() => {
    const a = animate(mv, wartosc, { duration: 0.7, ease: [0.22, 1, 0.36, 1] });
    return () => a.stop();
  }, [mv, wartosc]);
  return <motion.span>{tekst}</motion.span>;
}

const KURSY = [1.27, 1.34, 1.22, 1.45, 1.31];
const SZANSE = [0.73, 0.76, 0.69, 0.81, 0.72];

export function ScenaZmiany({ wariant }: { wariant: string }) {
  const [[i, poprz], setKrok] = useState<[number, number]>([0, 0]);
  const kurs = KURSY[i % KURSY.length];
  const szansa = SZANSE[i % SZANSE.length];
  const kursPoprz = KURSY[poprz % KURSY.length];
  const szansaPoprz = SZANSE[poprz % SZANSE.length];
  const kier = (a: number, b: number) => (a === b ? null : a > b ? "gora" : "dol");
  const fmtP = (p: number) => `${Math.round(p * 100)}%`;

  const liczba = (wartosc: number, poprzednia: number, fmt: (v: number) => string) => {
    if (wariant === "b") return <Blysk tekst={fmt(wartosc)} kier={kier(wartosc, poprzednia)} />;
    if (wariant === "c") return <Odliczanie wartosc={wartosc} format={fmt} />;
    return <Odometr tekst={fmt(wartosc)} />;
  };

  return (
    <div className="a-scena">
      <div className="a-rzad" style={{ gap: 40 }}>
        <div>
          <div className="a-podpis">kurs</div>
          <div className="a-kurs-liczba" style={{ fontSize: 34 }}>
            {liczba(kurs, kursPoprz, fmtKurs)}
          </div>
        </div>
        <div>
          <div className="a-podpis">szansa</div>
          <div className="a-kurs-liczba" style={{ fontSize: 34 }}>
            {liczba(szansa, szansaPoprz, fmtP)}
          </div>
        </div>
      </div>
      <button
        type="button"
        className="a-demo-guzik"
        onClick={() => setKrok(([x]) => [x + 1, x])}
      >
        Symuluj przeliczenie
      </button>
    </div>
  );
}

/* ======================================================================
   2.9 ŁADOWANIE
   ====================================================================== */

function Szkielet({ anim }: { anim: string }) {
  return (
    <div className="a-szkielet" aria-hidden>
      <div className="a-kosc" data-anim={anim} style={{ width: "38%" }} />
      <div className="a-kosc" data-anim={anim} style={{ width: "62%", height: 20 }} />
      <div className="a-kosc" data-anim={anim} style={{ width: "48%" }} />
      <div className="a-kosc" data-anim={anim} style={{ width: "100%", height: 44, marginTop: 6 }} />
    </div>
  );
}

export function ScenaLadowania({ wariant, typ }: { wariant: string; typ: TypV }) {
  const [laduje, setLaduje] = useState(true);

  const tresc = (
    <div>
      <div className="p-t3" style={{ fontSize: 12 }}>
        {typ.druzyna.nazwa} – {typ.rywal.nazwa}
      </div>
      <div className="p-n" style={{ fontSize: 20, marginTop: 6 }}>
        {typ.kto}
      </div>
      <div className="a-typ-co">
        {typ.rynek.toLowerCase()} {typ.strona === "ponizej" ? "poniżej" : "powyżej"} {fmtLinia(typ.linia)} · {fmtKurs(typ.kurs)}
      </div>
    </div>
  );

  let widok;
  if (wariant === "c") {
    widok = (
      <div style={{ position: "relative" }}>
        {laduje && <div className="a-postep" role="progressbar" aria-label="odświeżanie" />}
        <div style={{ opacity: laduje ? 0.45 : 1, transition: "opacity 0.25s ease" }}>{tresc}</div>
      </div>
    );
  } else {
    widok = laduje ? <Szkielet anim={wariant === "b" ? "puls" : "polysk"} /> : tresc;
  }

  return (
    <div className="a-scena" style={{ position: "relative" }}>
      <div style={{ maxWidth: 420, minHeight: 104 }}>{widok}</div>
      <button type="button" className="a-demo-guzik" onClick={() => setLaduje((l) => !l)}>
        {laduje ? "Pokaż gotowe" : "Pokaż ładowanie"}
      </button>
    </div>
  );
}

/* ======================================================================
   2.10 PRZYCISKI I PUSTY STAN
   ====================================================================== */

export function ScenaPrzyciskow() {
  return (
    <>
      <div className="a-scena">
        <div className="a-podpis">rodzaje × rozmiary (32 · 40 · 48 – największy na telefon)</div>
        <div style={{ display: "grid", gap: 12 }}>
          {(["s", "m", "l"] as const).map((r) => (
            <div key={r} className="a-rzad">
              <button type="button" className="a-guzik" data-t="glowny" data-r={r}>
                Dodaj do kuponu
              </button>
              <button type="button" className="a-guzik" data-t="drugi" data-r={r}>
                Skąd ta liczba
              </button>
              <button type="button" className="a-guzik" data-t="cichy" data-r={r}>
                Pokaż wszystkie →
              </button>
            </div>
          ))}
          <div className="a-rzad">
            <button type="button" className="a-guzik" data-t="ikona" aria-label="Ulubione">
              <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
                <path d="m8 2 1.8 3.8 4.2.5-3.1 2.9.8 4.1L8 11.3l-3.7 2 .8-4.1L2 6.3l4.2-.5Z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
              </svg>
            </button>
            <button type="button" className="a-guzik" data-t="ikona" aria-label="Udostępnij">
              <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
                <path d="M8 2v8M5 5l3-3 3 3M3 9v4h10V9" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </div>
      </div>
      <div className="a-scena">
        <div className="a-podpis">pusty stan – zdanie, powód i jedna akcja; bez obrazków</div>
        <div className="a-pusty">
          <div className="p-n" style={{ fontSize: 18 }}>
            Na jutro jeszcze nic
          </div>
          <p>Kursy na jutrzejsze mecze pojawiają się zwykle po 18:00. Wtedy model je przeliczy i dopisze typy.</p>
          <button type="button" className="a-guzik" data-t="drugi" data-r="m">
            Zobacz piątek · 17 meczów
          </button>
        </div>
      </div>
    </>
  );
}
