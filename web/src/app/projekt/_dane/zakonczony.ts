/**
 * Rozegrany mecz (redesign 7B): strona meczu znika po gwizdku, a adres
 * z zakładek albo z linku dalej działa. Zamiast suchego 404 – nasze typy
 * z tego meczu i jak wyszły. Po numerze meczu w rozliczeniach (`mecz_id`
 * od 7B); te same reguły co Wyniki: bez typów spoza publikacji, z drabinki
 * tylko 1. szczebel.
 */

import { zrodlo } from "./zrodlo";

type TypS = {
  mecz_id?: number | null;
  podmiot: string;
  mecz: string;
  rynek: string;
  rynek_kod: string;
  strona: string;
  linia: number;
  wynik: string;
  faktyczna: number | null;
  szczebel: number | null;
  poza_publikacja: unknown;
};

export type MeczZakonczony = {
  mecz: string;
  /** RRRR-MM-DD – dzień w Wynikach */
  dzien: string;
  typy: { kto: string; rynek: string; strona: string; linia: number; wynik: "wygrany" | "przegrany" | "zwrot"; faktyczna: number | null }[];
};

export function meczZakonczony(id: number): MeczZakonczony | null {
  const dni = (zrodlo().wyniki as { skutecznosc_dzienna?: { dzien: string; typy: TypS[] }[] }).skutecznosc_dzienna ?? [];
  for (const d of dni) {
    const typy = d.typy.filter(
      (t) => t.mecz_id === id && !t.poza_publikacja && (t.szczebel ?? 1) <= 1 && ["wygrany", "przegrany", "zwrot"].includes(t.wynik),
    );
    if (!typy.length) continue;
    return {
      mecz: typy[0].mecz.replace(/\s+-\s+/, " – "),
      dzien: d.dzien,
      typy: typy.map((t) => ({
        kto: /^match_/.test(t.rynek_kod) ? t.mecz : t.podmiot,
        rynek: t.rynek,
        strona: t.strona,
        linia: t.linia,
        wynik: t.wynik as "wygrany" | "przegrany" | "zwrot",
        faktyczna: t.faktyczna ?? null,
      })),
    };
  }
  return null;
}
