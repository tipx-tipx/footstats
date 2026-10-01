"use client";

import { MotionConfig } from "framer-motion";
import { useState } from "react";

import "../../atomy.css";
import "../../atomy2.css";
import "../../elementy.css";
import "../../kupony.css";
import "../../kupony2.css";

import type { LegPool } from "@/lib/types";

import type { DruzynaV } from "../../_dane/przygotuj";
import { Kreator, type StartKreatora } from "./Kreator";
import { KreatorV2 } from "./KreatorV2";

type Motyw = "ciemny" | "jasny";
const PALETA: Record<Motyw, string> = { ciemny: "b1", jasny: "p3" };

export function StronaKuponow({ pula, herby, start }: { pula: LegPool[]; herby: Record<string, DruzynaV>; start: StartKreatora }) {
  const [motyw, setMotyw] = useState<Motyw>(start.m === "jasny" ? "jasny" : "ciemny");
  const [szer, setSzer] = useState<"pelna" | "telefon">(start.s === "telefon" ? "telefon" : "pelna");
  const [wersja, setWersja] = useState<"2" | "1">(start.v === "1" ? "1" : "2");
  const telefon = szer === "telefon";

  const ekran = (
    <div className="p-ekran" data-p-motyw={motyw} data-p-paleta={PALETA[motyw]} data-p-font="2c">
      <div className="p-tresc" style={{ maxWidth: 760 }}>
        {wersja === "2" ? (
          <KreatorV2 pula={pula} herby={herby} telefon={telefon} start={start} />
        ) : (
          <Kreator pula={pula} herby={herby} telefon={telefon} start={start} />
        )}
      </div>
    </div>
  );

  return (
    <MotionConfig reducedMotion="user">
      <div className="p-pulpit">
        <div className="p-pulpit-wnetrze">
          <div className="p-pulpit-tytul">
            Etap 3.6 <span>· strona Kupony</span>
          </div>
          <div className="p-wybor">
            <span>wersja</span>
            <div className="p-segmenty" role="group">
              {(["2", "1"] as const).map((v) => (
                <button key={v} type="button" aria-pressed={wersja === v} onClick={() => setWersja(v)}>
                  {v === "2" ? "Nowa (v2)" : "Pierwsza"}
                </button>
              ))}
            </div>
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
        <div className="p-pulpit-opis">
          Wszystko działa na prawdziwej puli typów (migawka 30.09). Kupon siedzi w krótkim linku (Udostępnij → Kopiuj link).
        </div>
      </div>
      {telefon ? <div className="p-rama-telefon">{ekran}</div> : ekran}
    </MotionConfig>
  );
}
