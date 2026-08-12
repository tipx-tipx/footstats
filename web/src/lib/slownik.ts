/**
 * SŁOWNIK PRODUKTU – jedno miejsce, w którym liczby modelu zamieniają się
 * w polskie zdania.
 *
 * Powstał 2026-08-01 z przeglądu kart (Drabinki + Drużyny). Trzy rzeczy,
 * które ten plik naprawia u źródła:
 *
 *  1. TA SAMA RZECZ NAZYWANA RÓŻNIE. Karta Drabinek oceniała typ jako
 *     „TOP / mocny / solidny", lista drużyn jako „pewniak / perełka",
 *     a rozwinięcie jeszcze raz, własną czterostopniową skalą. Trzy słowniki
 *     na jedną rzecz – nikt z zewnątrz nie zgadnie, czy „mocny" to więcej
 *     czy mniej niż „pewniak".
 *
 *  2. SŁOWO „PEWNIAK" (decyzja usera 2026-08-01: znika z całej strony).
 *     Obiecywało pewność, której nie mamy – a produkt stoi na tym, że mówimy
 *     prawdę o szansach. Zastąpione opisem tego, co liczba naprawdę znaczy.
 *
 *  3. MNOŻNIK ×1,12. Kolumna liczb bez jednostki i bez kierunku; żeby
 *     cokolwiek z niej wyczytać, trzeba wiedzieć, że 1,00 znaczy „bez
 *     wpływu". To wiedza wewnętrzna, nie treść dla użytkownika.
 */

import { fmtKurs, fmtProc } from "./format";

/* ------------------------------------------------------------------ *
 * SIŁA TYPU – JEDYNA skala w całym produkcie
 * ------------------------------------------------------------------ */

/**
 * Cztery stopnie po samej szansie. Progi zostały te, co były (75 / 62 / 52),
 * bo są zestrojone z widełkami publikacji – zmieniają się TYLKO nazwy.
 *
 * Etykieta mówi wprost, o czym jest liczba: o szansie. Poprzednie nazwy
 * („pewniak", „mocny typ") oceniały typ, choć liczba opisywała wyłącznie
 * prawdopodobieństwo – i to właśnie brało się za obietnicę.
 */
export const SILA_TYPU = [
  {
    kod: "niska",
    label: "niska szansa",
    zakres: "poniżej 52%",
    od: 0,
    do: 0.52,
    cls: "bg-paper text-muted",
    opis: "Szansa poniżej 52%, czyli niewiele lepiej niż rzut monetą. Taki typ ma sens tylko przy wyraźnie wyższym kursie.",
  },
  {
    kod: "umiarkowana",
    label: "umiarkowana szansa",
    zakres: "52–61%",
    od: 0.52,
    do: 0.62,
    cls: "bg-paper text-muted",
    opis: "Szansa 52–61%. Wchodzi częściej, niż nie wchodzi, ale bez zapasu.",
  },
  {
    kod: "wysoka",
    label: "wysoka szansa",
    zakres: "62–74%",
    od: 0.62,
    do: 0.75,
    cls: "bg-data-green-wash text-data-green-ink",
    opis: "Szansa 62–74%. Solidny typ, choć kurs bywa za niski, żeby to się opłacało.",
  },
  {
    kod: "bardzo-wysoka",
    label: "bardzo wysoka szansa",
    zakres: "75% i więcej",
    od: 0.75,
    do: 1.01,
    cls: "bg-brand-wash text-brand-deep",
    opis: "Szansa 75% i więcej – najczęściej wchodzący rodzaj typu. Uwaga: przy takich szansach kursy są niskie, więc sama częstotliwość trafień nie oznacza zysku.",
  },
] as const;

export type SilaTypu = (typeof SILA_TYPU)[number];

/* ------------------------------------------------------------------ *
 * PRZEWAGA W CENIE – to, co niesie kropka przy wierszu
 * ------------------------------------------------------------------ */

/**
 * KROPKA MUSI COŚ ZNACZYĆ (decyzja usera 2026-08-02).
 *
 * Poprzednia wersja odpowiadała na pytanie „czy historia zgadza się z tym
 * typem": zielona, gdy linia padła w ≥65% z ostatnich 10 meczów. Trzy powody,
 * dla których to nie działało:
 *
 *  1. NAJCZĘŚCIEJ JEJ NIE BYŁO – 11 z 16 typów miało szarą kropkę, bo dla
 *     sum meczowych („rożne w meczu") nie ma czegoś takiego jak forma jednej
 *     drużyny, a typy wznowione traciły historię między cyklami,
 *  2. CZERWONA PODWAŻAŁA NASZ WŁASNY TYP – „historia przeczy temu typowi"
 *     przy zakładzie, który sami polecamy, jest nie do obrony,
 *  3. odpowiadała na pytanie, którego nikt nie zadaje.
 *
 * Teraz kropka mówi, O ILE KURS BIJE NASZĄ WYCENĘ. Liczona z pól, które ma
 * KAŻDY typ (szansa i kurs), więc nigdy nie jest pusta; jest powodem, dla
 * którego typ w ogóle trafił na listę; i nigdy nie przeczy produktowi –
 * słabsza przewaga to nie „zły typ", tylko inny rodzaj typu.
 *
 * BRUTTO, NIE NETTO (decyzja usera): interesuje nas kurs, podatek jest
 * dodatkiem i zostaje przypisem na karcie.
 *
 * Oś jest NIEZALEŻNA od podziału listy: półka mówi, jaki to rodzaj zakładu,
 * kropka – jak dobra jest cena.
 */
