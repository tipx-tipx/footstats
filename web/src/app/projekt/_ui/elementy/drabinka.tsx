"use client";

import { Lnk } from "../linki";
import { motion } from "framer-motion";
import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import { fmtKurs, fmtLinia } from "@/lib/format";

import type { DrabinkaV, RodzajD, SzczebelV } from "../../_dane/elementy";
import type { TypV } from "../../_dane/przygotuj";
import { Blysk } from "../atomy/wyniki-ruch";
import { KafelekD, KratkiD } from "../atomy2/podstawowe";
import { Herb } from "../Herb";
import { Powody } from "./karta";

/**
 * OZNACZENIA RODZAJÓW (warsztat 11.10, do wyboru właściciela). Rodzaj = powód,
 * na którym karta stoi (`DrabinkaV.rodzaje`); bez wybranego wariantu karta
 * wygląda jak dotąd. Wspólne zasady wszystkich wariantów:
 *   – jeden kolor, jedno znaczenie: bursztyn = argument z ceny, reszta tekstem,
 *   – słowo („krótko”) to nazwa rodzaju, zdanie to fakt z liczbą,
 *   – seria i forma są na karcie liczbami (kratki), więc w zdaniach ich nie ma.
 *   a – słowa w nagłówku, b – zdania pod drabinką, c – główny rodzaj (kreska
 *   ceny) + jedno zdanie, d – argumenty na swoich miejscach (cena przy kursie,
 *   mecz i skład pod historią)
 */
export type OznaczeniaD = "a" | "b" | "c" | "d" | "e";
/** e = D dopracowany (wybór właściciela 11.10) – na produkcji */
const jakD = (oz?: OznaczeniaD) => oz === "d" || oz === "e";
const rodzajeD = (d: DrabinkaV) => d.rodzaje ?? [];
const naglowkowe = (d: DrabinkaV) => rodzajeD(d).filter((r) => r.wNaglowku);
const jestPerla = (d: DrabinkaV) => rodzajeD(d).some((r) => r.kod === "perla");
const WIDOCZNE_W_KRATKACH = ["seria", "forma"];
const zdaniaPowodow = (d: DrabinkaV) => rodzajeD(d).filter((r) => r.kod !== "perla" && !WIDOCZNE_W_KRATKACH.includes(r.kod));
/** d: argumenty meczu i zawodnika (bez ceny – ta stoi przy kursie) */
const zdaniaMeczu = (d: DrabinkaV) => zdaniaPowodow(d).filter((r) => r.grupa !== "cena");

/**
 * ZNAK RODZAJU – z języka karty, nie ikona: seria i forma to te same kreski
 * trafień co w historii (zieleń = weszło), skład to „XI”, rywal to jego herb,
 * argument z ceny to bursztyn. Kolor niesie znaczenie, nie ozdobę.
 */
function ZnakRodzaju({ r, d }: { r: RodzajD; d: DrabinkaV }) {
  const linia = d.szczeble.find((x) => x.polecany)?.linia ?? 0;
  if (r.kod === "seria" || r.kod === "forma") {
    const okno = (r.kod === "forma" ? d.historia.slice(-5) : d.historia).slice(-10);
    return (
      <i className="el-drab-kreski" aria-hidden>
        {okno.map((v, j) => (
          <b key={j} data-s={v > linia ? "ok" : undefined} />
        ))}
      </i>
    );
  }
  if (r.kod === "rywal" || r.kod === "h2h") return <Herb d={d.rywal} tryb="prawdziwy" rozmiar={13} />;
  return null;
}

function Slowa({ d, ile, bezMeczu }: { d: DrabinkaV; ile?: number; bezMeczu?: boolean }) {
  // e: argument meczu stoi zdaniem pod historią – w nagłówku byłby dublem
  const lista = naglowkowe(d).filter((r) => !bezMeczu || r.grupa !== "mecz").slice(0, ile ?? 99);
  if (!lista.length) return null;
  return (
    <div className="el-drab-rodzaje">
      {lista.map((r) => (
        <span key={r.kod} data-grupa={r.grupa} data-kod={r.kod} title={r.zdanie}>
          <ZnakRodzaju r={r} d={d} />
          {r.krotko}
        </span>
      ))}
    </div>
  );
}

/**
 * SKŁAD – warunek, nie rodzaj (właściciel 11.10). „XI” przy nazwisku: pełne =
 * ogłoszony skład, obrys = pewny start z historii; brak znaku = nie wiemy.
 */
function ZnakSkladu({ d }: { d: DrabinkaV }) {
  if (!d.sklad) return null;
  return (
    <i className="el-drab-xi" data-ogloszony={d.sklad.stan === "ogloszony" || undefined} title={d.sklad.opis} aria-label={d.sklad.opis}>
      XI
    </i>
  );
}

/**
 * KURS U OBU BUKMACHERÓW (właściciel 11.10: „w każdej drabince kursy obu,
 * a jak nie ma jednego – nie pisać”). Dwa te same kafelki co wszędzie;
 * wyższa cena jest wybrana. Druga cena tylko pewna (siatka strony meczu).
 */
