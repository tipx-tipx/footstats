import type { Odrzucenie } from "@/lib/types";
import { etykietaPowodu, grupyOdrzucen } from "@/lib/odrzucenia";

/**
 * „CZEGO NIE TYPUJEMY I DLACZEGO" — sekcja, która była tylko na stronie meczu.
 *
 * PO CO NA DRUŻYNACH (przegląd sprzedażowy 05.08). Lista pokazuje, co model
 * wystawił, i milczy o tym, czego świadomie NIE wystawił. Dla kupującego to
 * różnica między „przejrzeliśmy wszystko i tyle przeszło" a „tyle znaleźliśmy" —
 * pierwsze jest argumentem za produktem, drugie brzmi jak słaby dzień.
 * Uczciwość liczbowa działa tu tak samo jak przy historii kuponów: „4 z 6"
 * buduje więcej zaufania niż „6 z 6".
 *
 * Świadomie BEZ nazwisk i wyliczanek — powód i liczba niosą treść, a lista
 * dwustu nazw byłaby ścianą tekstu (tak jest też na stronie meczu).
 */
export function CzegoNieTypujemy({
  odrzucenia,
  tytul = "Czego dziś nie typujemy i dlaczego",
}: {
  odrzucenia: Odrzucenie[];
  tytul?: string;
}) {
  if (odrzucenia.length === 0) return null;
  const grupy = grupyOdrzucen(odrzucenia);
  return (
    <details className="group border-y border-hairline">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 py-3.5 text-sm font-semibold [&::-webkit-details-marker]:hidden">
        <span>
          {tytul}
          <span className="font-data ml-2 text-xs font-normal text-faint">
            {odrzucenia.length} sprawdzonych bez typu
          </span>
        </span>
        <svg
          aria-hidden
          width="14"
          height="14"
          viewBox="0 0 14 14"
          className="shrink-0 text-faint transition-transform group-open:rotate-180"
        >
          <path
            d="M3 5.5 L7 9.5 L11 5.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </summary>
      <div className="space-y-4 border-t border-hairline py-4">
        <p className="text-xs leading-relaxed text-muted">
          Model liczy każdą drużynę i każdy rynek osobno. Gdy typu nie ma, to
          nie przeoczenie – poniżej powód dla każdej sprawdzonej pary.
        </p>
        {grupy.map(([powod, wpisy]) => (
          <div key={powod}>
            <div className="flex items-baseline justify-between gap-4 border-b border-hairline pb-1">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">
                {etykietaPowodu(powod)}
              </p>
              <span className="font-data shrink-0 text-sm font-semibold text-ink-soft">
                {wpisy.length}
              </span>
            </div>
            <p className="mt-1.5 text-xs leading-relaxed text-faint">
              {wpisy
                .slice(0, 6)
                .map((w) => `${w.podmiot} (${w.rynek.toLowerCase()})`)
                .join(", ")}
              {wpisy.length > 6 && ` i ${wpisy.length - 6} więcej`}
            </p>
          </div>
        ))}
      </div>
    </details>
  );
}
