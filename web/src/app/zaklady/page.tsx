import { BetTracker } from "@/components/BetTracker";

export const metadata = { title: "Moje zakłady — FootStats" };

export default function ZakladyPage() {
  return (
    <div className="pt-10">
      <h1 className="text-2xl font-bold">Moje zakłady</h1>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
        Dziennik postawionych zakładów. Po meczu uzupełnij wynik i kurs
        zamknięcia — zobaczysz swój <strong>CLV</strong>, czyli czy bierzesz
        kursy lepsze niż rynek tuż przed meczem. Dodatni CLV w dłuższej serii
        to najlepszy dowód, że system znajduje prawdziwą wartość.
      </p>
      <BetTracker />
    </div>
  );
}
