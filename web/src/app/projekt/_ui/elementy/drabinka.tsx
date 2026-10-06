"use client";

import { Lnk } from "../linki";
import { motion } from "framer-motion";
import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import { fmtKurs, fmtLinia } from "@/lib/format";

import type { DrabinkaV, SzczebelV } from "../../_dane/elementy";
import type { TypV } from "../../_dane/przygotuj";
import { Blysk } from "../atomy/wyniki-ruch";
import { KafelekD, KratkiD } from "../atomy2/podstawowe";
import { Herb } from "../Herb";

/**
 * Drabinka: jeden zawodnik, kilka linii tego samego rynku. Wspólna zasada
 * wszystkich wariantów: WYBÓR LINII PRZEBARWIA HISTORIĘ – kratki od razu
 * pokazują, w ilu meczach ta konkretna linia by weszła.
 */

function Kratki({ d, linia }: { d: DrabinkaV; linia: number }) {
  const t = {
    historia: d.historia,
    minuty: d.minuty,
    rywale: d.rywale,
    daty: d.historia.map(() => ""),
    kadra: d.historia.map(() => true),
    linia,
    strona: "powyzej",
  } as unknown as TypV;
  return <KratkiD t={t} />;
}

/* Szansę pokazujemy TYLKO przy naszym typie (05.10). Dalsze szczeble deklarowały
   ok. 35% i 21%, a weszły w 16% i 6% (70 i 49 kart) – liczba wprowadzała w błąd. */
const szansaWidoczna = (s: SzczebelV) => s.polecany && s.p !== null;
function bezSzansy(s: SzczebelV, d: DrabinkaV): string {
  const nasza = d.szczeble.find((x) => x.polecany)?.linia ?? null;
  if (nasza !== null && s.linia < nasza) return "Kurs za niski – nie typujemy";
  if (s.p !== null) return "Dalszy szczebel – wchodzi rzadko, szansy nie podajemy";
  return "Za mała szansa – nie typujemy";
}

function Wybrany({ s, d }: { s: SzczebelV; d: DrabinkaV }) {
  return (
    <div className="el-drab-wybor">
      <div>
        <div className="el-drab-wybor-linia">
          {d.rynek.toLowerCase()} powyżej {fmtLinia(s.linia)}
          {s.polecany && <span className="el-nasz">nasz typ</span>}
        </div>
        <small style={{ display: "block", marginTop: 4, color: "var(--t3)", fontSize: 12 }}>
          weszłoby w {s.traf} z {s.z} ostatnich meczów
        </small>
      </div>
      <div className="el-drab-wybor-prawa">
        {szansaWidoczna(s) && s.p !== null ? (
          <span className="d-szansa-liczba" style={{ fontSize: 22 }}>
            <Blysk tekst={`${Math.round(s.p * 100)}%`} kier={null} />
          </span>
        ) : (
          <span style={{ color: "var(--t3)", fontSize: 12, maxWidth: 120, textAlign: "right" }}>{bezSzansy(s, d)}</span>
        )}
        <KafelekD k={{ kurs: s.kurs, bukmacher: s.bukmacher, teraz: s.teraz, terazBukmacher: s.terazBukmacher }} />
      </div>
    </div>
  );
}

function Glowa({ d }: { d: DrabinkaV }) {
  return (
    <div style={{ display: "grid", gap: 10 }}>
      <div className="el-karta-meta">
        <Herb d={d.druzyna} tryb="prawdziwy" rozmiar={15} />
        <span>{d.mecz}</span>
        <time>
          {d.dzien}, {d.godzina}
        </time>
      </div>
      <div>
        <h3 className="el-kto">{d.podmiotId ? <Lnk href={`/zawodnik/${d.podmiotId}`}>{d.kto}</Lnk> : d.kto}</h3>
        <div className="el-kto-pod">
          {d.pozycja} · {d.druzyna.nazwa} · drabinka: {d.rynek.toLowerCase()}
        </div>
      </div>
    </div>
  );
}

