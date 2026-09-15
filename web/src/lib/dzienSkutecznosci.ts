import type { SkutecznoscDnia } from "./types";

/**
 * CZY TEN DZIEŃ MA COKOLWIEK DO POKAZANIA.
 *
 * ⚑ DZIEŃ BEZ ANI JEDNEJ PUBLIKACJI ZNIKAŁ W CAŁOŚCI (zgłoszenie usera
 * 2026-09-11: „gdzie są typy z 10 września?!"). 10.09 miał 80 rozliczonych
 * typów, 42 trafione — ale ŻADEN nie wszedł na listę dnia, bo produkt wstał
 * po godzinie domknięcia doby. `rozliczone` liczy tylko typy publikowane,
 * więc było zero, a kalendarz i nawigacja filtrowały dni po `rozliczone > 0`.
 * Efekt: dzień nie miał kafelka, nie dało się go wybrać strzałkami i nie było
 * ŻADNEJ ścieżki do jego typów — przy zasadzie „żadnych cichych odrzuceń" to
 * ciche odrzucenie całego dnia.
 *
 * Dlatego w widoku pełnym wystarczy, że dzień ma typy policzone na próbę.
 * W widoku klienta nie: `okrojDlaKlienta` zeruje `poza_n` i wycina te typy,
 * więc taki dzień byłby pustym kafelkiem prowadzącym do pustego panelu.
 */
export function maCoPokazacDnia(
  d: SkutecznoscDnia,
  pelnyWglad: boolean | undefined,
): boolean {
  // dzień z samymi zwrotami albo typami czekającymi na dane też ma co pokazać
  // (2026-09-16) – inaczej karta Hellebranda z 15.09 nie miałaby kafelka
  return (
    d.rozliczone > 0 ||
    (d.zwrot_n ?? 0) > 0 ||
    (d.czeka_n ?? 0) > 0 ||
    (!!pelnyWglad && (d.poza_n ?? 0) > 0)
  );
}
