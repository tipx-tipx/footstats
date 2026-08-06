/**
 * PIERWSZA POZYCJA MA WYGLĄDAĆ JAK PIERWSZA (2026-08-06).
 *
 * Lista typów to był szereg identycznych białych prostokątów: karta numer
 * jeden wyglądała dokładnie tak samo jak piąta. Ranking istniał (sortujemy
 * po jakości), ale nie było go widać — a lista, na której nic nie wystaje,
 * czyta się jak wygenerowana automatycznie, nie jak czyjś wybór.
 *
 * TRZECIE PODEJŚCIE, PO UWAGACH USERA. Wcześniej były dwa nieudane:
 *   1. pastylka z kropką nad kartą — kształt z co drugiego szablonu,
 *   2. kreska z wersalikami nad kartą + celownik z narożników wokół —
 *      narożniki wchodziły na napis, a etykieta stojąca OBOK karty czytała
 *      się jak podpis do sekcji, nie jak cecha tej jednej pozycji.
 *
 * Teraz znacznik jest WPIĘTY W KARTĘ: siedzi na jej górnej krawędzi, w kolorze
 * marki, ze ściętym rogiem — tym samym, który ma główny przycisk strony
 * (`cut-corner-sm`). Nic nie unosi się nad kartą i nie ma czego z czym mylić.
 *
 * CZWARTE PODEJŚCIE (2026-08-06, drugie zgłoszenie usera): wersja „wpięta
 * w krawędź" wciąż stała za blisko linii „kto gra i kiedy" nad kartą. Znacznik
 * przestaje być pozycjonowany absolutnie — to chorągiewka w NORMALNYM
 * PRZEPŁYWIE, z własnym wierszem, przyklejona do górnej krawędzi karty.
 * Ma własną wysokość w układzie, więc z niczym nie może kolidować.
 *
 * WYŁĄCZNIE przy sortowaniu „najlepsze". Przy sortowaniu po kursie albo
 * godzinie meczu „nasz typ numer 1" byłoby nieprawdą — pierwsza pozycja
 * znaczy wtedy tylko tyle, że coś musiało być pierwsze.
 */

export function Wyrozniona({
  etykieta = "nasz typ numer 1",
  children,
}: {
  etykieta?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      {/* chorągiewka w przepływie: własny wiersz, przyklejona do karty od góry
          (mt na linii wyżej robi odstęp, tu go celowo nie ma) */}
      <div className="pl-5 pt-1">
        <span className="cut-corner-sm font-display inline-block bg-brand px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest text-on-brand">
          {etykieta}
        </span>
      </div>
      {children}
    </div>
  );
}
