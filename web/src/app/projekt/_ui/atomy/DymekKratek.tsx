"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/*
 * Dymek nad kratką pokrycia – strona meczu i strona zawodnika (01.11,
 * właściciel: „po najechaniu niech będzie pokazany, jaki to jest mecz, bo
 * teraz trzeba czekać”). Natywny `title` przeglądarka pokazuje dopiero po
 * ~1 s; ten – od razu po najechaniu myszką albo dotknięciu na telefonie.
 *
 * Przez portal do `body` (`position: fixed`): tabela meczu ma
 * `overflow: hidden`, dymek w jej środku ucinałby się przy ostatnim wierszu.
 *
 * Kratka niesie treść w `data-mecz` (pierwsza linia) i `data-wynik` (druga);
 * zdarzenia łapie kontener – jeden słuchacz na cały rząd kratek.
 */

type Stan = { mecz: string; wynik: string; x: number; y: number; dol: boolean };

/** połowa szerokiego dymka – trzyma go w oknie przy brzegu ekranu */
const POL_SZER = 110;
/** tyle stoi dymek po dotknięciu (telefon nie ma „zjechania” z kratki) */
const DOTYK_MS = 2500;

export function useDymekKratek() {
  const [d, setD] = useState<Stan | null>(null);
  const zegar = useRef<number | undefined>(undefined);

  // dymek stoi w miejscu ekranu – przewinięcie albo zmiana okna go chowa
  useEffect(() => {
    if (!d) return;
    const schowaj = () => setD(null);
    window.addEventListener("scroll", schowaj, { capture: true, passive: true });
    window.addEventListener("resize", schowaj);
    return () => {
      window.removeEventListener("scroll", schowaj, { capture: true });
      window.removeEventListener("resize", schowaj);
    };
  }, [d]);
  useEffect(() => () => window.clearTimeout(zegar.current), []);

  const pokaz = (e: React.PointerEvent<HTMLElement>) => {
    const k = (e.target as Element).closest<HTMLElement>("[data-mecz]");
    if (!k || !e.currentTarget.contains(k)) return;
    window.clearTimeout(zegar.current);
    const r = k.getBoundingClientRect();
    const dol = r.top < 64; // przy górnej krawędzi – pod kratką
    const x = Math.min(Math.max(r.left + r.width / 2, POL_SZER + 8), window.innerWidth - POL_SZER - 8);
    setD({ mecz: k.dataset.mecz ?? "", wynik: k.dataset.wynik ?? "", x, y: dol ? r.bottom + 6 : r.top - 6, dol });
    if (e.pointerType !== "mouse") zegar.current = window.setTimeout(() => setD(null), DOTYK_MS);
  };
  const ukryj = (e: React.PointerEvent<HTMLElement>) => {
    if (e.pointerType === "mouse") setD(null);
  };

  const dymek = d
    ? createPortal(
        <span className="kr-dymek" role="tooltip" data-dol={d.dol || undefined} style={{ left: d.x, top: d.y }}>
          <b>{d.mecz}</b>
          {d.wynik && <span>{d.wynik}</span>}
        </span>,
        document.body,
      )
    : null;
  return { zdarzenia: { onPointerOver: pokaz, onPointerLeave: ukryj }, dymek };
}

/** treść dymka jednej kratki: „vs Sporting · 25.10” / „2 · 90 min” albo „nie zagrał” */
export function opisKratki(m: { v: number; min: number; rywal: string; data: string }) {
  return {
    "data-mecz": [m.rywal && `vs ${m.rywal}`, m.data].filter(Boolean).join(" · ") || "mecz",
    "data-wynik": m.min > 0 ? `${m.v} · ${m.min} min` : "nie zagrał",
  };
}
