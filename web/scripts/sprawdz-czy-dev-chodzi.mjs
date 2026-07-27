/**
 * `prebuild` — odpala się SAM przed `npm run build`.
 *
 * Blokuje build, gdy w tle chodzi serwer deweloperski. Oba pisałyby wtedy do
 * tego samego katalogu `.next`, a to jest najbardziej prawdopodobna przyczyna
 * incydentu z 2026-07-27 (1936 procesów node, 14 GB RAM — patrz
 * scripts/zombie.mjs). Wyjście z błędem jest tu CELOWO ostre: cichy warning
 * przy budowie, która trwa minutę, i tak zostałby przewinięty.
 *
 * W chmurze (Vercel, GitHub Actions) żaden dev nie chodzi, więc skrypt
 * przepuszcza build bez słowa. Na systemach innych niż Windows nie umie
 * sprawdzić i też przepuszcza — nie blokujemy na podstawie niewiedzy.
 *
 * Awaryjne obejście: FOOTSTATS_POMIN_KONTROLE=1 npm run build
 */

import { mb, znajdzZombie } from "./zombie.mjs";

if (process.env.CI || process.env.VERCEL || process.env.FOOTSTATS_POMIN_KONTROLE) {
  process.exit(0);
}

const zombie = znajdzZombie();
if (zombie.length === 0) process.exit(0);

const ram = mb(zombie.reduce((a, z) => a + z.ram, 0));

console.error(`
╭─ BUILD ZATRZYMANY ─────────────────────────────────────────────╮

  W tle chodzi serwer deweloperski (${zombie.length} procesów, ${ram} MB).

  Build i dev pisałyby do tego samego katalogu .next. Dev widzi wtedy
  lawinę zmian plików i przy każdej odpala PostCSS w nowym procesie —
  27.07.2026 skończyło się to 1936 procesami i 14 GB zajętej pamięci.

  Zrób jedno z trzech:
    1. zatrzymaj dev (Ctrl+C w jego oknie), potem  npm run build
    2. albo zbuduj obok, do osobnego katalogu:     npm run build:obok
    3. albo posprzątaj zabłąkane procesy:          npm run stop

╰────────────────────────────────────────────────────────────────╯
`);
process.exit(1);
