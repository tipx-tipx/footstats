import { StronaAplikacji } from "@/app/projekt/_ui/aplikacja/Strona";
import { przygotujStrony } from "@/app/projekt/_dane/strony";
import { zDanymi } from "@/app/projekt/_dane/zrodlo";
import { pobierzSurowe } from "@/lib/nowe/surowe";
import { czyTelefon } from "@/lib/nowe/telefon";

export const metadata = { title: "Jak czytać typy – FootStats" };

/**
 * Jak czytać typy (redesign, etap 7.3; 5.8 B „krok po kroku” zatwierdzone 01.10):
 * prawdziwa karta typu z listy rozebrana na części, słowniczek, pytania.
 */
export default async function JakPage() {
  const [surowe, telefon] = await Promise.all([pobierzSurowe(), czyTelefon()]);
  const dane = zDanymi(surowe, () => przygotujStrony());
  return <StronaAplikacji strona="jak" dane={dane} teraz={surowe.teraz} telefon={telefon} />;
}
