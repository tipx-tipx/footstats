"use client";

import { MotionConfig } from "framer-motion";
import { useEffect, useState } from "react";

import "../atomy.css";
import "../atomy2.css";
import "../elementy.css";

import type { DrabinkaV } from "../_dane/elementy";
import { Sekcja, type WariantAtomu } from "./atomy/wspolne";
import { ScenaDrabinki, type OznaczeniaD } from "./elementy/drabinka";

type Motyw = "ciemny" | "jasny";
const PALETA: Record<Motyw, string> = { ciemny: "b1", jasny: "p3" };

const WARIANTY: WariantAtomu[] = [
  { id: "0", nazwa: "Dziś", opis: "karta bez oznaczeń – punkt odniesienia." },
  {
    id: "a",
    nazwa: "A · Słowa",
    opis: "pod nazwiskiem wszystkie rodzaje karty słowem: perełka złotem, seria i forma zielenią z kreskami trafień, rywal z herbem, cena zwykłym tekstem. Pełne zdanie po najechaniu. Najszybciej się przegląda, karta nie rośnie.",
  },
  {
    id: "b",
    nazwa: "B · Zdania",
    opis: "pod drabinką klocek „powody” z karty typu: pełne zdania z liczbą o tym, czego karta jeszcze nie mówi (cena, skład, rywal). Perełka na przystanku zamiast „nasz typ”. Najwięcej wyjaśnia, karta rośnie o 0–3 linie.",
  },
  {
    id: "c",
    nazwa: "C · Jeden rodzaj",
    opis: "karta ma JEDEN najważniejszy rodzaj: słowo przy meczu, a perełka dodatkowo złotą kreskę 3 px u góry. Pod nazwiskiem jedno zdanie. Najspokojniej, ale reszta powodów znika.",
  },
  {
    id: "d",
    nazwa: "D · Słowa + mecz",
    opis: "do trzech słów pod nazwiskiem (jak A), a argument meczu (rywal, nowy klub) jednym zdaniem pod historią – tam, gdzie gracz patrzy na przeciwnika. Ceny obu bukmacherów stoją przy kursie we wszystkich wariantach.",
  },
  {
    id: "e",
    nazwa: "D · dopracowany",
    opis: "wybrany D po dopracowaniu: rywal tylko zdaniem z herbem (bez dubla w słowach), złota „perełka” na przystanku zamiast „nasz typ”, „XI” przy nazwisku. Tak pójdzie na stronę.",
  },
];

/** Wszystkie rodzaje z regułą i przykładem – teksty do oceny, także te, których dziś nie ma na żadnej karcie. */
const SLOWNIK: { slowo: string; grupa: "cena" | "forma" | "mecz"; kiedy: string; zdanie: string }[] = [
  { slowo: "Perełka", grupa: "cena", kiedy: "1. szczebel od 2,20 na mocnej linii", zdanie: "Kurs 2,20, a ta linia weszła w 7 z 10 ostatnich meczów" },
  { slowo: "Cena mówi: pewne", grupa: "cena", kiedy: "jeden bukmacher wycenia to jak niemal pewne, drugi płaci sensownie", zdanie: "Betclic daje tylko 1,15 – wycenia to jak niemal pewne; Superbet płaci 1,60" },
  { slowo: "Lepsza cena", grupa: "cena", kiedy: "duża różnica kursów między bukmacherami (12+ pkt proc.)", zdanie: "Superbet płaci 1,58, Betclic 1,32 za tę samą linię" },
  { slowo: "Kurs ponad szansę", grupa: "cena", kiedy: "szansa z analizy wyższa niż ta, za którą płaci kurs", zdanie: "Z analizy wychodzi 68%, a kurs 1,74 płaci jak za 57%" },
  { slowo: "Seria 9/10", grupa: "forma", kiedy: "linia weszła w 8+ z 10 ostatnich", zdanie: "Ta linia weszła w 9 z 10 ostatnich meczów" },
  { slowo: "Forma 5/5", grupa: "forma", kiedy: "weszła w każdym z 5 ostatnich", zdanie: "Weszła w każdym z 5 ostatnich meczów" },
  { slowo: "Nowy w klubie", grupa: "forma", kiedy: "karta liczona z profilu po transferze", zdanie: "Mało meczów w nowym klubie – liczymy też z poprzedniego sezonu" },
  { slowo: "Hojny rywal", grupa: "mecz", kiedy: "rywal pozwala na tym rynku o 10%+ więcej niż średnia ligi", zdanie: "Przeciw Valencii średnio 0,6 na zawodnika, w lidze 0,2" },
  { slowo: "Ceny zgodne", grupa: "cena", kiedy: "obaj bukmacherzy prawie tak samo – tylko w zdaniach, nie w nagłówku", zdanie: "Superbet 1,90, Betclic 1,88 – obaj wyceniają to tak samo" },
];

