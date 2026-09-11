/**
 * ODWROTNOŚĆ `_potnij` Z PIPELINE'U — I MUSI NIĄ BYĆ DOKŁADNIE.
 *
 * ⚑ `Object.assign` TU NIE WYSTARCZA (incydent 2026-09-11, kosztował 11 dni
 * niewidocznych rozliczeń). Element cięższy od limitu części pipeline tnie
 * REKURENCYJNIE i owija podkawałki z powrotem w jego własny klucz, więc ten
 * sam klucz najwyższego poziomu wraca w kilku częściach:
 *
 *     cz01 {"skutecznosc_dzienna": [17 dni]}
 *     cz02 {"skutecznosc_dzienna": [3 dni]}
 *     cz03 {"skutecznosc_dzienna": [1 dzień]}
 *
 * `Object.assign` zostawiał z tego OSTATNI kawałek, czyli 1 dzień z 21 — na
 * stronie Skuteczności kalendarz stał na 20 sierpnia, bo końcówka listy to
 * dni NAJSTARSZE. Dane w bazie były kompletnie poprawne; gubił je odczyt.
 * To ten sam rodzaj cichej awarii co niekomplet wyżej: strona wyglądała
 * zdrowo, tylko bez większości treści.
 *
 * Scalamy więc jak `supa._scal_w_glab`: słowniki w głąb, listy dopisując.
 *
 * ⚑ NIE WCHODZIMY KAWAŁKOWI DO ŚRODKA. Pierwsze wystąpienie klucza wstawiamy
 * jako KOPIĘ, bo inaczej `push` dopisywałby do tablicy należącej do kawałka
 * — na wyniku to nie zmienia nic (kawałków nikt już nie czyta), ale każdy
 * pomiar robiony po sklejeniu widzi wtedy zawyżone sumy i zgłasza awarię,
 * której nie ma.
 */
export function scalWGlab(cel: Record<string, unknown>, dolozenie: Record<string, unknown>): void {
  for (const [k, v] of Object.entries(dolozenie)) {
    const juz = cel[k];
    if (czySlownik(v) && czySlownik(juz)) {
      scalWGlab(juz, v);
    } else if (Array.isArray(v) && Array.isArray(juz)) {
      juz.push(...v);
    } else if (Array.isArray(v)) {
      cel[k] = [...v];
    } else if (czySlownik(v)) {
      cel[k] = { ...v };
    } else {
      cel[k] = v;
    }
  }
}

function czySlownik(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}
