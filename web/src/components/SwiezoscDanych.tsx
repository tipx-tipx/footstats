"use client";

import { useEffect, useState } from "react";

/**
 * ILE LAT MAJĄ DANE — widoczne z każdej strony.
 *
 * PO CO (przegląd sprzedażowy, punkt „brak wskaźnika świeżości"). Produkt
 * obiecuje żywe dane i pokazuje kursy, po których można postawić pieniądze.
 * Do 05.08 jedynym śladem, kiedy je zebrano, był napis „AKTUALIZACJA 13:19"
 * w stopce, najmniejszą czcionką na stronie — czyli człowiek dowiadywał się,
 * że kurs jest nieaktualny, dopiero u bukmachera, przy zakładzie.
 *
 * PROGI WZIĘTE Z POMIARU, nie z sufitu (05.08, 100 przebiegów z API GitHuba):
 * cykl trwa ~32 min, a po wpięciu pingu `/api/tick` dane mają przychodzić
 * mniej więcej co tyle. Więc:
 *
 *     < 45 min    świeże      normalna praca
 *     45–120 min  opóźnione   cykl się dławi albo ping nie doszedł
 *     > 120 min   stare       coś stoi — i user ma prawo to wiedzieć PRZED
 *                             postawieniem zakładu, nie po
 *
 * Liczone w PRZEGLĄDARCE, bo strony są ISR-owe: gdyby zdanie „sprzed 10 minut"
 * renderował serwer, zamroziłoby się w chwili budowania strony i po godzinie
 * nadal twierdziłoby „10 minut". Stąd `useEffect` i licznik odświeżany co
 * minutę. Do czasu montażu nie renderujemy NIC — inaczej pierwsza klatka
 * różniłaby się od serwerowej i React zgłosiłby rozjazd hydracji.
 */

const PROG_SWIEZE_MIN = 45;
const PROG_OPOZNIONE_MIN = 120;

function odmienMinuty(n: number): string {
  if (n === 1) return "minutę";
  const r10 = n % 10;
  const r100 = n % 100;
  return r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14) ? "minuty" : "minut";
}

function odmienGodziny(n: number): string {
  if (n === 1) return "godzinę";
  const r10 = n % 10;
  const r100 = n % 100;
  return r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14) ? "godziny" : "godzin";
}

function ileTemu(min: number): string {
  if (min < 1) return "przed chwilą";
  if (min < 90) return `${min} ${odmienMinuty(min)} temu`;
  const godz = Math.round(min / 60);
  return `${godz} ${odmienGodziny(godz)} temu`;
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

  const stan =
    m < PROG_SWIEZE_MIN
      ? {
          slowo: "dane świeże",
          kropka: "bg-data-green",
          tekst: "text-data-green-ink",
          tlo: "bg-data-green-wash",
          tytul:
            "Kursy i statystyki z ostatniego przeliczenia. Przeliczamy mniej " +
            "więcej co pół godziny.",
        }
      : m < PROG_OPOZNIONE_MIN
        ? {
            slowo: "dane opóźnione",
            kropka: "bg-data-amber",
            tekst: "text-data-amber-ink",
            tlo: "bg-data-amber-wash",
            tytul:
              "Ostatnie przeliczenie było dawniej, niż powinno. Kursy mogły " +
              "się u bukmachera zmienić — sprawdź je przed zakładem.",
          }
        : {
            slowo: "dane stare",
            kropka: "bg-data-red",
            tekst: "text-data-red-ink",
            tlo: "bg-data-red-wash",
            tytul:
              "Przeliczanie stoi od ponad dwóch godzin. Traktuj kursy i typy " +
              "jako orientacyjne, dopóki dane nie wrócą.",
          };

  return (
    <span
      title={stan.tytul}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full ${stan.tlo} px-2.5 py-1 text-[11px] font-medium ${stan.tekst}`}
    >
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${stan.kropka}`} />
      {stan.slowo}
      <span className="font-data text-faint">· {ileTemu(m)}</span>
    </span>
  );
}
