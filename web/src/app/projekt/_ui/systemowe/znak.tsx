"use client";

import { motion, useReducedMotion } from "framer-motion";
import { useId } from "react";

import { NapisLogo } from "../LogoPoziome";

/* ---- znak marki: jedno pióro dla całej rodziny ------------------------- */

// geometria w układzie 400 × 340: piłka (środek 170,170, r 150) jak w logo,
// łuk otwarty z prawej-dołu, tam wychodzi linia wykresu
const LUK_OD_DOLU = "M109 307 A150 150 0 1 1 303.6 101.9";
const SZWY = [
  // pięciokąt w środku
  "M140 84 L181.8 114.4 L165.9 163.6 L114.1 163.6 L98.2 114.4 Z",
  // szwy od wierzchołków na zewnątrz
  "M140 84 L140 33",
  "M181.8 114.4 L230.4 98.6",
  "M165.9 163.6 L195.8 204.9",
  "M114.1 163.6 L84.2 204.9",
  "M98.2 114.4 L49.6 98.6",
  // sąsiednie sześciokąty
  "M140 33 L207.6 35 L230.4 98.6 L249.4 163.5 L195.8 204.9 L140 243 L84.2 204.9 L30.6 163.5 L49.6 98.6 L72.4 35 Z",
  "M207.6 35 L240 -10 M249.4 163.5 L320 180 M140 243 L140 330 M30.6 163.5 L-30 180 M72.4 35 L40 -10",
];
const WYKRES: [number, number][] = [
  [102, 300],
  [186, 214],
  [236, 252],
  [288, 176],
  [372, 86],
];
// szwy kończą się na linii wykresu (jak w logo) – przycinamy je wielokątem nad linią
const NAD_LINIA = "M-40 -40 L440 -40 L440 40 L372 86 L288 176 L236 252 L186 214 L102 300 L-40 360 Z";

/*
 * Kolejność jak pióro rysujące logo: łuk piłki jednym pociągnięciem (od dołu,
 * tam gdzie startuje wykres, dookoła do prawej-góry), szwy od środka na
 * zewnątrz, potem wykres odcinek po odcinku – każda kropka wskakuje dokładnie
 * w chwili, gdy linia do niej dochodzi. Raz, przy wejściu. Przy ograniczonym
 * ruchu – od razu gotowe.
 *
 * Rodzina: `logo` (gruba kreska, mały rozmiar), `duzy` (tło i ilustracje),
 * koniec `blad` (wykres urywa się czerwoną pustą kropką), `brak` (urywa się
 * szarą przerywaną kropką – 404 i brak internetu).
 */
const T = { luk: 0, lukCzas: 0.75, szwy: 0.5, wykres: 0.86, odcinek: 0.17 };
const GRUBOSC = {
  logo: { luk: 18, szwy: 14, wykres: 16, kropka: 24 },
  duzy: { luk: 8, szwy: 6, wykres: 8, kropka: 13 },
};

