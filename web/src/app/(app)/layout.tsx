import { MainShell } from "@/components/MainShell";
import { Nav } from "@/components/Nav";
import { SiteFooter } from "@/components/SiteFooter";
import { getMeta } from "@/lib/data";

// ISR: odświeżaj strony grupy (app) co 60 s. Bez tego trasy bez API
// czasu żądania (druzyny, kupony, model, mecze, zaklady) domyślnie mają
// revalidate=false = prerender raz przy buildzie, a payload Supabase (~14 MB)
// przekracza limit 2 MB Data Cache, więc revalidate:60 z fetchu nie obniża
// interwału trasy. Ustawiony tu, na poziomie segmentu, działa niezależnie
// od cache'owalności fetchu (Cache Components wyłączony => stary model).
//
// ⚑ 60 s -> 1800 s (2026-08-25). Musi iść w parze z `ODSWIEZANIE_S` w
// `lib/data.ts`: to okno segmentu decyduje, jak często trasa w ogóle się
// przelicza, a każde przeliczenie to pobranie danych z Supabase. Minutowe
// okno przy 189 podstronach meczu wyczerpało miesięczny limit transferu
// (402 „exceed_egress_quota") i zatrzymało produkt.
export const revalidate = 1800;

/**
 * Chrome aplikacji (Nav + kolumna treści + stopka) – WYŁĄCZNIE dla stron
 * "wewnątrz" produktu. /login żyje poza tą grupą tras (parenteza w nazwie
 * folderu nie wchodzi do URL-a) i dostaje sam root layout, bez tego chrome'u
 * – dzięki temu Nav/MainShell/SiteFooter nie muszą już sprawdzać pathname
 * w czasie działania, żeby schować się na ekranie logowania.
 */
export default async function AppLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const meta = await getMeta();
  const aktualizacja = new Intl.DateTimeFormat("pl-PL", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  }).format(new Date(meta.wygenerowano_ts * 1000));
  return (
    <>
      <Nav wygenerowanoTs={meta.wygenerowano_ts} />
      <MainShell>{children}</MainShell>
      <SiteFooter
        liga={meta.liga}
        sezon={meta.sezon}
        aktualizacja={aktualizacja}
      />
    </>
  );
}
