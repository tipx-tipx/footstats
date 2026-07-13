/**
 * Most testu parytetu Python<->TS beam-searcha kuponów (pipeline/tests/
 * test_kupony_parytet.py). Czyta ze stdin JSON {pool, cmin, cmax, opts},
 * woła TĘ SAMĄ funkcję co GeneratorKuponu (zlozKupon), drukuje wynik jako
 * JSON na stdout. Uruchamiane z katalogu web/ (`node scripts/kupony_parity_bridge.ts`)
 * — Node >=23.6 uruchamia .ts bezpośrednio (natywne strip-typing), zero builda.
 * Rozszerzenia .ts w imporcie są WYMAGANE przez rezolucję ESM Node (inaczej
 * "module not found"), ale niedozwolone przez tsconfig bundlera Next.js —
 * dlatego scripts/ jest w tsconfig.json:exclude (poza type-checkiem appki).
 */
import { zlozKupon, type Kary, type Profil } from "../src/lib/kuponBuilder.ts";
import type { LegPool } from "../src/lib/types.ts";

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks).toString("utf-8");
}

async function main() {
  const raw = await readStdin();
  const input = JSON.parse(raw) as {
    pool: LegPool[];
    cmin: number;
    cmax: number;
    opts?: {
      profil?: Profil;
      minLegi?: number;
      maxLegi?: number;
      maxNaMecz?: number;
      kary?: Kary;
    };
  };
  const wynik = zlozKupon(input.pool, input.cmin, input.cmax, input.opts ?? {});
  process.stdout.write(JSON.stringify(wynik));
}

main();
