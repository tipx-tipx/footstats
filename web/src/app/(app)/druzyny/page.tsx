import { StronaAplikacji } from "@/app/projekt/_ui/aplikacja/Strona";
import { przygotujStrony } from "@/app/projekt/_dane/strony";
import { zDanymi } from "@/app/projekt/_dane/zrodlo";
import { pobierzSurowe } from "@/lib/nowe/surowe";
import { czyTelefon } from "@/lib/nowe/telefon";

export const metadata = { title: "Drużyny – FootStats" };

/**
 * Drużyny (redesign, etap 7.3). Układ A+B zatwierdzony 01.10 (/projekt/strony,
 * 5.2): szkielet jak Zawodnicy + mecz jako pojedynek (średnie obu drużyn).
 */
export default async function DruzynyPage() {
  const [surowe, telefon] = await Promise.all([pobierzSurowe(), czyTelefon()]);
  const dane = zDanymi(surowe, () => przygotujStrony());
  return <StronaAplikacji strona="druzyny" dane={dane} teraz={surowe.teraz} telefon={telefon} />;
}
