import { StronaAplikacji } from "@/app/projekt/_ui/aplikacja/Strona";
import { druzyna, type DruzynaV } from "@/app/projekt/_dane/przygotuj";
import { przygotujHistorieKuponow } from "@/app/projekt/_dane/kuponyHistoria";
import { przygotujStrony } from "@/app/projekt/_dane/strony";
import { zDanymi } from "@/app/projekt/_dane/zrodlo";
import type { LegPool } from "@/lib/types";
import { pobierzSurowe } from "@/lib/nowe/surowe";
import { czyTelefon } from "@/lib/nowe/telefon";

export const metadata = { title: "Kupony – FootStats" };

/**
 * Kupony (redesign, etap 7.3; 3.6 v3 zatwierdzone 01.10): jeden kupon do
 * edycji, „Ile chcesz wygrać?”, zamiana najsłabszego ogniwa, kupon z meczu,
 * kupon w linku (`?k=`), karta do udostępnienia. Pod kreatorem – kupony od
 * modelu i jak wyszły (historia z `typy_wyniki.kupony`, bilans z całości).
 */
export default async function KuponyPage({ searchParams }: { searchParams: Promise<{ k?: string }> }) {
  const [surowe, telefon, { k }] = await Promise.all([pobierzSurowe(), czyTelefon(), searchParams]);
  const pula = surowe.legiPool as LegPool[];
  const [dane, herby, historia] = zDanymi(surowe, () => {
    const h: Record<string, DruzynaV> = {};
    for (const l of pula) for (const n of [l.druzyna, l.podmiot_typ === "druzyna" ? l.podmiot : null]) if (n && !h[n]) h[n] = druzyna(n);
    return [przygotujStrony(), h, przygotujHistorieKuponow()] as const;
  });
  return <StronaAplikacji strona="kupony" dane={dane} kupony={{ pula, herby, k, historia }} teraz={surowe.teraz} telefon={telefon} />;
}
