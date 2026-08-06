/**
 * PIERWSZA POZYCJA MA WYGLĄDAĆ JAK PIERWSZA (2026-08-06).
 *
 * Lista typów to był szereg identycznych białych prostokątów: karta numer
 * jeden wyglądała dokładnie tak samo jak piąta. Ranking istniał (sortujemy
 * po jakości), ale nie było go widać — a lista, na której nic nie wystaje,
 * czyta się jak wygenerowana automatycznie, nie jak czyjś wybór.
 *
 * Produkt, który ma opinię, pokazuje ją układem. Stąd ta ramka: plakietka
 * z numerem i celownik z narożników — TEN SAM motyw, co wokół karty
 * w nagłówku strony (patrz `ZywyPodglad` w Hero). Dwa użycia robią z niego
 * język marki; jedno byłoby ozdobą.
 *
 * WYŁĄCZNIE przy sortowaniu „najlepsze". Przy sortowaniu po kursie albo
 * godzinie meczu „nasz typ numer 1" byłoby nieprawdą — pierwsza pozycja
 * znaczy wtedy tylko tyle, że coś musiało być pierwsze.
 */

const ROGI = [
  "left-0 top-0 border-l-2 border-t-2",
  "right-0 top-0 border-r-2 border-t-2",
  "bottom-0 left-0 border-b-2 border-l-2",
  "bottom-0 right-0 border-b-2 border-r-2",
];

export function Wyrozniona({
  etykieta = "nasz typ numer 1",
  children,
}: {
  etykieta?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="relative">
      {/* KRESKA I WERSALIKI, NIE PASTYLKA Z KROPKĄ (poprawka 06.08).
          Pierwsza wersja miała zaokrągloną plakietkę z kropką — kształt,
          który stoi w co drugim szablonie i nie ma nic wspólnego z resztą
          tej strony. Tu wszystkie nagłówki sekcji wyglądają tak samo:
          krótka kreska marki i wersaliki („— KUPON NA DZIŚ", „— WERDYKT").
          Odstęp `mb-3` jest większy niż wysunięcie narożników (`-inset-2`),
          więc celownik nie wchodzi już na napis. */}
      <p className="font-display mb-3 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-brand">
        <span aria-hidden className="h-px w-5 bg-brand-bright" />
        {etykieta}
      </p>
      <div className="relative">
        {/* celownik jak w nagłówku strony – dekoracja, więc nie rusza układu */}
        <span aria-hidden className="pointer-events-none absolute -inset-2 z-10">
          {ROGI.map((rog) => (
            <span
              key={rog}
              className={`absolute h-4 w-4 border-brand-bright ${rog}`}
            />
          ))}
        </span>
        {children}
      </div>
    </div>
  );
}
