import type { LegPool } from "@/lib/types";

import { druzyna, type DruzynaV } from "../_dane/przygotuj";
import pulaRaw from "../_dane/legi_pool.json";
import { StronaKuponow } from "../_ui/kupony/StronaKuponow";
import type { StartKreatora } from "../_ui/kupony/Kreator";

export default async function KuponyPage({ searchParams }: { searchParams: Promise<StartKreatora> }) {
  const pula = pulaRaw as unknown as LegPool[];
  const herby: Record<string, DruzynaV> = {};
  for (const l of pula) {
    for (const n of [l.druzyna, l.podmiot_typ === "druzyna" ? l.podmiot : null]) {
      if (n && !herby[n]) herby[n] = druzyna(n);
    }
  }
  return <StronaKuponow pula={pula} herby={herby} start={await searchParams} />;
}
