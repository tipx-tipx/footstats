import { SzkieletAplikacji } from "@/app/projekt/_ui/szkielet/SzkieletAplikacji";
import { druzyna } from "@/app/projekt/_dane/przygotuj";
import type { IndeksSzukania } from "@/app/projekt/_ui/szkielet/PaletaAplikacji";
import type { Mecz, ValueBet } from "@/lib/types";
import { getMecze, getMeta, getValueBets, terazTs } from "@/lib/data";
import { bezZjechanych } from "@/lib/kursTeraz";
import { zHerbamiMeczow } from "@/lib/nowe/surowe";

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
  const [meta, wszystkie, mecze] = await Promise.all([getMeta(), getValueBets(), getMecze()]);
  // wyszukiwarka nie podsuwa typów, których kursu już nie ma (lib/kursTeraz.ts)
  const typy = bezZjechanych(wszystkie.filter((t) => !t.sugestia));
  // indeks wyszukiwarki (Ctrl+K): kilka KB z danych, które układ i tak ma
  const kiedy = new Intl.DateTimeFormat("pl-PL", { weekday: "short", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Warsaw" });
  // stopka: ile rozgrywek naprawdę jest w ofercie na tydzień (zamiast stałej „50+”)
  const zaTydzien = terazTs() + 7 * 86400;
  const rozgrywek = new Set(mecze.filter((m) => m.kickoff_ts < zaTydzien && m.liga).map((m) => m.liga)).size;
  // herby z numerów drużyn w meczach (7B) – także drużyn spoza mapy w kodzie
  const indeks = zHerbamiMeczow(mecze, () => zbudujIndeks(typy, mecze, kiedy));
  return (
    <SzkieletAplikacji wygenerowanoTs={meta.wygenerowano_ts} indeks={indeks} rozgrywek={rozgrywek}>
      {children}
    </SzkieletAplikacji>
  );
}

function zbudujIndeks(typy: ValueBet[], mecze: Mecz[], kiedy: Intl.DateTimeFormat): IndeksSzukania {
  const zaw = new Map<number, IndeksSzukania["zawodnicy"][number]>();
  const dr = new Map<string, number>();
  for (const t of typy) {
    if (t.podmiot_typ === "druzyna") dr.set(t.podmiot, (dr.get(t.podmiot) ?? 0) + 1);
    else {
      const z = zaw.get(t.podmiot_id) ?? { id: t.podmiot_id, nazwa: t.podmiot, druzyna: t.druzyna ? druzyna(t.druzyna) : null, typy: 0 };
      z.typy++;
      zaw.set(t.podmiot_id, z);
    }
  }
  for (const m of mecze) for (const n of [m.gospodarz, m.gosc]) if (!dr.has(n)) dr.set(n, 0);
  return {
    zawodnicy: [...zaw.values()].sort((a, b) => b.typy - a.typy),
    druzyny: [...dr.entries()].map(([nazwa, n]) => ({ nazwa, herb: druzyna(nazwa), typy: n })).sort((a, b) => b.typy - a.typy),
    mecze: [...mecze].sort((a, b) => a.kickoff_ts - b.kickoff_ts).map((m) => ({ id: m.id, gosp: druzyna(m.gospodarz), gosc: druzyna(m.gosc), opis: kiedy.format(new Date(m.kickoff_ts * 1000)) })),
  };
}
