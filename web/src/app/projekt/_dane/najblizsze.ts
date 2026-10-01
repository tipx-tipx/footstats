import { pobierzSurowe } from "@/lib/nowe/surowe";

import { przygotujStrony } from "./strony";
import { zDanymi } from "./zrodlo";

/** 404: najbliższe mecze z typami – droga dalej zamiast ślepego zaułka */
export async function najblizszeMecze(ile = 3) {
  const s = await pobierzSurowe();
  const strony = zDanymi(s, przygotujStrony);
  const najblizsze = [...strony.meczeWszystkie]
    .filter((m) => m.okazje > 0 && m.ts > s.teraz)
    .sort((a, b) => a.ts - b.ts)
    .slice(0, ile);
  return { najblizsze, teraz: s.teraz };
}
