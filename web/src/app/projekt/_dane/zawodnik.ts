/**
 * Etap 5.7 – strona zawodnika (zaakceptowana 01.10). Z migawki: pełne kadry
 * 2 meczów (`pokrycia.json` przez `przygotujMecze`), typy na liście
 * (`przygotujStrony`), rozliczenia (`wyniki.json`, reguły jak w Wynikach:
 * bez typów spoza publikacji, drabinki tylko 1. szczebel).
 *
 * Nowe względem strony meczu: jeden zawodnik, WSZYSTKIE jego rynki naraz,
 * jego typy z różnych meczów i historia naszych typów na niego.
 *
 * Na produkcji (7B): zawodnik z lekkiego koszyka `zaw_kNN` (10 meczów +
 * kursy obu bukmacherów), a gdy go jeszcze nie ma – z kadr meczu jak strona
 * meczu. Historia naszych typów po numerze zawodnika (`podmiot_id`
 * w rozliczeniach od 7B); starsze rozliczenia bez numeru – po nazwisku.
 */

import { przygotujMecze, RYNKI_ZAWODNIKA, type HistoriaRynku, type MeczStrony } from "./mecz";
import { przygotujStrony } from "./strony";
import { zrodlo } from "./zrodlo";

/** zawodnicy w podglądzie: typ na liście bez historii, gwiazda z historią, drugi typ na liście */
const POKAZ = ["Romano Schmid", "Erling Haaland", "Ethan Ampadu"];

export type RynekZawodnika = {
  kod: string;
  nazwa: string;
  historia: HistoriaRynku;
  /** linia → wyższy kurs z dwóch bukmacherów i ten, który go daje */
  kursy: { linia: number; kurs: number; bukmacher: "Superbet" | "Betclic" }[];
  /** linia na start: nasz typ, a bez typu – kurs najbliżej 1,85 */
  liniaStart: number;
  typ: { linia: number } | null;
};

type TypS = { podmiot: string; podmiot_id?: number | null; mecz: string; rynek: string; rynek_kod: string; strona: string; linia: number; kurs: number; wynik: string; faktyczna: number | null; ekran: string | null; szczebel: number | null; poza_publikacja: unknown };

/** strona jednego zawodnika – z meczu, w którym ma kurs (kadry w `zrodlo().pokrycia`) */
export function przygotujZawodnika(id: number) {
  const mecze = przygotujMecze();
  const strony = przygotujStrony();
  const dni = (zrodlo().wyniki as { skutecznosc_dzienna: { dzien: string; typy: TypS[] }[] }).skutecznosc_dzienna ?? [];
  const m = mecze.find((x) => x.zawodnicy.some((z) => z.id === id));
  const z = m?.zawodnicy.find((x) => x.id === id);
  if (!m || !z) return null;
  const nazwa = z.nazwa;

  const rynki: RynekZawodnika[] = RYNKI_ZAWODNIKA.filter(([kod]) => z.rynki[kod]).map(([kod, nazwaR]) => {
    const kursy = Object.entries(z.kursy[kod] ?? {})
      .map(([l, k]) => {
        const bc = (k.bc ?? 0) > (k.sb ?? 0);
        return { linia: Number(l), kurs: (bc ? k.bc : k.sb) ?? 0, bukmacher: bc ? ("Betclic" as const) : ("Superbet" as const) };
      })
      // linie z kursem powyżej 8 to loteria (np. 4,5 strzału po 12,00) – najwyżej 4 linie
      .filter((x) => x.kurs > 1 && (x.kurs <= 8 || x.linia === z.naLiscie[kod]?.linia))
      .sort((a, b) => a.linia - b.linia)
      .slice(0, 4);
    const typ = z.naLiscie[kod] ? { linia: z.naLiscie[kod].linia } : null;
    const liniaStart = typ?.linia ?? [...kursy].sort((a, b) => Math.abs(a.kurs - 1.85) - Math.abs(b.kurs - 1.85))[0]?.linia ?? 0.5;
    return { kod, nazwa: nazwaR, historia: z.rynki[kod], kursy, liniaStart, typ };
  });

  const typy = strony.kartyStrony.filter((k) => k.kto === nazwa);

  // po numerze zawodnika (7B); rozliczenia sprzed 7B nie mają numeru – po nazwisku
  const jego = (t: TypS) => (t.podmiot_id != null ? t.podmiot_id === id : t.podmiot === nazwa);
  const historia = dni.flatMap((d) =>
    d.typy
      .filter((t) => jego(t) && !t.poza_publikacja && (t.szczebel ?? 1) <= 1 && ["wygrany", "przegrany", "zwrot"].includes(t.wynik))
      .map((t) => ({ dzien: d.dzien, mecz: t.mecz, rynek: t.rynek, strona: t.strona, linia: t.linia, kurs: t.kurs, wynik: t.wynik as "wygrany" | "przegrany" | "zwrot", faktyczna: t.faktyczna })),
  );

  const druzyna = z.strona === "gosp" ? m.gosp : m.gosc;
  const rywal = z.strona === "gosp" ? m.gosc : m.gosp;
  return { id: z.id, nazwa, pozycja: z.pozycja, xi: z.xi, druzyna, rywal, mecz: m as MeczStrony, rynki, typy, historia };
}

/** warsztat: trzech zawodników z migawki do porównania */
export function przygotujZawodnikow() {
  const mecze = przygotujMecze();
  return POKAZ.flatMap((nazwa) => {
    const z = mecze.flatMap((m) => m.zawodnicy).find((x) => x.nazwa === nazwa);
    const s = z ? przygotujZawodnika(z.id) : null;
    return s ? [s] : [];
  });
}

export type ZawodnikStrony = NonNullable<ReturnType<typeof przygotujZawodnika>>;

