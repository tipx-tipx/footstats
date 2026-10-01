"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Rząd przewijany w bok (rynki, dni). Na telefonie przesuwa się palcem, ale
 * na komputerze ukryty pasek przewijania = rząd „zablokowany” (zgłoszenie
 * właściciela 30.09: nie dało się dojść do „Rzuty rożne w meczu”). Dlatego:
 *  - kółko myszy przewija w bok, gdy kursor jest nad rzędem,
 *  - strzałki przy krawędziach (tylko przy myszy), jak u Superbetu,
 *  - wygaszenie krawędzi tylko tam, gdzie coś jeszcze jest,
 *  - wybrany element sam wjeżdża w pole widzenia (robią to rodzice).
 */
export function PrzewijanyRzad({
  className,
  children,
  role,
  ariaLabel,
}: {
  className: string;
  children: ReactNode;
  role?: string;
  ariaLabel?: string;
}) {
  const rzad = useRef<HTMLDivElement>(null);
  const [lewo, setLewo] = useState(false);
  const [prawo, setPrawo] = useState(false);

  useEffect(() => {
    const el = rzad.current;
    if (!el) return;
    const zmierz = () => {
      setLewo(el.scrollLeft > 2);
      setPrawo(el.scrollLeft + el.clientWidth < el.scrollWidth - 2);
    };
    const kolko = (e: WheelEvent) => {
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) return; // gładzik już przewija w bok
      if (el.scrollWidth <= el.clientWidth) return;
      const koniec = e.deltaY > 0 ? el.scrollLeft + el.clientWidth >= el.scrollWidth - 1 : el.scrollLeft <= 0;
      if (koniec) return; // na końcu rzędu oddajemy kółko stronie
      e.preventDefault();
      el.scrollLeft += e.deltaY;
    };
    const obserwator = new ResizeObserver(zmierz);
    obserwator.observe(el);
    el.addEventListener("scroll", zmierz, { passive: true });
    el.addEventListener("wheel", kolko, { passive: false });
    return () => {
      obserwator.disconnect();
      el.removeEventListener("scroll", zmierz);
      el.removeEventListener("wheel", kolko);
    };
  }, []);

  const przesun = (kier: 1 | -1) => {
    const el = rzad.current;
    if (el) el.scrollBy({ left: kier * el.clientWidth * 0.7, behavior: "smooth" });
  };

  return (
    <div className="g-rama">
      <div ref={rzad} className={`${className} g-rzad`} data-lewo={lewo || undefined} data-prawo={prawo || undefined} role={role} aria-label={ariaLabel}>
        {children}
      </div>
      {lewo && (
        <button type="button" className="g-strzalka" data-strona="lewo" aria-label="Przewiń w lewo" tabIndex={-1} onClick={() => przesun(-1)}>
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
            <path d="M7.5 2.5 4 6l3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}
      {prawo && (
        <button type="button" className="g-strzalka" data-strona="prawo" aria-label="Przewiń w prawo" tabIndex={-1} onClick={() => przesun(1)}>
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
            <path d="M4.5 2.5 8 6 4.5 9.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}
    </div>
  );
}
