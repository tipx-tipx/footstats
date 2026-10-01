/**
 * Strony systemowe (logowanie, 404, błąd, brak internetu) – liczby z tych
 * samych migawek co reszta warsztatu. Logowanie pokazuje prawdziwe wyniki
 * (wszystkie dni od startu, także słabe) i to, co czeka za hasłem.
 */

import { przygotujSkutecznosc } from "./skutecznosc";
import { przygotujStrony } from "./strony";

export function przygotujSystemowe() {
  const strony = przygotujStrony();
  const sk = przygotujSkutecznosc();

  // dni od najstarszego: weszło / rozstrzygnięte (zwrot nie liczy się w żadną stronę)
  const dni = [...sk.dni]
    .sort((a, b) => a.klucz.localeCompare(b.klucz))
    .map((d) => {
      const ok = d.typy.filter((t) => t.wynik === "wygrany").length;
      const n = d.typy.filter((t) => t.wynik !== "zwrot").length;
      return { klucz: d.klucz, ok, n };
    })
    .filter((d) => d.n > 0);
  const suma = dni.reduce((a, d) => ({ ok: a.ok + d.ok, n: a.n + d.n }), { ok: 0, n: 0 });

  // najbliższy dzień z typami: ile typów, ile meczów, kiedy pierwszy, półki
  const karty = [...strony.kartyStrony].sort((a, b) => a.ts - b.ts);
  const dzienPl = (ts: number) => new Date((ts + 2 * 3600) * 1000).toISOString().slice(0, 10);
  const pierwszyDzien = karty.length ? dzienPl(karty[0].ts) : null;
  const naDzien = karty.filter((k) => pierwszyDzien && dzienPl(k.ts) === pierwszyDzien);
  const polki: Record<string, number> = {};
  for (const k of naDzien) polki[k.polka] = (polki[k.polka] ?? 0) + 1;
  const godz = naDzien.length ? new Date((naDzien[0].ts + 2 * 3600) * 1000).toISOString().slice(11, 16) : null;
  const wczoraj = dni.at(-1) ?? null;

  // 404 „mecz się skończył”: prawdziwy rozliczony mecz z migawki – ten
  // z największą liczbą naszych typów z ostatnich trzech dni
  const kandydaci = sk.dni.slice(0, 3).flatMap((d) => {
    const m = new Map<string, typeof d.typy>();
    for (const t of d.typy) m.set(t.mecz, [...(m.get(t.mecz) ?? []), t]);
    return [...m.entries()].map(([mecz, typy]) => ({ dzien: d.klucz, mecz: mecz.replace(/�/g, "–"), typy }));
  });
  const zakonczony = kandydaci.sort((a, b) => b.typy.length - a.typy.length)[0] ?? null;

  // 404: najbliższe mecze z typami – droga dalej zamiast ślepego zaułka
  const najblizsze = [...strony.meczeWszystkie]
    .filter((m) => m.okazje > 0)
    .sort((a, b) => a.ts - b.ts)
    .slice(0, 3);

  return {
    zakonczony,
    najblizsze,
    strony,
    dni,
    suma,
    start: sk.start,
    dzis: {
      dzien: pierwszyDzien,
      typy: naDzien.length,
      zawodnicy: naDzien.filter((k) => k.podmiotTyp === "zawodnik").length,
      druzyny: naDzien.filter((k) => k.podmiotTyp === "druzyna").length,
      mecze: new Set(naDzien.map((k) => k.meczId)).size,
      pierwszy: godz,
      polki,
    },
    wczoraj,
  };
}

export type DaneSystemowe = ReturnType<typeof przygotujSystemowe>;