function Slownik() {
  return (
    <div className="el-karta" style={{ padding: "14px 16px", marginTop: 16 }}>
      <h3 className="el-kto" style={{ fontSize: 16, marginBottom: 4 }}>
        Słownik rodzajów
      </h3>
      <p style={{ margin: "0 0 12px", fontSize: 12, color: "var(--t3)" }}>
        Kolor = znaczenie: złoto tylko perełka (najrzadsza), zieleń tylko seria i forma (jak trafienia w historii), reszta zwykłym tekstem – cena mówi liczbami obok, rywal herbem. Słowo to nazwa, zdanie to fakt z liczbą. Bez „pewniak” i „gwarancja”. Skład nie jest rodzajem: „XI” przy nazwisku (pełne – skład ogłoszony, obrys – pewny start z historii, po najechaniu opis).
      </p>
      <div style={{ display: "grid", gap: 10 }}>
        {SLOWNIK.map((x) => (
          <div key={x.slowo} style={{ display: "grid", gridTemplateColumns: "minmax(120px, 160px) minmax(0, 1fr)", gap: 12, fontSize: 13 }}>
            <span className="el-drab-rodzaje" style={{ marginTop: 0 }}>
              <span data-grupa={x.grupa} data-kod={x.slowo === "Perełka" ? "perla" : undefined}>
                {x.slowo}
              </span>
            </span>
            <span style={{ color: "var(--t2)" }}>
              {x.zdanie}
              <small style={{ display: "block", color: "var(--t3)", fontSize: 11, marginTop: 2 }}>kiedy: {x.kiedy}</small>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export type StartRodzajow = Record<string, string | undefined>;

export function DrabinkiRodzaje({ karty, start }: { karty: DrabinkaV[]; start: StartRodzajow }) {
  const [motyw, setMotyw] = useState<Motyw>(start.m === "jasny" ? "jasny" : "ciemny");
  const [szer, setSzer] = useState<"pelna" | "telefon">(start.s === "telefon" ? "telefon" : "pelna");
  const [w, setW] = useState<string>(WARIANTY.some((x) => x.id === start.w) ? start.w! : "e");

  useEffect(() => {
    window.history.replaceState(null, "", `?${new URLSearchParams({ m: motyw, s: szer, w })}`);
  }, [motyw, szer, w]);

  const oz = w === "0" ? undefined : (w as OznaczeniaD);
  const telefon = szer === "telefon";
  const ekran = (
    <div className="p-ekran" data-p-motyw={motyw} data-p-paleta={PALETA[motyw]} data-p-font="2c">
      <div className="p-tresc" style={{ maxWidth: telefon ? 420 : 980 }}>
        <Sekcja
          nr="3.3b"
          tytul="Rodzaje drabinek"
          opis="Rodzaj = atut karty (ustalenia 28.07 i 17–18.09): cena (perełka, cena mówi: pewne, lepsza cena, kurs ponad szansę), forma (seria, forma, nowy w klubie) i mecz (hojny rywal); skład to warunek, więc stoi jako „XI” przy nazwisku. Kursy obu bukmacherów przy wybranej linii, gdy Betclic ją ma. Pięć pierwszych kart to prawdziwe karty z 06–10.10 (ceny z ostatniego zrzutu przed meczem), reszta to dzisiejsze karty z produkcji; słownik na dole."
          warianty={WARIANTY}
          wybrany={w}
          zmien={setW}
        >
          <div key={w} style={{ display: "grid", gridTemplateColumns: telefon ? "1fr" : "repeat(auto-fill, minmax(min(100%, 400px), 1fr))", gap: 12, alignItems: "start" }}>
            {karty.map((d) => (
              <ScenaDrabinki key={d.klucz ?? d.kto} wariant="a" d={d} oznaczenia={oz} />
            ))}
          </div>
          <Slownik />
        </Sekcja>
      </div>
    </div>
  );

  return (
    <MotionConfig reducedMotion="user">
      <div className="p-pulpit">
        <div className="p-pulpit-wnetrze">
          <div className="p-pulpit-tytul">
            Drabinki <span>· oznaczenia rodzajów</span>
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
          <div className="p-wybor">
            <span>ekran</span>
            <div className="p-segmenty" role="group">
              {(["pelna", "telefon"] as const).map((x) => (
                <button key={x} type="button" aria-pressed={szer === x} onClick={() => setSzer(x)}>
                  {x === "pelna" ? "Komputer" : "Telefon"}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="p-pulpit-opis">Wybór zapisuje się w adresie strony – wystarczy przesłać link.</div>
      </div>
      {telefon ? <div className="p-rama-telefon">{ekran}</div> : ekran}
    </MotionConfig>
  );
}
