"use client";

import { motion } from "framer-motion";

/* ---- komunikat: tytuł + opis, zawsze z ikoną i kolorem znaczenia ------- */

type Rodzaj = "blad" | "uwaga" | "info" | "ok";

function IkonaKomunikatu({ rodzaj }: { rodzaj: Rodzaj }) {
  return (
    <span className="sy-kom-ikona" aria-hidden>
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        {rodzaj === "ok" ? (
          <path d="M2.5 6.3 5 8.6l4.5-5" />
        ) : rodzaj === "info" ? (
          <path d="M6 5.4V9M6 3v.01" />
        ) : (
          <path d="M6 2.6v4M6 9v.01" />
        )}
      </svg>
    </span>
  );
}

export function Komunikat({ rodzaj, tytul, children, maly = false }: { rodzaj: Rodzaj; tytul: string; children?: React.ReactNode; maly?: boolean }) {
  return (
    <motion.div
      className="sy-kom"
      data-rodzaj={rodzaj}
      data-maly={maly || undefined}
      role={rodzaj === "blad" ? "alert" : "status"}
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="sy-kom-w">
        <IkonaKomunikatu rodzaj={rodzaj} />
        <div>
          <b>{tytul}</b>
          {children && <p>{children}</p>}
        </div>
      </div>
    </motion.div>
  );
}