export function ZnakRysowany({
  className,
  styl = "duzy",
  koniec = "pelny",
  start = 0,
  tempo = 1,
  szer,
  wys,
}: {
  className?: string;
  styl?: keyof typeof GRUBOSC;
  koniec?: "pelny" | "blad" | "brak";
  start?: number;
  /** >1 = wolniej (tło rysuje się spokojniej niż logo) */
  tempo?: number;
  szer?: number;
  wys?: number;
}) {
  const id = useId().replace(/:/g, "");
  // initial zawsze ten sam (serwer = przeglądarka, bez rozjazdu hydracji);
  // przy ograniczonym ruchu znak rysuje się w zerowym czasie
  const reduced = useReducedMotion();
  const g = GRUBOSC[styl];
  const d = (s: number) => (reduced ? 0 : start + s * tempo);
  const czasRys = reduced ? 0 : tempo;
  const pelny = koniec === "pelny";
  // przy urwanym wykresie rysujemy dwa odcinki, trzeci jest przerywany
  const punkty = pelny ? WYKRES : WYKRES.slice(0, 3);
  const odcinki = punkty.slice(1).map((p, i) => [punkty[i], p] as const);
  const naRaz = (s: number) => ({ delay: d(s), duration: 0.01 });
  return (
    <svg className={className} width={szer} height={wys} viewBox="0 0 400 340" fill="none" aria-hidden overflow="visible">
      <defs>
        <clipPath id={`${id}-kolo`}>
          <circle cx="170" cy="170" r="146" />
        </clipPath>
        <clipPath id={`${id}-nad`}>
          <path d={NAD_LINIA} />
        </clipPath>
      </defs>
      <motion.path
        className="zn-luk"
        d={LUK_OD_DOLU}
        stroke="currentColor"
        strokeWidth={g.luk}
        strokeLinecap="round"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: 1, opacity: 1 }}
        transition={{ pathLength: { delay: d(T.luk), duration: T.lukCzas * czasRys, ease: [0.65, 0, 0.35, 1] }, opacity: naRaz(T.luk) }}
      />
      <g clipPath={`url(#${id}-kolo)`}>
        <g className="zn-szwy" clipPath={`url(#${id}-nad)`} stroke="currentColor" strokeWidth={g.szwy} strokeLinejoin="round" strokeLinecap="round">
          {SZWY.map((p, i) => (
            <motion.path
              key={i}
              d={p}
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ pathLength: 1, opacity: 1 }}
              transition={{
                pathLength: { delay: d(T.szwy + i * 0.045), duration: (i === 0 ? 0.32 : 0.26) * tempo, ease: "easeOut" },
                opacity: naRaz(T.szwy + i * 0.045),
              }}
            />
          ))}
        </g>
      </g>
      {odcinki.map(([a, b], i) => (
        <motion.line
          key={i}
          className="zn-wykres"
          x1={a[0]}
          y1={a[1]}
          x2={b[0]}
          y2={b[1]}
          stroke="var(--marka)"
          strokeWidth={g.wykres}
          strokeLinecap="round"
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ pathLength: { delay: d(T.wykres + i * T.odcinek), duration: T.odcinek * czasRys, ease: "linear" }, opacity: naRaz(T.wykres + i * T.odcinek) }}
        />
      ))}
      {punkty.slice(1).map(([x, y], i) => (
        <motion.circle
          key={i}
          className="zn-kropka"
          cx={x}
          cy={y}
          r={g.kropka}
          fill="var(--marka)"
          style={{ transformBox: "fill-box", transformOrigin: "center" }}
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ delay: d(T.wykres + (i + 1) * T.odcinek) - 0.02, type: "spring", stiffness: 640, damping: 18 }}
        />
      ))}
      {!pelny && (
        <>
          {/* urwany odcinek: kreski tam, gdzie wykres miał iść dalej */}
          <motion.line
            x1={250}
            y1={232}
            x2={279}
            y2={189}
            stroke="currentColor"
            strokeOpacity="0.5"
            strokeWidth={g.szwy}
            strokeDasharray={`${g.szwy * 0.4} ${g.szwy * 2}`}
            strokeLinecap="round"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: d(T.wykres + 2 * T.odcinek + 0.15), duration: 0.3 }}
          />
          <motion.circle
            cx={288}
            cy={176}
            r={g.kropka - 1}
            fill="var(--tlo)"
            stroke={koniec === "blad" ? "var(--nie)" : "currentColor"}
            strokeOpacity={koniec === "blad" ? 1 : 0.6}
            strokeWidth={g.szwy * 0.7}
            strokeDasharray={koniec === "brak" ? `${g.szwy * 0.8} ${g.szwy * 0.9}` : undefined}
            style={{ transformBox: "fill-box", transformOrigin: "center" }}
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: d(T.wykres + 2 * T.odcinek + 0.35), type: "spring", stiffness: 520, damping: 20 }}
          />
        </>
      )}
      {/* ostatnia kropka raz „odbija” – wykres doszedł na górę */}
      {pelny && (
        <motion.circle
          cx={372}
          cy={86}
          r={g.kropka}
          stroke="var(--marka)"
          strokeWidth={g.szwy * 0.6}
          style={{ transformBox: "fill-box", transformOrigin: "center" }}
          initial={{ scale: 1, opacity: 0 }}
          animate={reduced ? { opacity: 0 } : { scale: [1, 2.4], opacity: [0.6, 0] }}
          transition={{ delay: d(T.wykres + 4 * T.odcinek + 0.1), duration: 0.8, ease: "easeOut" }}
        />
      )}
    </svg>
  );
}

/** czas, w którym znak kończy się rysować (do zgrania napisu i reszty) */
export const KONIEC_ZNAKU = T.wykres + 4 * T.odcinek;

/* ---- logo animowane ------------------------------------------------------ */

export function LogoAnimowane({ jasne, wysokosc = 44, start = 0 }: { jasne: boolean; wysokosc?: number; start?: number }) {
  const reduced = useReducedMotion();
  return (
    <span className="sy-logo-anim" role="img" aria-label="FootStats">
      <ZnakRysowany styl="logo" start={start} szer={Math.round((wysokosc * 400) / 340)} wys={wysokosc} className="sy-logo-anim-znak" />
      <motion.span
        className="sy-logo-anim-napis"
        initial={{ clipPath: "inset(0 100% 0 0)", x: -6 }}
        animate={{ clipPath: "inset(0 0% 0 0)", x: 0 }}
        transition={reduced ? { duration: 0 } : { delay: start + KONIEC_ZNAKU - 0.28, duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
      >
        <NapisLogo jasne={jasne} wysokosc={Math.round(wysokosc * 0.5)} />
      </motion.span>
    </span>
  );
}
