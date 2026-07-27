/**
 * `npm run stop` — ubija procesy robocze Turbopacka, które zostały po
 * serwerze deweloperskim (patrz scripts/zombie.mjs).
 *
 * Ratunek na wypadek powtórki z 2026-07-27, gdy 1936 takich procesów zjadło
 * 14 GB pamięci. Nie dotyka nic poza nimi: rozpoznaje po linii poleceń,
 * pomija samego siebie.
 */

import { execFileSync } from "node:child_process";

import { mb, znajdzZombie } from "./zombie.mjs";

const zombie = znajdzZombie();

if (zombie.length === 0) {
  console.log("Czysto — żadnych zabłąkanych procesów Turbopacka.");
  process.exit(0);
}

const ram = mb(zombie.reduce((a, z) => a + z.ram, 0));
console.log(`Znaleziono ${zombie.length} procesów (${ram} MB). Ubijam...`);

let ubite = 0;
for (const { pid } of zombie) {
  try {
    process.kill(pid, "SIGKILL");
    ubite += 1;
  } catch {
    // proces mógł już zniknąć sam — to nie błąd
  }
}

// druga tura: przy tysiącach procesów część znika dopiero po chwili
await new Promise((r) => setTimeout(r, 1500));
const zostalo = znajdzZombie();

console.log(`Ubite: ${ubite}. Zostało: ${zostalo.length}.`);
if (zostalo.length > 0) {
  console.log("Zostały uparte — uruchom polecenie jeszcze raz.");
  process.exit(1);
}
