"use client";

import { motion, useReducedMotion } from "framer-motion";

/** Spójny nagłówek zakładki: eyebrow + tytuł + opis, z wejściem. */
export function PageHeader({
  eyebrow,
  title,
  lead,
  children,
}: {
  eyebrow: string;
  title: string;
  lead?: React.ReactNode;
  children?: React.ReactNode;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.header
      initial={reduced ? false : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="pt-10"
    >
      <p className="text-xs font-semibold uppercase tracking-widest text-brand">
        {eyebrow}
      </p>
      <h1 className="mt-1.5 text-3xl font-bold tracking-tight">{title}</h1>
      {lead && (
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">{lead}</p>
      )}
      {children}
    </motion.header>
  );
}
