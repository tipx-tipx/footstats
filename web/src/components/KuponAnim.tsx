"use client";

/**
 * Wspólne animacje kuponów — te same w generatorze („Zbuduj własny kupon")
 * i w automatycznych na /kupony, żeby całość czytała się jako jeden system.
 * Motyw: kupon się „składa" — kurs dobija do wartości, pasek szansy narasta,
 * legi wpadają jeden po drugim. Wszystko respektuje prefers-reduced-motion.
 */

import { motion, useInView, useReducedMotion, type Variants } from "framer-motion";
import { useEffect, useRef } from "react";

/** Kurs łączny „dobijający" do wartości (rośnie jak przy składaniu kuponu).

 * Płynność: licznik pisze PROSTO do textContent w pętli rAF — bez setState.
 * Wersja ze stanem renderowała React 60×/s na każdą kartę naraz (na /kupony
 * ~9 kart podczas wejścia), co dławiło główny wątek dokładnie w trakcie
 * animacji wejściowych; na ciemnym motywie zacięcia są najbardziej widoczne
 * (wysoki kontrast krawędzi kart), stąd wrażenie "30 fps". */
export function CountUpKurs({
  value,
  className,
  prefix = "×",
}: {
  value: number;
  className?: string;
  prefix?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-20px" });
  const reduced = useReducedMotion();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fmt = (x: number) => `${prefix}${x.toFixed(2).replace(".", ",")}`;
    if (reduced || !inView) {
      el.textContent = fmt(value);
      return;
    }
    const from = Math.max(1, value * 0.55);
    const dur = 750;
    let raf = 0;
    let t0 = 0;
    const tick = (t: number) => {
      if (!t0) t0 = t;
      const p = Math.min(1, (t - t0) / dur);
      const e = 1 - Math.pow(1 - p, 3); // easeOutCubic
      el.textContent = fmt(from + (value - from) * e);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    el.textContent = fmt(from);
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, value, reduced, prefix]);

  return (
    <span ref={ref} className={className}>
      {prefix}
      {value.toFixed(2).replace(".", ",")}
    </span>
  );
}

/** Pasek szansy narastający od 0 do p (0..1) gdy karta wejdzie w kadr.

 * Płynność: animujemy transform (scaleX), NIE width — zmiana szerokości to
 * właściwość LAYOUTU (przeliczenie układu + malowanie w każdej klatce, dla
 * wszystkich kart naraz, w środku układu kolumnowego /kupony), a transform
 * idzie w całości na kompozytorze. Pasek ma stałą szerokość = pct i rośnie
 * skalą od lewej — wygląda identycznie, kosztuje ułamek. */
export function PasekSzansy({
  p,
  className,
}: {
  p: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-20px" });
  const reduced = useReducedMotion();
  const pct = Math.max(0, Math.min(100, Math.round(p * 100)));
  const wypelnij = reduced || inView;
  return (
    <div
      ref={ref}
      className={`h-1.5 w-full overflow-hidden rounded-full bg-ink/10 ${className ?? ""}`}
      role="img"
      aria-label={`szansa ${pct}%`}
    >
      <div
        className="h-full rounded-full bg-gradient-to-r from-brand to-brand-bright transition-transform duration-[900ms] ease-out motion-reduce:transition-none"
        style={{
          width: `${pct}%`,
          transform: wypelnij ? "scaleX(1)" : "scaleX(0)",
          transformOrigin: "left",
        }}
      />
    </div>
  );
}

/** Kontener + element do staggera legów — legi wpadają jeden po drugim. */
export const legiKontener: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06, delayChildren: 0.08 } },
};
export const legWpada: Variants = {
  hidden: { opacity: 0, x: -12 },
  show: { opacity: 1, x: 0, transition: { duration: 0.32, ease: [0.22, 1, 0.36, 1] } },
};

/**
 * Owija listę legów w animowany kontener (stagger). Użyj z <LegWpada> na
 * poszczególnych legach. Respektuje reduced-motion (renderuje bez animacji).
 */
export function LegiStagger({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      variants={legiKontener}
      initial="hidden"
      animate="show"
    >
      {children}
    </motion.div>
  );
}

export function LegWpada({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;
  return (
    <motion.div className={className} variants={legWpada}>
      {children}
    </motion.div>
  );
}
