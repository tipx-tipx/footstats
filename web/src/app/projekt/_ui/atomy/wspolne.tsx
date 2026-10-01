"use client";

import type { ReactNode } from "react";

export type WariantAtomu = { id: string; nazwa: string; opis: string };

/**
 * Jedna sekcja warsztatu: numer, tytuł, po co ten element, przełącznik
 * wariantów i opis wybranego wariantu (skąd pomysł, kiedy się sprawdza).
 */
export function Sekcja({
  nr,
  tytul,
  opis,
  warianty,
  wybrany,
  zmien,
  children,
}: {
  nr: string;
  tytul: string;
  opis: string;
  warianty: WariantAtomu[];
  wybrany: string;
  zmien: (id: string) => void;
  children: ReactNode;
}) {
  const w = warianty.find((x) => x.id === wybrany) ?? warianty[0];
  return (
    <section className="a-sekcja" id={`atom-${nr}`}>
      <div className="a-sekcja-glowa">
        <div>
          <h2 className="p-n">
            <span>{nr}</span>
            {tytul}
          </h2>
          <p className="a-opis">{opis}</p>
        </div>
        {warianty.length > 1 && (
          <div className="a-warianty" role="group" aria-label={`Warianty: ${tytul}`}>
            {warianty.map((x) => (
              <button key={x.id} type="button" aria-pressed={x.id === w.id} onClick={() => zmien(x.id)}>
                {x.nazwa}
              </button>
            ))}
          </div>
        )}
      </div>
      <p className="a-wariant-opis">
        <b>{w.nazwa}</b> – {w.opis}
      </p>
      {children}
    </section>
  );
}

/* ---- bukmacherzy -------------------------------------------------------- */

const LOGA: Record<string, { src: string; proporcja: number; skala: number; kolor: string }> = {
  // optyczna równość: Superbet to sam napis, Betclic napis w prostokącie
  Superbet: { src: "/bukmacherzy/superbet.png", proporcja: 271 / 48, skala: 0.72, kolor: "#e2001a" },
  Betclic: { src: "/bukmacherzy/betclic.png", proporcja: 142 / 48, skala: 1, kolor: "#e4002b" },
};

export function LogoBuk({ nazwa, wysokosc = 12 }: { nazwa: string; wysokosc?: number }) {
  const l = LOGA[nazwa];
  if (!l) return <span style={{ fontSize: 11, color: "var(--t3)" }}>{nazwa}</span>;
  const h = Math.round(wysokosc * l.skala * 10) / 10;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img className="a-logo-buk" src={l.src} alt={nazwa} width={Math.round(h * l.proporcja)} height={h} />
  );
}

/** znak bukmachera do pigułek: pierwsza litera na kolorze marki – oba są
 *  czerwone, więc rozróżnia je litera, nigdy sam kolor */
export function ZnakBuk({ nazwa }: { nazwa: string }) {
  const l = LOGA[nazwa];
  return (
    <span className="a-znak-buk" style={{ background: l?.kolor ?? "var(--pow3)" }} aria-label={nazwa} title={nazwa}>
      {nazwa[0]}
    </span>
  );
}

export function Ptaszek({ rozmiar = 10 }: { rozmiar?: number }) {
  return (
    <svg width={rozmiar} height={rozmiar} viewBox="0 0 12 12" aria-hidden>
      <path d="M2.5 6.5 5 9l4.5-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Krzyzyk({ rozmiar = 10 }: { rozmiar?: number }) {
  return (
    <svg width={rozmiar} height={rozmiar} viewBox="0 0 12 12" aria-hidden>
      <path d="m3 3 6 6M9 3 3 9" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function Zwrot({ rozmiar = 11 }: { rozmiar?: number }) {
  return (
    <svg width={rozmiar} height={rozmiar} viewBox="0 0 12 12" aria-hidden>
      <path
        d="M9.5 6A3.5 3.5 0 1 1 8.4 3.5M9.5 1.8v2.4H7.1"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Zegar({ rozmiar = 11 }: { rozmiar?: number }) {
  return (
    <svg width={rozmiar} height={rozmiar} viewBox="0 0 12 12" aria-hidden>
      <circle cx="6" cy="6" r="4.3" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M6 3.8V6l1.5 1" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export const procent = (p: number) => `${Math.round(p * 100)}%`;