// ⚑ KROPKA MÓWI O SZANSIE, NIE O PRZEWADZE W CENIE (2026-08-13).
//
// Do 13.08 progi liczyły się z `ev_pct`: „kurs płaci 15% ponad naszą wycenę".
// Odkąd szansa pokazywana jest ściągana do uczciwej ceny (backend:
// `rozliczanie.marza_sciagania`), różnica między kursem a naszą wyceną to po
// prostu marża bukmachera — praktycznie taka sama przy każdym typie. Skutek
// na produkcji: wszystkie 31 typów dostawało kropkę „cienka przewaga", czyli
// kolumna widoczna w KAŻDYM wierszu przestała cokolwiek odróżniać.
//
// Progi szansy są te same, co w podziale listy na półki, żeby kropka i
// etykieta nie mówiły dwóch różnych rzeczy o tym samym typie.
export const PRZEWAGA_KROPKI = [
  {
    kod: "mocna",
    label: "duża szansa",
    opis: "Nasza liczba daje temu zdarzeniu co najmniej 65% szans na wejście.",
    od: 65,
  },
  {
    kod: "jest",
    label: "średnia szansa",
    opis: "Nasza liczba daje temu zdarzeniu 52–65% szans – najczęstszy typ na liście.",
    od: 52,
  },
  {
    kod: "cienka",
    label: "niższa szansa, wyższy kurs",
    opis: "Poniżej połowy szans, za to kurs płaci wyraźnie więcej. Świadome ryzyko.",
    od: -Infinity,
  },
] as const;

export type PrzewagaKropki = (typeof PRZEWAGA_KROPKI)[number];

/** Kropka dla typu – z szansy pokazywanej na karcie (ta sama liczba co w wierszu). */
export function przewagaKropki(bet: {
  p_model?: number | null;
}): PrzewagaKropki {
  const p = (bet.p_model ?? 0) * 100;
  return PRZEWAGA_KROPKI.find((k) => p >= k.od) ?? PRZEWAGA_KROPKI[2];
}

/** Klasy kropki: pełna / obwódka / cienka obwódka – ta sama skala co wyżej. */
export const KROPKA_STYL: Record<string, string> = {
  mocna: "bg-data-green",
  jest: "border-2 border-data-green bg-transparent",
  cienka: "border border-hairline-strong bg-transparent",
};

export function silaTypu(p: number): SilaTypu {
  return SILA_TYPU.find((s) => p >= s.od && p < s.do) ?? SILA_TYPU[0];
}

/**
 * PROFIL TYPU – druga, NIEZALEŻNA oś: nie „jak mocny", tylko „jak
 * postawiony". Dawne „perełka" i „wyższa linia" mówiły dokładnie to samo
 * (poprzeczka wyżej, kurs lepszy, szansa niższa) dwiema różnymi nazwami.
 *
 * Zwraca null, gdy typ jest zwykły – plakietka pojawia się tylko wtedy,
 * gdy naprawdę coś zmienia.
 */
export function profilTypu(bet: {
  wyzsza_linia?: boolean;
  kurs?: number | null;
  p_model: number;
}): { label: string; cls: string; opis: string } | null {
  if (bet.wyzsza_linia) {
    return {
      label: "wyżej postawiona poprzeczka",
      cls: "bg-data-amber-wash text-data-amber-ink",
      opis: "Ten sam zawodnik i ten sam rynek, ale linia postawiona wyżej niż zwykle. Wchodzi rzadziej, płaci wyraźnie więcej.",
    };
  }
  if (bet.p_model < 0.52 && (bet.kurs ?? 0) >= 1.9) {
    return {
      label: "wyższy kurs",
      cls: "bg-data-amber-wash text-data-amber-ink",
      opis: "Szansa poniżej połowy, ale kurs na tyle wysoki, że przy dłuższej serii to się broni. Świadome ryzyko, nie wpadka.",
    };
  }
  return null;
}

