"use client";

/**
 * Wspólne animacje kuponów — te same w generatorze („Zbuduj własny kupon")
 * i w automatycznych na /kupony, żeby całość czytała się jako jeden system.
 * Motyw: kupon się „składa" — kurs dobija do wartości, pasek szansy narasta,
 * legi wpadają jeden po drugim. Wszystko respektuje prefers-reduced-motion.
 */

import { motion, useInView, useReducedMotion, type Variants } from "framer-motion";
import { useEffect, useRef, useState } from "react";

/** Kurs łączny „dobijający" do wartości (rośnie jak przy składaniu kuponu). */
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
  const [v, setV] = useState(value);

  useEffect(() => {
    if (reduced || !inView) {
      setV(value);
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
      setV(from + (value - from) * e);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    setV(from);
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, value, reduced]);

  return (
    <span ref={ref} className={className}>
      {prefix}
      {v.toFixed(2).replace(".", ",")}
    </span>
  );
}

/** Pasek szansy narastający od 0 do p (0..1) gdy karta wejdzie w kadr. */
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
      className={`h-1.5 w-full overflow-hidden rounded-full bg-paper ${className ?? ""}`}
      role="img"
      aria-label={`szansa ${pct}%`}
    >
      <div
        className="h-full rounded-full bg-gradient-to-r from-brand to-data-green transition-[width] duration-[900ms] ease-out motion-reduce:transition-none"
        style={{ width: wypelnij ? `${pct}%` : "0%" }}
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
