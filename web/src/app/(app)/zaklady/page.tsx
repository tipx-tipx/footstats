import { BetTracker } from "@/components/BetTracker";
import { MojeKupony } from "@/components/MojeKupony";
import { PageHeader } from "@/components/PageHeader";
import { getTypyWyniki } from "@/lib/data";

export const metadata = { title: "Moje zakłady – FootStats" };

export default async function ZakladyPage() {
  // historia kuponów z pipeline'u — zagrane kupony rozliczają się z niej
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
            Wszystko, co postawiłeś, w jednym miejscu. Po meczu uzupełnij wynik
            i kurs zamknięcia, a zobaczysz swój <strong>CLV</strong>, czyli czy
            bierzesz kursy lepsze niż rynek tuż przed meczem. Dodatni CLV w
            dłuższej serii to najlepszy dowód, że system znajduje prawdziwą
            wartość.
          </>
        }
      />
      <MojeKupony historia={historia} />
      <BetTracker />
    </div>
  );
}
