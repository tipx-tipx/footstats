"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { KURS_KROK, KURS_MAX, KURS_MIN } from "../liniePomiar";

/*
 * Suwak „kurs od” (Mecze › Najlepsze linie, 05.11 – właściciel: „suwak, i tam
 * co 0,10 zmieniać … dopracowane zarówno do mobile, jak i desktop”; „od kurs.
 * A do nie trzeba”).
 *
 *  - jeden uchwyt, krok 0,10, skala 1,30 … 4,00 (dalej jest 3% linii);
 *  - klawiatura: strzałki ±0,10, PageUp/PageDown ±0,50, Home/End;
 *  - nad torem rozkład linii przy pozostałych progach – widać, ile zostaje
 *    po przesunięciu, zanim się przeciągnie;
 *  - wskaźnik obsługujemy NATYWNYMI słuchaczami z `stopPropagation`: na
 *    telefonie suwak siedzi w arkuszu, który framer-motion przeciąga w pionie
 *    (też natywnie) – bez tego poziomy ruch palca ciągnąłby cały arkusz.
 */

const N = Math.round((KURS_MAX - KURS_MIN) / KURS_KROK);
const doIndeksu = (k: number) => Math.min(N, Math.max(0, Math.round((k - KURS_MIN) / KURS_KROK)));
const zIndeksu = (i: number) => Math.round((KURS_MIN + i * KURS_KROK) * 100) / 100;
const txt = (k: number) => k.toFixed(2).replace(".", ",");
const ZNACZNIKI = [1.3, 2, 2.5, 3, 4];

export function SuwakKursu({
  od,
  rozklad,
  zmien,
}: {
  od: number;
  /** liczba linii w każdym kroku skali (N + 1 kubełków, ostatni = 4,00 i więcej) */
  rozklad: number[];
  zmien: (od: number) => void;
}) {
  const i = doIndeksu(od);
  const tor = useRef<HTMLDivElement>(null);
  const korzen = useRef<HTMLDivElement>(null);
  const uchwyt = useRef<HTMLSpanElement>(null);
  const [ciagnie, setCiagnie] = useState(false);
  // aktualne wartości dla natywnych słuchaczy (nie przepinamy ich przy każdym ruchu)
  const stan = useRef({ i, zmien });
  useLayoutEffect(() => {
    stan.current = { i, zmien };
  });

  const ustaw = (n: number) => {
    const k = Math.min(N, Math.max(0, n));
    if (k !== stan.current.i) stan.current.zmien(zIndeksu(k));
  };

  useEffect(() => {
    const el = korzen.current;
    if (!el) return;
    let aktywny = false;
    const indeks = (x: number) => {
      const r = tor.current!.getBoundingClientRect();
      return Math.round(((x - r.left) / r.width) * N);
    };
    const dol = (e: PointerEvent) => {
      if (e.button !== 0) return;
      e.stopPropagation();
      e.preventDefault();
      aktywny = true;
      setCiagnie(true);
      el.setPointerCapture(e.pointerId);
      ustaw(indeks(e.clientX));
      uchwyt.current?.focus({ preventScroll: true });
    };
    const ruch = (e: PointerEvent) => {
      if (!aktywny) return;
      e.stopPropagation();
      ustaw(indeks(e.clientX));
    };
    const gora = (e: PointerEvent) => {
      if (!aktywny) return;
      aktywny = false;
      setCiagnie(false);
      if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
    };
    el.addEventListener("pointerdown", dol);
    el.addEventListener("pointermove", ruch);
    el.addEventListener("pointerup", gora);
    el.addEventListener("pointercancel", gora);
    return () => {
      el.removeEventListener("pointerdown", dol);
      el.removeEventListener("pointermove", ruch);
      el.removeEventListener("pointerup", gora);
      el.removeEventListener("pointercancel", gora);
    };
  }, []);

  const klawisz = (e: React.KeyboardEvent) => {
    const krok: Record<string, number> = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1, PageDown: -5, PageUp: 5 };
    if (e.key in krok) ustaw(i + krok[e.key]);
    else if (e.key === "Home") ustaw(0);
    else if (e.key === "End") ustaw(N);
    else return;
    e.preventDefault();
  };

  // pierwiastek: przy 1,30–1,60 bywa 30× więcej linii niż przy 3,00 – liniowo droższe ceny znikały
  const max = Math.sqrt(Math.max(1, ...rozklad));
  const proc = (x: number) => `${(x / N) * 100}%`;

  return (
    <div className="sk" ref={korzen} data-ciagnie={ciagnie || undefined}>
      <div className="sk-wartosc" aria-hidden>
        <span>od</span>
        <b>{txt(zIndeksu(i))}</b>
      </div>
      <div className="sk-rozklad" aria-hidden>
        {Array.from({ length: N + 1 }, (_, k) => (
          <i key={k} data-w={k >= i ? "" : undefined} style={{ height: `${rozklad[k] ? Math.max(8, (Math.sqrt(rozklad[k]) / max) * 100) : 0}%` }} />
        ))}
      </div>
      <div className="sk-tor" ref={tor}>
        <span className="sk-zakres" style={{ left: proc(i), right: 0 }} />
        <span
          ref={uchwyt}
          className="sk-uchwyt"
          role="slider"
          tabIndex={0}
          aria-label="Kurs od"
          aria-valuemin={KURS_MIN}
          aria-valuemax={KURS_MAX}
          aria-valuenow={zIndeksu(i)}
          aria-valuetext={`od ${txt(zIndeksu(i))}`}
          style={{ left: proc(i) }}
          onKeyDown={klawisz}
        />
      </div>
      <div className="sk-skala" aria-hidden>
        {ZNACZNIKI.map((k) => (
          <span key={k} style={{ left: proc(doIndeksu(k)) }}>
            {txt(k)}
          </span>
        ))}
      </div>
    </div>
  );
}
