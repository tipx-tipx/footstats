/**
 * DOBA PRODUKTOWA 6:00 → 6:00, nie kalendarzowa (2026-08-14).
 *
 * 41% naszych typów to mecze grane między północą a 4:00 rano — Ameryka Płd.
 * Przy dacie kalendarzowej mecz o 2:00 w nocy z piątku na sobotę pokazywałby
 * się jako „jutro", choć człowiek obstawia go w piątek wieczorem i choć
 * należy do PIĄTKOWEJ listy dnia, którą backend zamyka o 6:00 (patrz
 * `build_wc_fast.dzien_listy` — ta sama definicja po obu stronach).
 *
 * ⚑ JEDNO MIEJSCE DLA OBU ZAKŁADEK (2026-09-15). Limit listy liczy się na
 * dobę osobno w Zawodnikach i w Drużynach (15 wysokiej szansy + 5 wyższych
 * kursów), więc obie zakładki muszą ciąć dni tą samą granicą — inaczej
 * dzień na stronie nie zgadzałby się z dniem, dla którego liczy się limit.
 *
 * ⚑ Terminarz meczów (`TerminarzMeczy`) świadomie zostaje przy dacie
 * kalendarzowej: tam pytanie brzmi „kiedy jest ten mecz", a nie „co mogę
 * dziś zagrać". Skuteczność i rozliczenia też liczą doby kalendarzowo
 * (`rozliczanie.dzien_pl`) i tego nie wolno zmieniać — przestawiłoby
 * całą historię.
 */
export const GODZINA_DOMKNIECIA = 6;

export function kluczDnia(ts: number): string {
  const przesuniete = (ts - GODZINA_DOMKNIECIA * 3600) * 1000;
  return new Intl.DateTimeFormat("en-CA", {
    dateStyle: "short",
    timeZone: "Europe/Warsaw",
  }).format(new Date(przesuniete));
}

export function etykietaDnia(
  ts: number,
  teraz: number,
): { glowna: string; data: string } {
  const pelna = new Intl.DateTimeFormat("pl-PL", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "Europe/Warsaw",
  }).format(new Date(ts * 1000));
  if (kluczDnia(ts) === kluczDnia(teraz)) return { glowna: "dziś", data: pelna };
  if (kluczDnia(ts) === kluczDnia(teraz + 86400))
    return { glowna: "jutro", data: pelna };
  const [dow, ...reszta] = pelna.split(" ");
  // pl-PL daje "czwartek, 23 lipca" – przecinek zostaje przy dniu tygodnia
  return { glowna: dow.replace(/,$/, ""), data: reszta.join(" ") };
}
