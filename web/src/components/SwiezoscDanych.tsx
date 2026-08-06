"use client";

import { useEffect, useState } from "react";

/**
 * KIEDY SPRAWDZALIŚMY KURSY — jedna plakietka, widoczna z każdej strony.
 *
 * PRZEPISANE 2026-08-06. Poprzednia wersja miała trzy stany („dane świeże",
 * „dane opóźnione", „dane stare") z progami 45 i 120 minut. Progi wzięły się
 * z założenia, że cykl chodzi co pół godziny — a zmierzony rytm to zupełnie
 * co innego (163 przebiegi z dwóch tygodni):
 *
 *     mediana odstępu 82 min
 *     próg  45 min -> ostrzeżenie świeci w 78% wejść
 *     próg 120 min -> w 31%
 *     próg 240 min -> w 7%     <- dopiero tu znaczy „coś stoi"
 *
 * Czyli kupujący widział żółte „dane opóźnione" przy w pełni sprawnym
 * produkcie, prawie zawsze. Ostrzeżenie, które świeci zawsze, nie ostrzega
 * przed niczym — psuje tylko zaufanie do reszty strony.
 *
 * DRUGA ZMIANA, WAŻNIEJSZA: to nie jest miejsce na raport o naszym cyklu.
 * Człowieka nie obchodzi, czy pipeline chodzi co 45 czy co 90 minut. Obchodzi
 * go jedno pytanie: „czy kurs, który widzę, jest jeszcze aktualny". Plakietka
 * odpowiada więc tylko na nie, i tylko wtedy, gdy odpowiedź brzmi „sprawdź".
 *
 * Liczone w PRZEGLĄDARCE, bo strony są ISR-owe: zdanie „sprzed 10 minut"
 * renderowane na serwerze zamroziłoby się w chwili budowania strony.
 */

/** Powyżej tylu minut kurs mógł się realnie ruszyć — patrz pomiar wyżej. */
const PROG_OSTRZEZENIA_MIN = 240;

/** „sprzed godziny", „sprzed 5 godzin" — po „sprzed" idzie dopełniacz. */
function odmienGodziny(n: number): string {
  return n === 1 ? "godziny" : "godzin";
}

export function SwiezoscDanych({ wygenerowanoTs }: { wygenerowanoTs: number }) {
  const [minuty, setMinuty] = useState<number | null>(null);

  useEffect(() => {
    if (!wygenerowanoTs) return;
    const policz = () =>
      setMinuty(Math.max(0, Math.floor(Date.now() / 1000 - wygenerowanoTs) / 60));
    policz();
    const id = setInterval(policz, 60_000);
    return () => clearInterval(id);
  }, [wygenerowanoTs]);

  if (minuty === null) return null;
  const m = Math.floor(minuty);
  const godzina = new Intl.DateTimeFormat("pl-PL", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  }).format(new Date(wygenerowanoTs * 1000));

  if (m >= PROG_OSTRZEZENIA_MIN) {
    const godz = Math.round(m / 60);
    return (
      <span
        title="Od tego czasu kurs mógł się u bukmachera zmienić. Zanim postawisz, zerknij, czy się zgadza."
        className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-data-amber-wash px-2.5 py-1 text-[11px] font-medium text-data-amber-ink"
      >
        <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-data-amber" />
        kursy sprzed {godz} {odmienGodziny(godz)} – sprawdź przed zakładem
      </span>
    );
  }

  return (
    <span
      title="Tyle było na zegarze, gdy ostatnio pobieraliśmy kursy i statystyki."
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-data-green-wash px-2.5 py-1 text-[11px] font-medium text-data-green-ink"
    >
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-data-green" />
      kursy z <span className="font-data">{godzina}</span>
    </span>
  );
}
