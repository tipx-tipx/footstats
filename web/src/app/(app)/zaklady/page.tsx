import { BetTracker } from "@/components/BetTracker";
import { PageHeader } from "@/components/PageHeader";

export const metadata = { title: "Moje zakłady — FootStats" };

export default function ZakladyPage() {
  return (
    <div>
      <PageHeader
        eyebrow="dziennik gracza"
        title="Moje zakłady"
        lead={
          <>
            Wszystko, co postawiłeś, w jednym miejscu. Po meczu uzupełnij wynik
            i kurs zamknięcia — zobaczysz swój <strong>CLV</strong>, czyli czy
            bierzesz kursy lepsze niż rynek tuż przed meczem. Dodatni CLV w
            dłuższej serii to najlepszy dowód, że system znajduje prawdziwą
            wartość.
          </>
        }
      />
      <BetTracker />
    </div>
  );
}
