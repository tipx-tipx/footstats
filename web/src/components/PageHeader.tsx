"use client";

import { motion } from "framer-motion";

/** Spójny nagłówek zakładki: eyebrow z kreską marki + tytuł + opis. */
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
  return (
    <motion.header
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="pt-10 sm:pt-12"
    >
      <p className="flex items-center gap-2.5 text-xs font-semibold uppercase tracking-widest text-brand">
        <span aria-hidden className="h-px w-6 bg-brand-bright" />
        {eyebrow}
      </p>
      <h1 className="mt-2.5 text-[2.1rem] font-bold leading-[1.05] tracking-tight sm:text-[2.7rem]">
        {title}
      </h1>
      {lead && (
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted sm:text-[15px]">
          {lead}
        </p>
      )}
      {children}
    </motion.header>
  );
}
