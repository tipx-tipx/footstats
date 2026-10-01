"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";

import "../../systemowe.css";

/*
 * Brak internetu (S.4, zatwierdzony pasek): osobny lekki plik, bo szkielet
 * aplikacji ładuje go na każdej stronie.
 */

export function IkonaBezSieci() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden>
      <path d="M1.5 6a9.5 9.5 0 0 1 13 0M4 8.6a6 6 0 0 1 8 0M6.4 11.1a2.6 2.6 0 0 1 3.2 0" opacity="0.45" />
      <circle cx="8" cy="13.3" r="0.9" fill="currentColor" stroke="none" />
      <path d="M2.5 2.5l11 11" />
    </svg>
  );
}

export function usePolaczenie() {
  // „wrócił” trzyma się 3 s, potem pasek znika
  const [stan, setStan] = useState<"jest" | "brak" | "wrocil">("jest");
  useEffect(() => {
    let t: ReturnType<typeof setTimeout> | undefined;
    const off = () => {
      clearTimeout(t);
      setStan("brak");
    };
    const on = () => {
      setStan("wrocil");
      t = setTimeout(() => setStan("jest"), 3000);
    };
    if (!navigator.onLine) off();
    window.addEventListener("offline", off);
    window.addEventListener("online", on);
    return () => {
      clearTimeout(t);
      window.removeEventListener("offline", off);
      window.removeEventListener("online", on);
    };
  }, []);
  return stan;
}

export function PasekPolaczenia({ stan, godz }: { stan: "jest" | "brak" | "wrocil"; godz: string }) {
  return (
    <AnimatePresence mode="wait" initial={false}>
      {stan === "wrocil" ? (
        <motion.div key="on" className="ap-baner" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
          <div className="sy-pasek" data-online role="status">
            <span className="sy-pasek-ikona" aria-hidden>
              <svg width="14" height="14" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M2.5 6.3 5 8.6l4.5-5" />
              </svg>
            </span>
            <span>
              <b>Znowu online.</b> Typy i kursy odświeżone.
            </span>
          </div>
        </motion.div>
      ) : stan === "brak" ? (
        <motion.div key="off" className="ap-baner" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
          <div className="sy-pasek" role="status">
            <span className="sy-pasek-ikona" aria-hidden>
              <IkonaBezSieci />
            </span>
            <span>
              <b>Brak internetu.</b> Widzisz typy i kursy z {godz} – odświeżymy je sami, gdy wróci zasięg.
            </span>
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
