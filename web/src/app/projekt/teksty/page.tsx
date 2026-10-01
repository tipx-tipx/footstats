import "../atomy.css";

/*
 * Wątek „teksty” – szkic głosu marki do akceptacji (01.10). Przykłady „przed”
 * to dosłowne teksty z obecnej strony.
 */

const ZASADY: [string, string][] = [
  ["Mówimy do Ciebie", "Na „Ty”, jak kolega, który zna się na liczbach. Nie „użytkownik”, nie „klient”."],
  ["Najpierw konkret", "Liczba albo fakt na początku, wyjaśnienie po nim. „8 z 10 meczów ponad 0,5”, a nie „historia pokrycia linii wskazuje…”."],
  ["Krótko", "Jedna myśl w jednym zdaniu, do ok. 15 słów. Bez nawiasów w nawiasach i bez średników."],
  ["Słowa gracza, nie modelu", "Piszemy tak, jak mówi ktoś, kto gra u bukmachera. Nasze wewnętrzne nazwy (półka, pokrycie, próba, kalibracja) nie wychodzą na stronę."],
  ["Mocne strony na wierzchu", "Skala, serie, trafność – tam, gdzie są prawdziwe, mówimy o nich pierwsi i wprost."],
  ["Uczciwie", "Bez obietnic wygranej i bez liczb, których nie mamy. Ryzyko mówimy raz, jasno, bez straszenia. To też sprzedaje: nie chowamy przegranych."],
  ["Pusty stan i błąd", "Zawsze trzy rzeczy: co się stało, dlaczego, co możesz zrobić."],
  ["Interpunkcja", "Tylko krótkie myślniki (–) i oszczędnie. Żadnych WERSALIKÓW dla podkreślenia, żadnych wykrzykników."],
];

const SLOWNIK: [string, string][] = [
  ["okazje, pozycje, selekcje", "typy"],
  ["model / silnik wylicza", "liczymy, nasze wyliczenia"],
  ["pokrycie linii 8/10", "weszło w 8 z 10 meczów"],
  ["linia 0,5", "powyżej 0,5 (w drabince: próg)"],
  ["półka „wysoka_szansa”", "Wysokie szanse / Wyższe kursy"],
  ["EV, przewaga, value", "bukmacher płaci więcej, niż powinien"],
  ["próba, efektywna próba", "z N meczów (albo nic)"],
  ["norma ligi", "średnia w lidze"],
  ["scenariusz meczu", "kursy na sam mecz zapowiadają…"],
  ["skan, przeskanowane", "sprawdziliśmy"],
  ["rozliczenie", "wynik"],
  ["na próbę (poza listą)", "poza listą dnia"],
  ["XI, przewidywany skład", "pewny skład / przewidywany skład"],
  ["zwrot", "zwrot – nie zagrał, stawka wraca (przy pierwszym użyciu)"],
];

const PRZYKLADY: { gdzie: string; przed: string; po: string }[] = [
  {
    gdzie: "Główna, nagłówek",
    przed: "Model, który typuje za Ciebie",
    po: "Codziennie sprawdzamy ponad 1600 zakładów. Zostawiamy te, które wchodzą najczęściej.",
  },
  {
    gdzie: "Drużyny, wstęp",
    przed: "Gole, rożne i kartki drużyny – nie pojedynczych zawodników. Bierzemy 17 rozgrywek, w których mamy dość historii, żeby cokolwiek policzyć.",
    po: "Gole, rożne i kartki całych drużyn. 17 lig, które znamy najlepiej.",
  },
  {
    gdzie: "Mecze, wstęp",
    przed: "Rozkład najbliższych meczów, które model już przeskanował. Wejdź w mecz, a zobaczysz zawodników z najlepszym pokryciem linii i wszystkie okazje.",
    po: "Najbliższe mecze, które już przeliczyliśmy. Wejdź w mecz, żeby zobaczyć każdy typ.",
  },
  {
    gdzie: "Karta typu, powód",
    przed: "Średnio 5,2 na mecz (próba: 20 meczów, ostatnie 5 meczów: 6,0); po korekcie na siłę rywali i miejsce gry oraz zderzeniu krótkiej próby z normą ligi model startuje od 5,0",
    po: "Średnio 5,2 na mecz, w ostatnich 5 meczach 6,0.",
  },
  {
    gdzie: "Karta typu, powód",
    przed: "Drużyny notują przeciw Sporting Kansas City średnio 5,8 przy normie ligi 4,9 (próba: 40 meczów)",
    po: "Przeciw Sporting Kansas City rywale mają średnio 5,8 rożnych na mecz, w lidze 4,9.",
  },
  {
    gdzie: "Ostrzeżenie na karcie",
    przed: "Czerwone światło: w ostatnich 10 meczach ta linia padła mniej niż 5 razy. Historia przeczy temu typowi.",
    po: "Uwaga: w ostatnich 10 meczach weszło tylko 4 razy.",
  },
  {
    gdzie: "Sekcja pod listą",
    przed: "Czego dziś nie typujemy i dlaczego",
    po: "Co dziś odpuściliśmy i dlaczego",
  },
  {
    gdzie: "Legenda listy",
    przed: "Kropka = jak często ten typ wchodzi według nas",
    po: "(znika – szansa jest liczbą przy każdym typie)",
  },
  {
    gdzie: "Pusty filtr",
    przed: "Brak typów dla tych filtrów. Zdejmij filtr, żeby zobaczyć całą listę.",
    po: "Nic tu nie pasuje. Bez „Wkrótce” byłoby 12 typów. [Pokaż 12 typów]",
  },
  {
    gdzie: "Awaria danych",
    przed: "Nasze źródło danych nie odpowiada. Typy i wyniki poniżej pochodzą sprzed przerwy – nowe pojawią się, gdy tylko wróci.",
    po: "Chwilowo nie mamy świeżych danych. Pokazujemy typy z 21:00 – odświeżymy, gdy tylko wrócą.",
  },
];

