import { PageHeader } from "@/components/PageHeader";
import { TerminarzMeczy } from "@/components/TerminarzMeczy";
import { getMecze, getValueBets, terazTs } from "@/lib/data";

export const metadata = { title: "Mecze – FootStats" };

export default async function MeczePage() {
  const [mecze, bets] = await Promise.all([getMecze(), getValueBets()]);

  // liczniki per mecz (rekordy — serializowalne do komponentu klienckiego)
  const okazje: Record<number, number> = {};
  const sugestie: Record<number, number> = {};
  const najlepsze: Record<number, number> = {};
  for (const b of bets) {
    if (b.sugestia) {
      sugestie[b.mecz_id] = (sugestie[b.mecz_id] ?? 0) + 1;
      continue;
    }
    okazje[b.mecz_id] = (okazje[b.mecz_id] ?? 0) + 1;
    if (b.ev_pct != null && (najlepsze[b.mecz_id] ?? 0) < b.ev_pct)
      najlepsze[b.mecz_id] = b.ev_pct;
  }

  return (
    <div>
      <PageHeader
        eyebrow="terminarz skanu"
        title="Mecze w analizie"
        lead="Rozkład najbliższych meczów, które model już przeskanował. Wejdź w mecz, a zobaczysz zawodników z najlepszym pokryciem linii i wszystkie okazje."
      />
      <TerminarzMeczy
        mecze={mecze}
        okazje={okazje}
        sugestie={sugestie}
        najlepsze={najlepsze}
        teraz={terazTs()}
      />
    </div>
  );
}