function useWybor(d: DrabinkaV) {
  const start = Math.max(0, d.szczeble.findIndex((s) => s.polecany));
  const [i, setI] = useState(start);
  const klawisze = (e: KeyboardEvent) => {
    if (e.key === "ArrowRight" || e.key === "ArrowUp") {
      e.preventDefault();
      setI((x) => Math.min(x + 1, d.szczeble.length - 1));
    }
    if (e.key === "ArrowLeft" || e.key === "ArrowDown") {
      e.preventDefault();
      setI((x) => Math.max(x - 1, 0));
    }
  };
  return { i, setI, klawisze };
}

/* A · suwak linii (Polymarket), dopracowany 01.10:
   przeciąganie z przyciąganiem do linii, kolor przystanku = jak często wchodziła,
   wibracja przy przeskoku na telefonie, strzałki na klawiaturze */
function Suwak({ d }: { d: DrabinkaV }) {
  const { i, setI, klawisze } = useWybor(d);
  const n = d.szczeble.length;
  const s = d.szczeble[i];
  const rama = useRef<HTMLDivElement>(null);
  const [ciagnie, setCiagnie] = useState(false);

  const ustawZ = (x: number) => {
    const r = rama.current?.getBoundingClientRect();
    if (!r) return;
    const j = Math.min(n - 1, Math.max(0, Math.floor(((x - r.left) / r.width) * n)));
    setI((stary) => {
      if (stary !== j && typeof navigator !== "undefined" && "vibrate" in navigator) navigator.vibrate?.(6);
      return j;
    });
  };
  const start = (e: PointerEvent) => {
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    setCiagnie(true);
    ustawZ(e.clientX);
  };

  return (
    <>
      <div
        ref={rama}
        className="el-suwak"
        data-ciagnie={ciagnie || undefined}
        role="radiogroup"
        aria-label="Linia – przeciągnij albo wybierz"
        onKeyDown={klawisze}
        onPointerDown={start}
        onPointerMove={(e) => ciagnie && ustawZ(e.clientX)}
        onPointerUp={() => setCiagnie(false)}
        onPointerCancel={() => setCiagnie(false)}
      >
        <div className="el-suwak-tor" aria-hidden />
        <motion.div
          className="el-suwak-wypelnienie"
          aria-hidden
          animate={{ width: `${((i + 0.5) / n) * 100}%` }}
          transition={{ type: "spring", stiffness: 420, damping: 34 }}
        />
        <motion.div
          className="el-suwak-znacznik"
          aria-hidden
          animate={{ left: `${((i + 0.5) / n) * 100}%`, scale: ciagnie ? 1.15 : 1 }}
          transition={{ type: "spring", stiffness: 420, damping: 34 }}
        />
        <div className="el-suwak-przystanki">
          {d.szczeble.map((x, j) => {
            const r = x.traf / x.z;
            return (
              <button
                key={x.linia}
                type="button"
                role="radio"
                aria-checked={j === i}
                aria-label={`powyżej ${fmtLinia(x.linia)}, kurs ${fmtKurs(x.teraz ?? x.kurs)}, weszło ${x.traf} z ${x.z}`}
                tabIndex={j === i ? 0 : -1}
                className="el-przystanek"
                data-pokrycie={r >= 0.8 ? "mocne" : r >= 0.5 ? "srednie" : "slabe"}
                onClick={() => setI(j)}
              >
                {x.polecany && <span className="el-przystanek-nasz">nasz typ</span>}
                <span className="el-przystanek-linia">{fmtLinia(x.linia)}</span>
                <span className="el-przystanek-kropka" />
                {/* ta sama cena co gruba w kafelku – bieżąca, gdy się ruszyła */}
                <span className="el-przystanek-kurs">{fmtKurs(x.teraz ?? x.kurs)}</span>
                <span className="el-przystanek-pokrycie">
                  {x.traf}/{x.z}
                </span>
              </button>
            );
          })}
        </div>
      </div>
      <Wybrany s={s} d={d} />
      <Kratki d={d} linia={s.linia} />
    </>
  );
}