const HASLA: string[] = [
  "Ponad 1600 zakładów sprawdzonych dziennie. Na stronę trafia kilkanaście.",
  "Każdy typ zostaje w historii – także te, które nie weszły.",
  "Widzisz, dlaczego typujemy: historia meczów i powody przy każdym typie.",
];

export default function TekstyPage() {
  return (
    <div className="p-ekran" data-p-motyw="ciemny" data-p-paleta="b1" data-p-font="2c" style={{ minHeight: "100vh" }}>
      <div className="p-tresc" style={{ maxWidth: 860 }}>
        <h1 className="p-n" style={{ fontSize: 30 }}>
          Głos FootStats
        </h1>
        <p className="p-t2" style={{ marginTop: 8, maxWidth: 620 }}>
          Szkic do akceptacji. Tak piszemy każdy tekst na stronie: nagłówki, opisy, powody przy typach, puste stany i błędy.
        </p>

        <section className="a-sekcja" style={{ borderTop: 0 }}>
          <h2 className="p-n" style={{ fontSize: 21, marginBottom: 14 }}>
            Zasady
          </h2>
          <div style={{ display: "grid", gap: 10 }}>
            {ZASADY.map(([t, o], i) => (
              <div key={t} className="a-scena" style={{ display: "grid", gridTemplateColumns: "28px 1fr", gap: 10, padding: 14 }}>
                <span className="p-t4 p-n" style={{ fontSize: 18 }}>
                  {i + 1}
                </span>
                <div>
                  <b style={{ fontWeight: 600 }}>{t}</b>
                  <p className="p-t2" style={{ marginTop: 3, fontSize: 13 }}>
                    {o}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="a-sekcja">
          <h2 className="p-n" style={{ fontSize: 21, marginBottom: 14 }}>
            Słownik zamian
          </h2>
          <div className="a-scena" style={{ padding: 0 }}>
            {SLOWNIK.map(([a, b], i) => (
              <div
                key={a}
                style={{
                  display: "grid",
                  gridTemplateColumns: "minmax(0,1fr) 24px minmax(0,1fr)",
                  gap: 8,
                  padding: "10px 14px",
                  borderTop: i ? "1px solid var(--kreska)" : 0,
                  fontSize: 13,
                }}
              >
                <span className="p-t3" style={{ textDecoration: "line-through", textDecorationColor: "var(--t4)" }}>
                  {a}
                </span>
                <span className="p-t4">→</span>
                <span style={{ fontWeight: 600 }}>{b}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="a-sekcja">
          <h2 className="p-n" style={{ fontSize: 21, marginBottom: 6 }}>
            Przed i po
          </h2>
          <p className="p-t3" style={{ fontSize: 13, marginBottom: 14 }}>
            „Przed” to dosłowne teksty z obecnej strony.
          </p>
          <div style={{ display: "grid", gap: 10 }}>
            {PRZYKLADY.map((p, i) => (
              <div key={i} className="a-scena" style={{ padding: 14, display: "grid", gap: 8 }}>
                <span className="p-t4" style={{ fontSize: 11 }}>
                  {p.gdzie}
                </span>
                <p className="p-t3" style={{ fontSize: 13, textDecoration: "line-through", textDecorationColor: "var(--t4)" }}>
                  {p.przed}
                </p>
                <p style={{ fontSize: 15, fontWeight: 600 }}>{p.po}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="a-sekcja">
          <h2 className="p-n" style={{ fontSize: 21, marginBottom: 6 }}>
            Zdania sprzedażowe – propozycje
          </h2>
          <p className="p-t3" style={{ fontSize: 13, marginBottom: 14 }}>
            Każda liczba sprawdzana na danych przed publikacją (np. „1600” to dzisiejsza liczba sprawdzonych zakładów).
          </p>
          <div style={{ display: "grid", gap: 8 }}>
            {HASLA.map((h) => (
              <div key={h} className="a-scena" style={{ padding: 14, fontSize: 16, fontWeight: 600 }}>
                {h}
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
