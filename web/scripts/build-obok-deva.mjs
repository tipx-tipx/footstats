/**
 * `npm run build:obok` — build do OSOBNEGO katalogu, bezpieczny przy
 * chodzącym serwerze deweloperskim.
 *
 * Ustawia NEXT_DIST_DIR (czyta go next.config.ts), więc `next build` pisze do
 * `.next-build` zamiast do `.next`. Dev zostaje przy swoim katalogu i nie
 * dostaje lawiny zdarzeń z systemu plików — czyli znika przyczyna incydentu
 * z 2026-07-27 (patrz scripts/zombie.mjs).
 *
 * Do sprawdzania „czy się kompiluje". Deploy idzie normalnym `npm run build`,
 * którego zachowania celowo nie ruszamy — Vercel ma dostać dokładnie to samo
 * co dotąd.
 */

import { spawn } from "node:child_process";

const proc = spawn("npx", ["next", "build"], {
  stdio: "inherit",
  shell: process.platform === "win32",
  env: {
    ...process.env,
    NEXT_DIST_DIR: ".next-build",
    // prebuild i tak się tu nie odpali (to nie jest skrypt `build`),
    // ale gdyby ktoś kiedyś przepiął — nie ma czego blokować
    FOOTSTATS_POMIN_KONTROLE: "1",
  },
});

proc.on("exit", (kod) => process.exit(kod ?? 1));
