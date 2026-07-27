/**
 * Wspólne rozpoznawanie „procesów-zombi" po incydencie 2026-07-27.
 *
 * Co się stało: Turbopack liczy PostCSS w OSOBNYM procesie node (pliki
 * `.next/dev/build/*.js`, wejście `[turbopack-node]/child_process/evaluate.ts`).
 * Normalnie takich procesów jest kilka. Tamtego dnia było ich 1936 na 14 GB
 * RAM — przy projekcie, który ma DOKŁADNIE JEDEN plik CSS. Wszystkie ruszyły
 * w cztery sekundy i żaden nie zużył ani sekundy procesora, czyli powstały
 * i nigdy nie dostały pracy ani nie zostały posprzątane.
 *
 * Najbardziej prawdopodobna przyczyna: `next build` wsypał ~350 MB do `.next`,
 * który w tym samym czasie obserwował chodzący `next dev`. Lawina zdarzeń
 * z systemu plików = lawina przeliczeń CSS = lawina procesów.
 */

import { execFileSync } from "node:child_process";

/** Sygnatura procesu roboczego Turbopacka (ta sama na dev i na buildzie). */
const SYGNATURA = /[\\/]\.next[^\\/]*[\\/]dev[\\/]build[\\/]/;

/**
 * Procesy node uruchomione z katalogu roboczego Turbopacka.
 * Zwraca [] na systemach innych niż Windows albo gdy nie da się odpytać.
 */
export function znajdzZombie() {
  if (process.platform !== "win32") return [];
  try {
    // Get-CimInstance zamiast tasklist: potrzebujemy linii poleceń, żeby
    // odróżnić workera Turbopacka od zwykłego node (w tym od nas samych)
    const out = execFileSync(
      "powershell.exe",
      [
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | " +
          "Select-Object ProcessId, CommandLine, WorkingSetSize | ConvertTo-Json -Compress",
      ],
      { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 },
    ).trim();
    if (!out) return [];
    const surowe = JSON.parse(out);
    const lista = Array.isArray(surowe) ? surowe : [surowe];
    return lista
      .filter((p) => p?.CommandLine && SYGNATURA.test(p.CommandLine))
      .filter((p) => p.ProcessId !== process.pid)
      .map((p) => ({ pid: p.ProcessId, ram: Number(p.WorkingSetSize) || 0 }));
  } catch {
    return [];
  }
}

export function mb(bajty) {
  return Math.round(bajty / 1024 / 1024);
}
