import { StronaAplikacji } from "@/app/projekt/_ui/aplikacja/Strona";
import { przygotujStrony } from "@/app/projekt/_dane/strony";
import { zDanymi } from "@/app/projekt/_dane/zrodlo";
import { pobierzSurowe } from "@/lib/nowe/surowe";
import { czyTelefon } from "@/lib/nowe/telefon";

export const metadata = { title: "Mecze – FootStats" };

/**
 * Mecze – lista (redesign, etap 7.3; 5.3 zatwierdzone 01.10): wejście do
 * narzędzia pokryć. W wierszu: ilu zawodników ma kurs i ile typów jest na liście.
 */
export default async function MeczePage() {
  const [surowe, telefon] = await Promise.all([pobierzSurowe(), czyTelefon()]);
  const dane = zDanymi(surowe, () => przygotujStrony());
  return <StronaAplikacji strona="mecze" dane={dane} teraz={surowe.teraz} telefon={telefon} />;
}
