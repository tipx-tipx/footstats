import type { NextConfig } from "next";

/**
 * ROZDZIELONE KATALOGI BUILDU (incydent 2026-07-27).
 *
 * Serwer deweloperski (`next dev`) obserwuje katalog projektu, a produkcyjny
 * `next build` wsypuje do `.next` ~350 MB plików. Gdy oba celują w ten sam
 * katalog i chodzą jednocześnie, dev widzi lawinę zdarzeń z systemu plików
 * i przy każdym z nich odpala na nowo PostCSS — a Turbopack liczy PostCSS
 * w OSOBNYM procesie node (`.next/dev/build/*.js` → `[turbopack-node]/
 * child_process/evaluate.ts`). Zmierzone tego dnia: 1936 procesów node,
 * 14 GB RAM, wszystkie na jednym pliku CSS (projekt ma dokładnie jeden).
 *
 * `next build` pisze więc teraz do `.next-build`, a dev zostaje przy `.next`.
 * Nie ma wspólnego katalogu, nie ma lawiny zdarzeń, nie ma rozmnażania.
 */
const nextConfig: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
};

export default nextConfig;
