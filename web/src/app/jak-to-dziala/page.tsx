export const metadata = { title: "Jak to działa — FootStats" };

const KROKI = [
  {
    tytul: "Zbieramy historię",
    opis: "Dla każdego zawodnika system zna każdy mecz: ile grał minut, ile miał strzałów, fauli, odbiorów. Świeże mecze ważą więcej niż te sprzed pół roku — forma się liczy, ale nie zapominamy o dłuższej historii.",
  },
  {
    tytul: "Liczymy „prawdziwy poziom” zawodnika",
    opis: "Zawodnik po 3 meczach z dobrymi liczbami to często przypadek. Model porównuje go z podobnymi zawodnikami (ta sama pozycja i rola) i ostrożnie przesuwa ocenę w stronę jego wyników dopiero wtedy, gdy danych przybywa. Dzięki temu nie daje się nabrać na chwilowe wystrzały.",
  },
  {
    tytul: "Przewidujemy minuty",
    opis: "Ta sama skuteczność przy 90 i przy 60 minutach to zupełnie inna szansa na „powyżej 1,5 strzału”. Model rozważa scenariusze: pełny mecz, zejście w 70. minucie, wejście z ławki, brak występu — i waży je szansami. Po ogłoszeniu oficjalnych składów przelicza wszystko od nowa.",
  },
  {
    tytul: "Uwzględniamy kontekst meczu",
    opis: "Przeciwnik, który pozwala rywalom dużo strzelać, podbija szansę na strzały. Sędzia, który gwiżdże 30% więcej fauli niż średnia, podbija rynki fauli i kartek. Mecz u siebie, spodziewany przebieg gry — każdy czynnik to osobna, ograniczona korekta, którą widzisz w uzasadnieniu zakładu.",
  },
  {
    tytul: "Zamieniamy to na szansę i uczciwy kurs",
    opis: "Model daje pełen rozkład: jaka szansa na 0, 1, 2, 3… zdarzeń. Z tego wprost wynika szansa „powyżej linii” i uczciwy kurs (odwrotność szansy). Przykład: szansa 58% → uczciwy kurs 1,72.",
  },
  {
    tytul: "Porównujemy z kursem bukmachera",
    opis: "Z kursu bukmachera zdejmujemy jego marżę i sprawdzamy, co naprawdę „mówi” o szansie. Jeśli bukmacher wycenia zdarzenie na 45%, a model na 58% — kurs płaci za dużo. To jest właśnie okazja (value bet).",
  },
  {
    tytul: "Oceniamy pewność i ryzyko",
    opis: "Pewność mówi, ile danych i jak stabilnych stoi za predykcją (mała próba, niepewne minuty = niska pewność). Ryzyko mówi, jak kapryśne jest samo zdarzenie — rzadkie zdarzenia (np. strzały głową) to loteria nawet przy dobrym modelu. Wysokiej wartości bez pewności nie traktujemy poważnie.",
  },
  {
    tytul: "Sprawdzamy sami siebie",
    opis: "Zakładka „Skuteczność modelu” to test na meczach, których model nie widział podczas nauki. Jeśli mówi „60%”, a zdarzenia zachodzą w 60% przypadków — możesz mu ufać. A Twój dziennik zakładów z CLV pokazuje, czy realnie wyprzedzasz rynek.",
  },
];

export default function JakToDzialaPage() {
  return (
    <div className="pt-10">
      <h1 className="text-2xl font-bold">Jak to działa</h1>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
        Bez żargonu: co się dzieje między „mecz w sobotę" a „ten kurs jest
        zawyżony". Osiem kroków — dokładnie w tej kolejności wykonuje je
        system dla każdego zawodnika i każdego rynku.
      </p>

      <ol className="mt-8 max-w-3xl space-y-4">
        {KROKI.map((k, i) => (
          <li
            key={k.tytul}
            className="flex gap-4 rounded-(--radius-card) border border-hairline bg-card p-5 shadow-(--shadow-card)"
          >
            <span
              aria-hidden
              className="font-data flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-wash text-sm font-semibold text-brand"
            >
              {i + 1}
            </span>
            <div>
              <h2 className="font-semibold">{k.tytul}</h2>
              <p className="mt-1 text-sm leading-relaxed text-ink-soft">
                {k.opis}
              </p>
            </div>
          </li>
        ))}
      </ol>

      <div className="mt-10 max-w-3xl rounded-(--radius-card) border border-data-amber/40 bg-data-amber-wash p-5 text-sm leading-relaxed text-[#6d4410]">
        <h2 className="font-semibold">Uczciwe zastrzeżenie</h2>
        <p className="mt-1">
          Model nie zna kontuzji ogłoszonej godzinę temu, konfliktu w szatni
          ani planów trenera. Dlatego nigdy nie pokazujemy zakładów, w których
          model drastycznie nie zgadza się z rynkiem — najczęściej to rynek
          wie coś, czego nie wie model. Wartość dodatnia w długiej serii, a
          nie pojedynczy „pewniak", jest celem tego narzędzia.
        </p>
      </div>
    </div>
  );
}
