"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";

import { fmtLinia } from "@/lib/format";

import type { TypV } from "../../_dane/przygotuj";
import { KafelekD, KratkiD } from "./podstawowe";
import { SzkieletWiersza } from "./SzkieletWiersza";

export { SzkieletWiersza };

/* ======================================================================
   2.9 SZKIELET – dokładnie w kształcie wiersza, jedna fala połysku
   ====================================================================== */

function WierszTypu({ t }: { t: TypV }) {
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div className="a-typ" style={{ padding: 0 }}>
        <div style={{ minWidth: 0 }}>
          <div className="a-typ-kto">{t.kto}</div>
          <div className="a-typ-co">
            {t.rynek.toLowerCase()} {t.strona === "ponizej" ? "poniżej" : "powyżej"} {fmtLinia(t.linia)}
          </div>
        </div>
        <KafelekD k={{ kurs: t.kurs, bukmacher: t.bukmacher }} />
      </div>
      <KratkiD t={t} />
    </div>
  );
}

export function SzkieletD({ typy }: { typy: TypV[] }) {
  const [laduje, setLaduje] = useState(true);
  const [widacSzkielet, setWidacSzkielet] = useState(false);

  // szkielet dopiero po 300 ms: szybkie wczytanie nie mruga szarymi paskami
  useEffect(() => {
    if (!laduje) return;
    const t = setTimeout(() => setWidacSzkielet(true), 300);
    return () => {
      clearTimeout(t);
      setWidacSzkielet(false);
    };
  }, [laduje]);

  return (
    <div className="a-scena">
      <div style={{ display: "grid", gap: 22, maxWidth: 440 }}>
        {typy.slice(0, 2).map((t) =>
          laduje ? (
            widacSzkielet ? <SzkieletWiersza key={t.id} /> : <div key={t.id} style={{ height: 150 }} />
          ) : (
            <motion.div key={t.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }}>
              <WierszTypu t={t} />
            </motion.div>
          ),
        )}
      </div>
      <button type="button" className="a-demo-guzik" onClick={() => setLaduje((l) => !l)}>
        {laduje ? "Pokaż gotowe" : "Pokaż ładowanie"}
      </button>
    </div>
  );
}

/* ======================================================================
   2.10 PRZYCISKI I PUSTY STAN – dopracowane
   ====================================================================== */

export function PrzyciskiD() {
  const [zapis, setZapis] = useState(false);
  useEffect(() => {
    if (!zapis) return;
    const t = setTimeout(() => setZapis(false), 1600);
    return () => clearTimeout(t);
  }, [zapis]);

  return (
    <>
      <div className="a-scena">
        <div className="a-podpis">rodzaje – przejdź klawiszem Tab, żeby zobaczyć obwódkę fokusu</div>
        <div className="a-rzad">
          <button type="button" className="a-guzik" data-t="glowny" data-r="m">
            Dodaj do kuponu <span className="d-meta">3 typy · ×2,11</span>
          </button>
          <button type="button" className="a-guzik" data-t="drugi" data-r="m">
            Skąd ta liczba
          </button>
          <button type="button" className="a-guzik" data-t="cichy" data-r="m">
            Wszystkie typy <span className="d-strzalka">→</span>
          </button>
          <button type="button" className="a-guzik" data-t="ikona" aria-label="Ulubione">
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
              <path d="m8 2 1.8 3.8 4.2.5-3.1 2.9.8 4.1L8 11.3l-3.7 2 .8-4.1L2 6.3l4.2-.5Z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>
      <div className="a-scena">
        <div className="a-podpis">stany – kliknij „Zapisz kupon”</div>
        <div className="a-rzad">
          <button
            type="button"
            className="a-guzik"
            data-t="glowny"
            data-r="m"
            style={{ minWidth: 150 }}
            aria-busy={zapis}
            onClick={() => setZapis(true)}
          >
            <AnimatePresence mode="popLayout" initial={false}>
              {zapis ? (
                <motion.span key="k" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
                  <span className="d-krecik" aria-hidden /> Zapisuję
                </motion.span>
              ) : (
                <motion.span key="t" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                  Zapisz kupon
                </motion.span>
              )}
            </AnimatePresence>
          </button>
          <button type="button" className="a-guzik" data-t="glowny" data-r="m" disabled>
            Wyłączony
          </button>
          <button type="button" className="a-guzik" data-t="drugi" data-r="m" disabled>
            Wyłączony
          </button>
        </div>
      </div>
      <div className="a-scena">
        <div className="a-podpis">rozmiary: 32 (gęste listy na komputerze) · 40 (standard) · 48 (główna akcja na telefonie)</div>
        <div className="a-rzad">
          <button type="button" className="a-guzik" data-t="glowny" data-r="s">
            32 px
          </button>
          <button type="button" className="a-guzik" data-t="glowny" data-r="m">
            40 px
          </button>
          <button type="button" className="a-guzik" data-t="glowny" data-r="l">
            48 px
          </button>
        </div>
      </div>
      <div className="a-scena">
        <div className="a-podpis">pusty stan – co się stało, dlaczego, co zrobić</div>
        <div className="d-pusty">
          <div className="p-n" style={{ fontSize: 18 }}>
            Na jutro jeszcze nic
          </div>
          <p>Bukmacherzy wystawiają kursy na jutrzejsze mecze zwykle po 18:00. Wtedy model je przeliczy i dopisze typy.</p>
          <button type="button" className="a-guzik" data-t="drugi" data-r="m" style={{ marginTop: 6 }}>
            Zobacz piątek · 17 meczów <span className="d-strzalka">→</span>
          </button>
        </div>
      </div>
    </>
  );
}
