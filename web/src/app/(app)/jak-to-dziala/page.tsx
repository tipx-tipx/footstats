import { PageHeader } from "@/components/PageHeader";
import { Reveal } from "@/components/Reveal";

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
    tytul: "Przewidujemy minuty i składy",
    opis: "Ta sama skuteczność przy 90 i przy 60 minutach to zupełnie inna szansa na „powyżej 1,5 strzału”. Model rozważa scenariusze: pełny mecz, zejście w 70. minucie, wejście z ławki, brak występu. Przewidywane jedenastki bierzemy z dwóch niezależnych źródeł, a po ogłoszeniu oficjalnych składów wszystko przeliczamy od nowa.",
  },
  {
    tytul: "Uwzględniamy kontekst i strony boiska",
    opis: "Przeciwnik, który pozwala rywalom dużo strzelać, podbija szansę na strzały. Sędzia gwiżdżący 30% więcej fauli podbija rynki fauli i kartek. Skrzydłowy grający na najczęściej faulującego obrońcę dostaje bonus do fauli wywalczonych. Każdy czynnik to osobna, ograniczona korekta, którą widzisz w uzasadnieniu zakładu.",
  },
  {
    tytul: "Zamieniamy to na szansę i uczciwy kurs",
    opis: "Model daje pełen rozkład: jaka szansa na 0, 1, 2, 3… zdarzeń. Z tego wprost wynika szansa „powyżej linii” i uczciwy kurs (odwrotność szansy). Przykład: szansa 58% → uczciwy kurs 1,72.",
  },
  {
    tytul: "Porównujemy z kursem bukmachera",
    opis: "Z kursu bukmachera zdejmujemy jego marżę i sprawdzamy, co naprawdę „mówi” o szansie. Jeśli bukmacher wycenia zdarzenie na 45%, a model na 58% — kurs płaci za dużo. Dodatkowo patrzymy na średnią bukmacherów zagranicznych: kurs wyraźnie odstający od reszty rynku to często najlepszy sygnał.",
  },
  {
    tytul: "Oceniamy pewność i ryzyko",
    opis: "Pewność mówi, ile danych i jak stabilnych stoi za predykcją (mała próba, niepewne minuty = niska pewność). Ryzyko mówi, jak kapryśne jest samo zdarzenie — rzadkie zdarzenia (np. strzały głową) to loteria nawet przy dobrym modelu. Wysokiej wartości bez pewności nie traktujemy poważnie.",
  },
  {
    tytul: "Sprawdzamy sami siebie",
    opis: "Zakładka „Skuteczność” to test na meczach, których model nie widział podczas nauki. Jeśli mówi „60%”, a zdarzenia zachodzą w 60% przypadków — możesz mu ufać. A Twój dziennik zakładów z CLV pokazuje, czy realnie wyprzedzasz rynek.",
  },
];

export default function JakToDzialaPage() {
  return (
    <div>
      <PageHeader
        eyebrow="metoda"
        title="Jak to działa"
        lead={
          <>
            Bez żargonu: co się dzieje między „mecz w sobotę” a „ten kurs jest
            zawyżony”. Osiem kroków — dokładnie w tej kolejności system
            wykonuje je dla każdego zawodnika i każdego rynku.
          </>
        }
      />

      <ol className="relative mt-9 max-w-3xl space-y-5">
        {/* linia łącząca kroki */}
        <span
          aria-hidden
          className="absolute bottom-8 left-[19px] top-8 w-px bg-hairline-strong"
        />
        {KROKI.map((k, i) => (
          <Reveal key={k.tytul} delay={Math.min(i * 0.04, 0.2)}>
            <li className="relative flex gap-5">
              <span
                aria-hidden
                className="font-data relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-brand/25 bg-brand-wash text-sm font-semibold text-brand shadow-(--shadow-card)"
              >
                {i + 1}
              </span>
              <div className="rounded-2xl border border-hairline bg-card p-5 shadow-(--shadow-card)">
                <h2 className="font-semibold">{k.tytul}</h2>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">
                  {k.opis}
                </p>
              </div>
            </li>
          </Reveal>
        ))}
      </ol>

      <Reveal className="mt-10">
        <div className="max-w-3xl rounded-2xl border border-data-amber/40 bg-data-amber-wash p-5 text-sm leading-relaxed text-[#6d4410]">
          <h2 className="font-semibold">Uczciwe zastrzeżenie</h2>
          <p className="mt-1">
            Model nie zna kontuzji ogłoszonej godzinę temu, konfliktu w szatni
            ani planów trenera. Dlatego nigdy nie pokazujemy zakładów, w których
            model drastycznie nie zgadza się z rynkiem — najczęściej to rynek
            wie coś, czego nie wie model. Wartość dodatnia w długiej serii, a
            nie pojedynczy „pewniak”, jest celem tego narzędzia.
          </p>
        </div>
      </Reveal>
    </div>
  );
}
