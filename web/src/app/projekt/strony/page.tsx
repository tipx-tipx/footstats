import { przygotujKontrole } from "../_dane/kontrola";
import { przygotujMecze } from "../_dane/mecz";
import { przygotujSkutecznosc } from "../_dane/skutecznosc";
import { przygotujStrony } from "../_dane/strony";
import { przygotujZawodnikow } from "../_dane/zawodnik";
import { UkladyStron, type StartUkladow } from "../_ui/strony/UkladyStron";

export default async function StronyPage({ searchParams }: { searchParams: Promise<StartUkladow> }) {
  return <UkladyStron dane={przygotujStrony()} mecze={przygotujMecze()} skutecznosc={przygotujSkutecznosc()} kontrola={przygotujKontrole()} zawodnicy={przygotujZawodnikow()} start={await searchParams} />;
}
