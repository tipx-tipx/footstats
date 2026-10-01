import { StronaAplikacji } from "@/app/projekt/_ui/aplikacja/Strona";
import { przygotujStrony } from "@/app/projekt/_dane/strony";
import { zDanymi } from "@/app/projekt/_dane/zrodlo";
import { pobierzSurowe } from "@/lib/nowe/surowe";
import { czyTelefon } from "@/lib/nowe/telefon";

/**
 * Zawodnicy – strona główna (redesign, etap 7.3). Układ C „najpierw
 * najlepsze”, zatwierdzony 01.10 w warsztacie (/projekt/strony, 5.1).
 * Dane: te same adaptery co w warsztacie, policzone na danych z Supabase.
 */
export default async function ZawodnicyPage() {
  const [surowe, telefon] = await Promise.all([pobierzSurowe(), czyTelefon()]);
  const dane = zDanymi(surowe, () => przygotujStrony());
  return <StronaAplikacji strona="zawodnicy" dane={dane} teraz={surowe.teraz} telefon={telefon} />;
}