/* B · schody: im wyżej, tym więcej płaci i rzadziej wchodzi */
function Schody({ d }: { d: DrabinkaV }) {
  const { i, setI, klawisze } = useWybor(d);
  const s = d.szczeble[i];
  const n = d.szczeble.length;
  return (
    <>
      <div className="el-schody" role="radiogroup" aria-label="Linia" onKeyDown={klawisze}>
        {d.szczeble.map((x, j) => {
          const wys = 34 + ((j + 1) / n) * 66; // schody rosną z linią
          const pokrycie = x.traf / x.z;
          return (
            <button key={x.linia} type="button" role="radio" aria-checked={j === i} tabIndex={j === i ? 0 : -1} className="el-stopien" onClick={() => setI(j)}>
              <span className="el-stopien-kurs">{fmtKurs(x.teraz ?? x.kurs)}</span>
              <motion.span
                className="el-stopien-slup"
                initial={{ height: 0 }}
                animate={{ height: `${wys}%` }}
                transition={{ delay: j * 0.06, type: "spring", stiffness: 200, damping: 24 }}
              >
                {/* jedna liczba na stopniu: w ilu meczach weszło; szansa jest w panelu pod spodem */}
                <span className="el-stopien-proc">
                  {x.traf}/{x.z}
                </span>
                <motion.span
                  className="el-stopien-wypelnienie"
                  style={{ borderTopWidth: x.traf ? 2 : 0 }}
                  initial={{ height: 0 }}
                  animate={{ height: `${pokrycie * 100}%` }}
                  transition={{ delay: 0.2 + j * 0.06, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
                />
              </motion.span>
              <span className="el-stopien-linia">
                pow. {fmtLinia(x.linia)}
                {x.polecany ? " · nasz" : ""}
              </span>
            </button>
          );
        })}
      </div>
      <Wybrany s={s} d={d} />
      <Kratki d={d} linia={s.linia} />
    </>
  );
}

/* C · tabela szczebli: najgęściej, dobre na telefon */
function Tabela({ d }: { d: DrabinkaV }) {
  const { i, setI, klawisze } = useWybor(d);
  const s = d.szczeble[i];
  return (
    <>
      <div className="el-tabela" role="radiogroup" aria-label="Linia" onKeyDown={klawisze}>
        {d.szczeble.map((x, j) => (
          <div
            key={x.linia}
            role="radio"
            aria-checked={j === i}
            tabIndex={j === i ? 0 : -1}
            className="el-szczebel"
            onClick={() => setI(j)}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setI(j)}
          >
            <span className="el-szczebel-linia">
              powyżej {fmtLinia(x.linia)}
              {x.polecany && <span className="el-nasz">nasz typ</span>}
            </span>
            <span className="el-szczebel-pokrycie">
              {x.traf}/{x.z} meczów
            </span>
            <span className="el-szczebel-p" data-brak={szansaWidoczna(x) ? undefined : "true"}>
              {szansaWidoczna(x) && x.p !== null ? `${Math.round(x.p * 100)}%` : "–"}
            </span>
            <span onClick={(e) => e.stopPropagation()}>
              <KafelekD k={{ kurs: x.kurs, bukmacher: x.bukmacher, teraz: x.teraz, terazBukmacher: x.terazBukmacher }} />
            </span>
          </div>
        ))}
      </div>
      <Kratki d={d} linia={s.linia} />
    </>
  );
}

/**
 * 01.10: próg, który w ostatnich meczach nie wszedł ANI RAZU i którego nie
 * liczymy (brak naszej szansy), to tylko kusząco wysoki kurs bez podstaw –
 * nie pokazujemy go jako przystanku, zostaje jedno zdanie wyjaśnienia.
 */
function bezPustych(d: DrabinkaV): { d: DrabinkaV; ukryte: SzczebelV[] } {
  const ukryte = d.szczeble.filter((s) => s.traf === 0 && s.p === null && !s.polecany);
  return { d: { ...d, szczeble: d.szczeble.filter((s) => !ukryte.includes(s)) }, ukryte };
}

export function ScenaDrabinki({ wariant, d: surowa }: { wariant: string; d: DrabinkaV | null }) {
  if (!surowa) return null;
  const { d, ukryte } = bezPustych(surowa);
  return (
    <article className="el-karta el-drabinka">
      <Glowa d={d} />
      {wariant === "b" ? <Schody d={d} /> : wariant === "c" ? <Tabela d={d} /> : <Suwak d={d} />}
      {ukryte.length > 0 && (
        <p className="p-t3" style={{ fontSize: 12 }}>
          Wyższe progi ({ukryte.map((s) => fmtLinia(s.linia)).join(" i ")}) pomijamy – w ostatnich {ukryte[0].z} meczach nie weszły ani
          razu.
        </p>
      )}
    </article>
  );
}
