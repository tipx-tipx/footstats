import { StronaAplikacji } from "@/app/projekt/_ui/aplikacja/Strona";
import { mocneLinieMeczow, przygotujLinie } from "@/app/projekt/_dane/linie";
import { przygotujStrony } from "@/app/projekt/_dane/strony";
import { zDanymi } from "@/app/projekt/_dane/zrodlo";
import { pobierzSurowe, zLiniami } from "@/lib/nowe/surowe";
import { czyTelefon } from "@/lib/nowe/telefon";

export const metadata = { title: "Mecze – FootStats" };

/**
 * Mecze – lista (redesign, etap 7.3; 5.3 zatwierdzone 01.10): wejście do
 * narzędzia pokryć. W wierszu: ilu zawodników ma kurs i ile typów jest na liście.
 * Obok listy „Najlepsze linie” (15.10) – linie ze wszystkich meczów naraz.
 */
export default async function MeczePage({ searchParams }: { searchParams: Promise<{ widok?: string }> }) {
  const { widok } = await searchParams;
  const [surowe, telefon] = await Promise.all([pobierzSurowe().then(zLiniami), czyTelefon()]);
  const [dane, linie, mocne] = zDanymi(surowe, () => [przygotujStrony(), przygotujLinie(), mocneLinieMeczow()] as const);
  return <StronaAplikacji strona="mecze" dane={dane} teraz={surowe.teraz} telefon={telefon} linie={{ dane: linie, mocne, widok }} />;
}
