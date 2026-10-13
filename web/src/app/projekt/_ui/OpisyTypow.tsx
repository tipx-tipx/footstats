"use client";

import { MotionConfig } from "framer-motion";
import { useState } from "react";

import "../atomy.css";
import "../atomy2.css";
import "../elementy.css";

import type { Powod } from "../_dane/elementy";
import { fmtKurs } from "@/lib/format";
import { Powody } from "./elementy/karta";

export type PorownanieOpisu = {
  klucz: string;
  kto: string;
  druzynowy: boolean;
  zaklad: string;
  kurs: number;
  szansa: number;
  stary: Powod[];
  nowy: Powod[];
  maNowy: boolean;
};

type Motyw = "ciemny" | "jasny";
const PALETA: Record<Motyw, string> = { ciemny: "b1", jasny: "p3" };

export function OpisyTypow({ lista }: { lista: PorownanieOpisu[] }) {
  const [motyw, setMotyw] = useState<Motyw>("ciemny");
  const zNowym = lista.filter((x) => x.maNowy).length;
  return (
    <MotionConfig reducedMotion="user">
      <div className="p-pulpit">
        <div className="p-pulpit-wnetrze">
          <div className="p-pulpit-tytul">
            Opisy typów <span>· stary silnik obok modelu</span>
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
        </div>
        <div className="p-pulpit-opis">
          Typy z produkcji liczone modelem: {lista.length}, z nowym opisem: {zNowym}. Lewa kolumna – to, co karta pokazuje dziś (czynniki
          starego silnika), prawa – składniki liczby modelu (forma, gdzie gra, rywal, liga, styl, linia w historii).
        </div>
      </div>
      <div className="p-ekran" data-p-motyw={motyw} data-p-paleta={PALETA[motyw]} data-p-font="2c">
        <div className="p-tresc" style={{ maxWidth: 1040, display: "grid", gap: 12 }}>
          {lista.map((x) => (
            <article key={x.klucz} className="el-karta" style={{ padding: "14px 16px", display: "grid", gap: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
                <div>
                  <h3 className="el-kto" style={{ fontSize: 17 }}>
                    {x.kto}
                  </h3>
                  <div className="el-kto-pod">{x.zaklad}</div>
                </div>
                <div style={{ fontSize: 13, color: "var(--t2)", whiteSpace: "nowrap" }}>
                  {Math.round(x.szansa * 100)}% · kurs {fmtKurs(x.kurs)}
                </div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 320px), 1fr))", gap: 16 }}>
                <div>
                  <small style={{ display: "block", color: "var(--t3)", marginBottom: 6 }}>Dziś – stary silnik</small>
                  {x.stary.length ? <Powody powody={x.stary} /> : <small style={{ color: "var(--t3)" }}>brak</small>}
                </div>
                <div>
                  <small style={{ display: "block", color: "var(--t3)", marginBottom: 6 }}>Nowy – model</small>
                  {x.nowy.length ? (
                    <Powody powody={x.nowy} />
                  ) : (
                    <small style={{ color: "var(--t3)" }}>{x.maNowy ? "brak czynników ponad 3%" : "czeka na cykl z nowym opisem"}</small>
                  )}
                </div>
              </div>
            </article>
          ))}
        </div>
      </div>
    </MotionConfig>
  );
}
