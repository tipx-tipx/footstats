import { BetTracker } from "@/components/BetTracker";
import { MojeKupony } from "@/components/MojeKupony";
import { PageHeader } from "@/components/PageHeader";
import { getTypyWyniki } from "@/lib/data";

export const metadata = { title: "Moje zakłady – FootStats" };

export default async function ZakladyPage() {
  // historia kuponów z pipeline'u – zagrane kupony rozliczają się z niej
  // same (po kluczu), bez ręcznego ustawiania wyniku
  const typy = await getTypyWyniki();
  const historia = [
    ...(typy.kupony ?? []),
    ...(typy.kupony_wygrane ?? []),
  ];

  return (
    <div>
      <PageHeader
        eyebrow="dziennik gracza"
        title="Moje zakłady"
        lead={
          <>
            Wszystko, co postawiłeś, w jednym miejscu. Po meczu wpisz wynik i
            kurs, jaki był tuż przed pierwszym gwizdkiem – pokażemy Ci, czy
            łapiesz lepsze kursy niż reszta rynku. Jeśli w dłuższej serii są
            lepsze, to najmocniejszy dowód, że ten system naprawdę coś
            znajduje.
          </>
        }
      />
      <MojeKupony historia={historia} />
      <BetTracker />
    </div>
  );
}
