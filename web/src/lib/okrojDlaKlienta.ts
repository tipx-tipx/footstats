import type { SkutecznoscDnia, TypyWyniki } from "./types";

/**
 * Wytnij kuchnię modelu z danych, ZANIM trafią do przeglądarki.
 *
 * Ukrycie czegoś w interfejsie nie jest ukryciem: komponent sceny jest
 * kliencki, więc wszystko, co dostanie w propsach, ląduje w źródle strony —
 * nawet jeśli nic tego nie renderuje. Przy przygotowaniu strony pod klienta
 * zewnętrznego to jest różnica między „nie pokazujemy" a „nie wysyłamy".
 *
 * Co wypada i dlaczego:
 *   diagnostyka, kupony_diag, epoki_per_rynek — narzędzia inżynierskie,
 *   po_rynku                                  — tabela „obiecywał vs weszło",
 *                                               czyli wprost miara tego, o ile
 *                                               model przeszacowuje pewność,
 *   typy z `poza_publikacja`                  — nigdy nie były na stronie,
 *                                               to nasza kontrola jakości.
 *
 * Liczniki dnia (`rozliczone`, `trafione`, `roi_flat`) zostają nietknięte —
 * one i tak NIGDY nie zawierały typów „na próbę" (patrz rozliczanie.py:
 * skutecznosc_per_dzien), więc usunięcie ich z listy nie rozjeżdża sum.
 */

function bezProbnych(dni: SkutecznoscDnia[]): SkutecznoscDnia[] {
  return dni.map((d) => ({
    ...d,
    poza_n: 0,
    poza_trafione: 0,
    typy: (d.typy ?? []).filter((t) => !t.poza_publikacja),
  }));
}

/**
 * Pola, których typ `TypyWyniki` w ogóle nie deklaruje, a które pipeline
 * wkłada do JSON-a (diagnostyka modelu). Nie widać ich w kodzie, więc tym
 * łatwiej byłoby je przeoczyć — kasujemy po nazwie.
 */
const NIEZADEKLAROWANA_KUCHNIA = ["diagnostyka", "kupony_diag"] as const;

export function okrojDlaKlienta(typy: TypyWyniki): TypyWyniki {
  const strumienie = typy.skutecznosc_strumienie;
  const out: TypyWyniki = {
    ...typy,
    po_rynku: [],
    epoki_per_rynek: undefined,
    ostatnie: (typy.ostatnie ?? []).filter((t) => !t.poza_publikacja),
    skutecznosc_dzienna: bezProbnych(typy.skutecznosc_dzienna ?? []),
    skutecznosc_strumienie: strumienie
      ? Object.fromEntries(
          Object.entries(strumienie).map(([k, s]) => [
            k,
            {
              ...s,
              dni: bezProbnych(s.dni),
              podsumowanie: { ...s.podsumowanie, poza_n: 0, poza_trafione: 0 },
            },
          ]),
        )
      : undefined,
  };
  const luzny = out as unknown as Record<string, unknown>;
  for (const pole of NIEZADEKLAROWANA_KUCHNIA) delete luzny[pole];
  return out;
}
