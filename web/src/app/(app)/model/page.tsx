import { StronaAplikacji } from "@/app/projekt/_ui/aplikacja/Strona";
import { przygotujKontrole } from "@/app/projekt/_dane/kontrola";
import { przygotujSkutecznosc } from "@/app/projekt/_dane/skutecznosc";
import { przygotujStrony } from "@/app/projekt/_dane/strony";
import { zDanymi } from "@/app/projekt/_dane/zrodlo";
import { czyPelnyWglad, czytajRole } from "@/lib/rola";
import { pobierzSurowe, zKuchnia } from "@/lib/nowe/surowe";
import { czyTelefon } from "@/lib/nowe/telefon";

export const metadata = { title: "Wyniki – FootStats" };

/**
 * Wyniki (redesign, etap 7.3): klient – kalendarz (5.5 A); admin – przełącznik
 * Wyniki | Kontrola (5.6 A Raport), gdzie „Wyniki” = dokładnie widok klienta.
 *
 * ROLE NA SERWERZE: dane Kontroli liczone i wysyłane wyłącznie adminowi
 * (web/AGENTS.md – ukrycie w interfejsie to nie ukrycie).
 */
export default async function WynikiPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const [surowe, telefon, rola, q] = await Promise.all([pobierzSurowe(), czyTelefon(), czytajRole(), searchParams]);
  const start = { widok: q.widok, dzien: /^\d{4}-\d{2}-\d{2}$/.test(q.dzien ?? "") ? q.dzien : undefined };
  const admin = czyPelnyWglad(rola);
  const pelne = admin ? await zKuchnia(surowe) : surowe;
  const [dane, skutecznosc, kontrola] = zDanymi(pelne, () => [przygotujStrony(), przygotujSkutecznosc(), admin ? przygotujKontrole() : undefined] as const);
  return <StronaAplikacji strona="wyniki" dane={dane} wyniki={{ skutecznosc, kontrola, start }} teraz={surowe.teraz} telefon={telefon} />;
}
