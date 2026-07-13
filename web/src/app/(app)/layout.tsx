import { MainShell } from "@/components/MainShell";
import { Nav } from "@/components/Nav";
import { SiteFooter } from "@/components/SiteFooter";
import { getMeta } from "@/lib/data";

/**
 * Chrome aplikacji (Nav + kolumna treści + stopka) — WYŁĄCZNIE dla stron
 * "wewnątrz" produktu. /login żyje poza tą grupą tras (parenteza w nazwie
 * folderu nie wchodzi do URL-a) i dostaje sam root layout, bez tego chrome'u
 * — dzięki temu Nav/MainShell/SiteFooter nie muszą już sprawdzać pathname
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
      <Nav />
      <MainShell>{children}</MainShell>
      <SiteFooter
        zrodlo={meta.zrodlo}
        liga={meta.liga}
        sezon={meta.sezon}
        meczow={meta.meczow_w_bazie}
        aktualizacja={aktualizacja}
      />
    </>
  );
}