function KursyObu({ s }: { s: SzczebelV }) {
  const sb = { kurs: s.kurs, bukmacher: s.bukmacher, teraz: s.teraz, terazBukmacher: s.terazBukmacher };
  if (!s.betclic) return <KafelekD k={sb} />;
  return (
    <span className="el-drab-kursy">
      {/* bez wyróżniania wyższej ceny (właściciel 11.10) – liczby mówią same */}
      <KafelekD k={sb} />
      <KafelekD k={{ kurs: s.betclic, bukmacher: "Betclic" }} />
    </span>
  );
}

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
/* 11.10 (właściciel: „krócej, bez łamania”): słowo na karcie, wyjaśnienie w dymku */
function bezSzansy(s: SzczebelV, d: DrabinkaV): { krotko: string; dymek: string } {
  const nasza = d.szczeble.find((x) => x.polecany)?.linia ?? null;
  if (nasza !== null && s.linia < nasza) return { krotko: "Za niski kurs", dymek: "Kurs za niski – tego szczebla nie typujemy" };
  if (s.p !== null) return { krotko: "Dalszy szczebel", dymek: "Wchodzi rzadko – szansy nie podajemy, bo myliłaby" };
  return { krotko: "Za mała szansa", dymek: "Za mała szansa – tego szczebla nie typujemy" };
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
          weszło w {s.traf} z {s.z} ostatnich
        </small>
      </div>
      <div className="el-drab-wybor-prawa">
        {szansaWidoczna(s) && s.p !== null ? (
          <span className="d-szansa-liczba" style={{ fontSize: 22 }}>
            <Blysk tekst={`${Math.round(s.p * 100)}%`} kier={null} />
          </span>
        ) : (
          <span className="el-drab-bez" title={bezSzansy(s, d).dymek}>
            {bezSzansy(s, d).krotko}
          </span>
        )}
        <KursyObu s={s} />
      </div>
    </div>
  );
}

function Glowa({ d, oz }: { d: DrabinkaV; oz?: OznaczeniaD }) {
  const glowny = naglowkowe(d)[0];
  const zdanieC = zdaniaPowodow(d)[0];
  return (
    <div style={{ display: "grid", gap: 10 }}>
      <div className="el-karta-meta">
        <Herb d={d.druzyna} tryb="prawdziwy" rozmiar={15} />
        <span>{d.mecz}</span>
        {oz === "c" && glowny && (
          <span className="el-drab-glowny" data-grupa={glowny.grupa} data-kod={glowny.kod}>
            {glowny.krotko}
          </span>
        )}
        <time>
          {d.dzien}, {d.godzina}
        </time>
      </div>
      <div>
        <h3 className="el-kto">
          {d.podmiotId ? <Lnk href={`/zawodnik/${d.podmiotId}`}>{d.kto}</Lnk> : d.kto}
          {oz && <ZnakSkladu d={d} />}
        </h3>
        <div className="el-kto-pod">
          {d.pozycja} · {d.druzyna.nazwa} · drabinka: {d.rynek.toLowerCase()}
        </div>
        {oz === "a" && <Slowa d={d} />}
        {oz === "d" && <Slowa d={d} ile={3} />}
        {oz === "e" && <Slowa d={d} ile={3} bezMeczu />}
        {oz === "c" && zdanieC && <div className="el-drab-zdanie">{zdanieC.zdanie}</div>}
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
function Suwak({ d, oz }: { d: DrabinkaV; oz?: OznaczeniaD }) {
  const perlaNaPrzystanku = (oz === "b" || oz === "e") && jestPerla(d);
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
                {x.polecany && (
                  <span className="el-przystanek-nasz" data-perla={perlaNaPrzystanku || undefined}>
                    {perlaNaPrzystanku ? "perełka" : "nasz typ"}
                  </span>
                )}
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

export function ScenaDrabinki({ wariant, d: surowa, oznaczenia: oz }: { wariant: string; d: DrabinkaV | null; oznaczenia?: OznaczeniaD }) {
  if (!surowa) return null;
  const { d, ukryte } = bezPustych(surowa);
  const powody = oz === "b" ? zdaniaPowodow(d) : [];
  const meczD = jakD(oz) ? zdaniaMeczu(d) : [];
  const glowny = naglowkowe(d)[0];
  return (
    <article className="el-karta el-drabinka" data-kreska={(oz === "c" && glowny?.kod === "perla") || undefined}>
      <Glowa d={d} oz={oz} />
      {wariant === "b" ? <Schody d={d} /> : wariant === "c" ? <Tabela d={d} /> : <Suwak d={d} oz={oz} />}
      {powody.length > 0 && <Powody powody={powody.map((r) => ({ tekst: r.zdanie, kier: "za" as const }))} />}
      {meczD.length > 0 && (
        <div className="el-drab-mecz">
          {meczD.map((r) => (
            <p key={r.kod}>
              {oz === "e" && (r.kod === "rywal" || r.kod === "h2h") && <Herb d={d.rywal} tryb="prawdziwy" rozmiar={14} />}
              {r.zdanie}
            </p>
          ))}
        </div>
      )}
      {ukryte.length > 0 && (
        <p className="p-t3" style={{ fontSize: 12 }}>
          Wyższe progi ({ukryte.map((s) => fmtLinia(s.linia)).join(" i ")}) pomijamy – w ostatnich {ukryte[0].z} meczach nie weszły ani
          razu.
        </p>
      )}
    </article>
  );
}