/**
 * CHARAKTER SZCZEBLA drabinki – opis JEDNEJ linii, nie ocena całego typu.
 *
 * PODPIS MÓWI O CENIE, NIE O RYZYKU (decyzja usera 2026-08-01). Wcześniej
 * było „wysoka szansa / realne / ryzykowne" i to nie działało: dolnych
 * szczebli zawsze będzie najwięcej, więc drabinka w kółko krzyczała
 * „ryzykowne" – choć wyższa poprzeczka nie jest wpadką, tylko innym
 * wyborem: mniej pewności, więcej wypłaty.
 *
 * Liczymy z KURSU, nie z naszej szansy. Podpis wzięty z szansy potrafiłby
 * przeczyć cenie stojącej dwa wiersze wyżej w tej samej komórce (typ
 * z niską szansą i niskim kursem istnieje – to po prostu zły typ).
 */
export function charakterSzczebla(kurs: number | null | undefined): string | null {
  if (kurs == null || kurs <= 1) return null;
  if (kurs < 1.6) return "niski kurs";
  if (kurs < 2.5) return "średni kurs";
  return "wysoki kurs";
}

/* ------------------------------------------------------------------ *
 * MNOŻNIKI – kierunek słowem, liczba jako przypis
 * ------------------------------------------------------------------ */

/**
 * ×1,12 -> „podnosi". Siedem stopni, bo mniej gubi różnicę między „ledwie
 * drgnęło" a „przewróciło rachunek do góry nogami".
 */
export function kierunekMnoznika(m?: number | null): string {
  if (m == null || Math.abs(m - 1) < 0.02) return "bez zmian";
  if (m >= 1.25) return "mocno podnosi";
  if (m >= 1.08) return "podnosi";
  if (m > 1) return "lekko podnosi";
  if (m <= 0.8) return "mocno obniża";
  if (m <= 0.93) return "obniża";
  return "lekko obniża";
}

/** Kolor kierunku – zielony w górę, bursztyn w dół, szary bez zmian. */
export function klasaKierunku(m?: number | null): string {
  if (m == null || Math.abs(m - 1) < 0.02) return "text-faint";
  return m > 1 ? "text-data-green-ink" : "text-data-amber-ink";
}

/* ------------------------------------------------------------------ *
 * LICZBY -> ZDANIA
 * ------------------------------------------------------------------ */

const przecinek = (v: number, cyfry = 1) =>
  v.toFixed(cyfry).replace(".", ",");

/** „1,8/90" -> „średnio 1,8 na mecz". */
export function naMecz(v: number, prefiks = "średnio "): string {
  return `${prefiks}${przecinek(v)} na mecz`;
}

/** „8/10" -> „przebił tę linię w 8 z 10 ostatnich meczów". */
export function trafioneZ(traf: number, z: number, co = "przebił tę linię"): string {
  return `${co} w ${traf} z ${z} ostatnich meczów`;
}

/**
 * „+6 pkt proc." -> „kurs wyceniony jak na 51%, my dajemy 57%".
 *
 * Punkt procentowy to pojęcie, którego większość ludzi nie odróżnia od
 * procenta – a tu akurat różnica jest sednem. Więc zamiast nazwy jednostki
 * pokazujemy obie liczby obok siebie i zostawiamy porównanie oczom.
 */
export function szansaWobecKursu(
  p: number,
  kurs: number,
): { zdanie: string; przewaga: number | null } {
  if (!kurs || kurs <= 1) return { zdanie: `dajemy temu ${fmtProc(p)}`, przewaga: null };
  const cena = 1 / kurs;
  return {
    zdanie: `kurs ${fmtKurs(kurs)} jest wyceniony jak na ${fmtProc(cena)}, my dajemy ${fmtProc(p)}`,
    przewaga: Math.round((p - cena) * 100),
  };
}

/**
 * „#3 z 18 w lidze" -> „3. najszczelniejsza drużyna w lidze (z 18)".
 *
 * Sama liczba porządkowa była pułapką: miejsce 1 ma drużyna, która pozwala
 * NAJMNIEJ – i to zdanie siedziało w dymku, którego na telefonie nie ma.
 */
export function miejsceWLidze(rank: number, z: number): string {
  return `${rank}. najszczelniejsza w lidze na tym rynku (z ${z} drużyn)`;
}

/**
 * Ile realnie wraca ze stawki. `kursNetto` liczymy tu sami, bo `podatek.ts`
 * operuje na całych rekordach typu, a tu mamy same liczby.
 */
export function zeStawki(
  p: number,
  kurs: number,
  stawka = 10,
  wspPodatku = 0.88,
): string {
  const zwrot = p * kurs * wspPodatku * stawka;
  return `postawione ${stawka} zł wraca średnio jako ${przecinek(zwrot, 2)} zł`;
}
