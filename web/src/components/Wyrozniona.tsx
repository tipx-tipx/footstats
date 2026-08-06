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
    /* `pt-2` rezerwuje miejsce na wystającą część znacznika. Bez tego znacznik
       wychodził PONAD obrys komponentu i najeżdżał na to, co stoi wyżej —
       na stronie głównej zakrywał linię „kto gra i kiedy" nad kartą
       (zgłoszenie usera 2026-08-06). */
    <div className="relative pt-2">
      {/* `top-0` + `pt-2` wpinają znacznik w krawędź karty; `z-10`, bo karta ma
          własne tło i cień. Lewy margines mija kolumnę numeru na karcie drużynowej. */}
      <span className="cut-corner-sm font-display absolute top-0 left-5 z-10 bg-brand px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest text-on-brand shadow-(--shadow-card)">
        {etykieta}
      </span>
      {children}
    </div>
  );
}
