"use client";

import { useMemo, useState } from "react";

import { TabelaTypow } from "./WierszTypu";
import { useBilans } from "../useBilans";
import { fmtDzien, odmien } from "@/lib/format";
import type { Ekran, SkutecznoscDnia, TypRozliczony } from "@/lib/types";
import { odmienLinie } from "@/lib/warianty";

/**
 * Panel JEDNEGO DNIA – pod kalendarzem, zawsze otwarty na którymś dniu.
 *
 * Jedna oś czasu, dwa sposoby ruszania się po niej: kliknięcie w kafelek
 * (skok w konkretną datę) i strzałki tutaj (krok po kolejnych dniach
 * z rozliczeniami). To NIE jest dawny osobny pager z własnej zakładki –
 * obie drogi ustawiają ten sam wybór, a kalendarz przewija się za nim, więc
 * podświetlony kafelek zawsze odpowiada temu, co widać niżej.
 *
 * Filtr wyniku pojawia się dopiero przy dłuższej liście: przy trzech typach
 * jest szumem, przy trzydziestu – jedynym sposobem, żeby szybko zobaczyć,
 * co konkretnie nie weszło.
 */

type Filtr = "wszystko" | "weszly" | "nie";

/**
 * TRZY POZIOMY WIDOCZNOŚCI (decyzja usera 2026-08-02: „niech się wyświetla
 * dokładnie to, co jest pokazywane w wysoka szansa/drużyny/drabinki; co jest
 * dodatkowo, to nie tym samym kolorem").
 *
 * Kolor przestaje znaczyć „wygrał czy przegrał" – to mówi już kolumna wyniku –
 * a zaczyna znaczyć CZY TO WIDZIAŁEŚ. Bo tylko to rozstrzyga, czy dana liczba
 * jest oceną produktu, czy pomiarem w tle:
 *
 *   1 — stał na TEJ zakładce; to jest wynik, o który pytasz,
 *   2 — był na stronie, ale gdzie indziej (np. typ zawodniczy bez znacznika
 *       „wysoka szansa”, którego od 1 sierpnia nie listuje żadna zakładka),
 *   3 — nigdy nie był na stronie: policzony „na próbę”, uczy model w tle.
 *
 * Rekord BEZ stempla (sprzed 2026-08-02) dostaje poziom 1 i osobny przypis –
 * nie wiemy o nim, że stał gdzie indziej, więc nie wolno go za to karać.
 */
export type Poziom = 1 | 2 | 3;

const EKRAN_STRUMIENIA: Record<string, Ekran> = {
  pewniaki: "wysokie_szanse",
  druzyny: "druzyny",
  drabinki: "drabinki",
};

export function poziomTypu(t: TypRozliczony, wybor: string): Poziom {
  if (t.poza_publikacja) return 3;
  if (!t.ekran) return 1;
  if (wybor === "wszystko") return t.ekran === "poza_lista" ? 2 : 1;
  return t.ekran === EKRAN_STRUMIENIA[wybor] ? 1 : 2;
}

/** Czemu ten wiersz jest przygaszony – jedno zdanie, bez żargonu. */
const OPIS_POZIOMU_2 =
  "Ten typ był policzony i rozliczony, ale nie stał na tej zakładce – " +
  "typy zawodnicze bez znacznika „wysoka szansa” nie mają od 1 sierpnia " +
  "własnej listy. Nie liczymy ich do wyniku powyżej.";

const FILTRY: { kod: Filtr; label: string }[] = [
  { kod: "wszystko", label: "Wszystkie" },
  { kod: "weszly", label: "Weszły" },
  { kod: "nie", label: "Nie weszły" },
];

/** Od tylu typów w dniu filtr zaczyna się opłacać. */
const PROG_FILTRA = 8;

/**
 * ZAKŁAD, a nie wiersz. Ten sam mecz + rynek + drużyna + strona to jedna
 * rzecz, choćby stała w kilku liniach:
 *
 *   Wisła Płock  rożne w meczu poniżej  6,5 / 7,5 / 13,5 / 14,5 / 15,5
 *
 * Padło 11 rożnych – trzy ostatnie wchodzą RAZEM. Zgłoszenie usera
 * 2026-08-01 („czemu tu jest miliard typów?") dotyczyło dokładnie tego.
 * Publikacja wystawia od tej pory jedną linię na stronę, ale w księdze
 * zostają dni sprzed zmiany – i one nadal mają się czytać uczciwie.
 */
function kluczZakladu(t: {
  mecz: string;
  rynek_kod: string;
  podmiot: string;
  strona: string;
}) {
  return `${t.mecz}|${t.rynek_kod}|${t.podmiot}|${t.strona}`;
}

function Strzalka({
  kierunek,
  onClick,
  tytul,
}: {
  kierunek: "lewo" | "prawo";
  onClick?: () => void;
  tytul: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      aria-label={tytul}
      title={tytul}
      className="flex h-7 w-7 items-center justify-center rounded-(--radius-control) border border-hairline text-ink-soft transition-colors hover:border-brand hover:text-brand disabled:cursor-default disabled:opacity-35 disabled:hover:border-hairline disabled:hover:text-ink-soft"
    >
      <svg
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        aria-hidden
      >
        <path
          d={kierunek === "lewo" ? "M15 5l-7 7 7 7" : "M9 5l7 7-7 7"}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
}

export function TypyDnia({
  dzien,
  starszy,
  nowszy,
  pozycja,
  ile,
  pelnyWglad = true,
  wybor = "wszystko",
}: {
  dzien: SkutecznoscDnia;
  /** false = widok klienta: bez typów liczonych „na próbę" */
  pelnyWglad?: boolean;
  /** wybrany produkt z góry strony – decyduje, który ekran jest poziomem 1 */
  wybor?: string;
  /** krok do dnia WCZEŚNIEJSZEGO; brak = to najstarszy dzień */
  starszy?: () => void;
  /** krok do dnia PÓŹNIEJSZEGO; brak = to najnowszy dzień */
  nowszy?: () => void;
  pozycja?: number;
  ile?: number;
}) {
  const { bilans } = useBilans(pelnyWglad);
  const [filtr, setFiltr] = useState<Filtr>("wszystko");
  // Typy „na próbę" nie były na stronie i mają własne podsumowanie zdaniem
  // niżej – ZWINIĘTE domyślnie, bo potrafią zająć połowę listy (zmierzone
  // 2026-08-01: 27 z 60 ostatnich rozliczeń).
  const [pokazNaProbe, setPokazNaProbe] = useState(false);
  // `?? []` w ciele komponentu tworzyłoby nową tablicę co render i unieważniało
  // useMemo niżej przy każdym przerysowaniu
  // typy z INNEJ zakładki (poziom 2) też schodzą pod przycisk – inaczej lista
  // „Wysokich szans" pokazywałaby typy, których na tej zakładce nie było
  const [pokazInne, setPokazInne] = useState(false);
  const typy = useMemo(
    () =>
      (dzien.typy ?? []).filter((t) => {
        const p = poziomTypu(t, wybor);
        if (p === 3) return pelnyWglad && pokazNaProbe;
        if (p === 2) return pokazInne;
        return true;
      }),
    [dzien.typy, pelnyWglad, pokazNaProbe, pokazInne, wybor],
  );
  // ile jest poziomu 2 (niezależnie od tego, czy rozwinięte)
  const innaZakladka = useMemo(
    () => (dzien.typy ?? []).filter((t) => poziomTypu(t, wybor) === 2),
    [dzien.typy, wybor],
  );
  // LICZBA, nie flaga — patrz zdanie niżej. „Część" przy 42 z 43 kłamie.
  const bezStempla = useMemo(
    () => (dzien.typy ?? []).filter((t) => !t.ekran || t.ekran_odtworzony).length,
    [dzien.typy],
  );

  const widoczne = useMemo(
    () =>
      typy.filter((t) =>
        filtr === "weszly"
          ? t.wynik === "wygrany"
          : filtr === "nie"
            ? t.wynik === "przegrany"
            : true,
      ),
    [typy, filtr],
  );

  // ile z tych wierszy to naprawdę osobne zakłady (patrz `kluczZakladu`)
  const zakladow = useMemo(
    () => new Set(widoczne.map(kluczZakladu)).size,
    [widoczne],
  );

  const proc = dzien.rozliczone
    ? Math.round((dzien.trafione / dzien.rozliczone) * 100)
    : 0;

  return (
    <div className="rounded-(--radius-card) border border-hairline bg-card p-4 shadow-(--shadow-card) sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <h4 className="font-display text-base font-bold tracking-tight first-letter:uppercase">
            {fmtDzien(dzien.dzien, true)}
          </h4>
          {/* bilans dnia to widok pełny — użytkownik czyta ten sam dzień
              w typach, tak jak resztę zakładki (06.08) */}
          <p className="mt-0.5 text-xs text-muted">
            <span className="font-data font-semibold text-ink">
              {dzien.trafione}/{dzien.rozliczone}
            </span>{" "}
            weszło ({proc}%)
            {pelnyWglad && (
              <>
                {" "}· bilans{" "}
                <span
                  className={`font-data font-semibold ${
                    dzien.roi_flat > 0
                      ? "text-data-green"
                      : dzien.roi_flat < 0
                        ? "text-data-red"
                        : "text-ink-soft"
                  }`}
                >
                  {bilans(dzien.roi_flat)}
                </span>{" "}
                · {dzien.okazje} z kursem
              </>
            )}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {pozycja != null && ile != null && ile > 1 && (
            <span className="font-data text-[11px] text-faint">
              {pozycja} z {ile}
            </span>
          )}
          <Strzalka
            kierunek="lewo"
            onClick={starszy}
            tytul="Wcześniejszy dzień z rozliczeniami"
          />
          <Strzalka
            kierunek="prawo"
            onClick={nowszy}
            tytul="Późniejszy dzień z rozliczeniami"
          />
        </div>
      </div>

      {innaZakladka.length > 0 && (
        <p className="mt-3 text-xs leading-relaxed text-faint">
          Poza tym {innaZakladka.length}{" "}
          {innaZakladka.length === 1 ? "typ był" : "typów było"} na stronie, ale{" "}
          <strong className="font-semibold">nie na tej zakładce</strong> (weszło{" "}
          {innaZakladka.filter((t) => t.wynik === "wygrany").length}).{" "}
          <button
            onClick={() => setPokazInne((v) => !v)}
            aria-expanded={pokazInne}
            title={OPIS_POZIOMU_2}
            className="font-semibold text-brand underline underline-offset-2 hover:text-brand-deep"
          >
            {pokazInne ? "Ukryj je" : "Pokaż je na liście"}
          </button>
        </p>
      )}

      {/* NIE WIEMY ≠ NIE WESZŁO. Typ zamknięty bez danych ze źródła znika
          z trafień i z bilansu, więc dzień z padniętym feedem wygląda jak
          dzień z małym terminarzem. Ta linia jest jedynym miejscem, gdzie
          taka strata w ogóle się ujawnia. */}
      {(dzien.brak_danych_n ?? 0) > 0 && (
        <p className="mt-3 rounded-(--radius-control) border border-dashed border-data-amber/50 bg-data-amber-wash/40 px-3.5 py-2.5 text-xs leading-relaxed text-data-amber-ink">
          <span className="font-data font-semibold">
            {dzien.brak_danych_n}{" "}
            {odmien(dzien.brak_danych_n!, "typ", "typy", "typów")}
          </span>{" "}
          z tego dnia zamknęliśmy <strong>bez rozstrzygnięcia</strong> – źródło
          nie podało statystyk z meczu w terminie. Nie wiemy, czy weszły, więc
          nie liczą się ani do trafień, ani do bilansu wyżej.
        </p>
      )}

      {/* ILE DOKŁADNIE, NIE „CZĘŚĆ" (2026-08-04). Zgłoszenie usera: „za chuj
          wczoraj nie było tych wszystkich typów w zakładce Drużyny". Miał
          rację i to zdanie mu to ukrywało: dla 3 sierpnia stempel był
          odtworzony w 42 z 43 przypadków, a strona mówiła „część". Przy 98%
          to nie jest zastrzeżenie, tylko wprowadzanie w błąd — bo sugeruje,
          że reszta jest zapisana, a nie zgadnięta z rodzaju rynku.
          Stempel istnieje od 2 sierpnia, więc liczba sama zejdzie do zera. */}
      {pelnyWglad && bezStempla > 0 && (
        <p className="mt-2 text-[11px] leading-relaxed text-faint">
          <span className="font-data font-semibold">
            {bezStempla} z {typy.length}
          </span>{" "}
          {odmien(bezStempla, "typu", "typów", "typów")} z tego dnia jest sprzed
          wprowadzenia znacznika zakładki (2 sierpnia) – przypisanie do tej
          listy <strong>odtworzyliśmy z rodzaju rynku</strong>, nie odczytali
          z zapisu. Tam, gdzie ta liczba jest wysoka, sam podział na zakładki
          jest domysłem.
        </p>
      )}

      {pelnyWglad && (dzien.poza_n ?? 0) > 0 && (
        <p className="mt-3 text-xs leading-relaxed text-faint">
          Poza tym {dzien.poza_n}{" "}
          {dzien.poza_n === 1 ? "typ policzył się" : "typów policzyło się"}{" "}
          tylko na próbę (weszło {dzien.poza_trafione ?? 0}). Nie było ich na
          stronie, więc nie liczymy ich do bilansu wyżej.{" "}
          <button
            onClick={() => setPokazNaProbe((v) => !v)}
            aria-expanded={pokazNaProbe}
            className="font-semibold text-brand underline underline-offset-2 hover:text-brand-deep"
          >
            {pokazNaProbe ? "Ukryj je" : "Pokaż je na liście"}
          </button>
        </p>
      )}

      {/* LISTA NIŻEJ JEST JUŻ ZWINIĘTA (jeden wiersz na zakład), więc ten
          dopisek nie tłumaczy wyglądu listy – tłumaczy LICZBĘ W NAGŁÓWKU,
          która nadal jest liczona po poprzeczkach. To jedyne miejsce, gdzie
          te dwie wielkości się rozjeżdżają, i user ma prawo o tym wiedzieć,
          zamiast domyślać się z rozbieżności. */}
      {/* Ten akapit tłumaczy rozjazd DWÓCH NASZYCH SPOSOBÓW LICZENIA
          (poprzeczki vs zakłady). Dla użytkownika to wewnętrzna księgowość —
          na liście niżej i tak widzi jeden wiersz na zakład (06.08). */}
      {pelnyWglad && widoczne.length > zakladow && (
        <p className="mt-3 rounded-(--radius-control) border border-hairline bg-card-soft px-3.5 py-2.5 text-xs leading-relaxed text-muted">
          Wynik u góry liczy{" "}
          <span className="font-data font-semibold text-ink">
            {widoczne.length}{" "}
            {odmien(widoczne.length, "poprzeczkę", "poprzeczki", "poprzeczek")}
          </span>
          , ale to{" "}
          <span className="font-data font-semibold text-ink">
            {zakladow} {odmien(zakladow, "zakład", "zakłady", "zakładów")}
          </span>{" "}
          – ta sama drużyna i ten sam rynek bywają wycenione na kilku
          poprzeczkach naraz (np. „poniżej 13,5”, „poniżej 14,5”). Wchodzą albo
          przepadają <strong>razem</strong>, bo to jedna liczba z meczu. Na
          liście niżej stoją jako jeden wiersz – kliknij „{odmienLinie(2)}”,
          żeby rozwinąć poprzeczki.
        </p>
      )}

      {/* DZIEŃ TO SUMA, ZAKŁADKA TO ZDJĘCIE (2026-08-04).
          Zgłoszenie usera: „czemu w Skuteczności z 3.08 jest 29 typów, przecież
          wczoraj w Drużynach nie było 29". Obie liczby były prawdziwe i to jest
          właśnie problem – odpowiadały na inne pytania. Zmierzone na tamtym
          dniu: typy publikowaliśmy o 00, 01, 03, 11, 14, 15, 19, 20, 22 i 23,
          bo mecze startowały od nocy do późnego wieczora, a każdy cykl dokładał
          swoje. W żadnej chwili nie wisiało ich tyle naraz.
          Bez tego zdania rozjazd wygląda na błąd w liczeniu. */}
      {zakladow > 1 && (
        <p className="mt-2 text-xs leading-relaxed text-faint">
          To wszystko, co pokazaliśmy <strong>w ciągu całego dnia</strong> – typy
          dochodzą przez dobę, razem z kolejnymi meczami. Zakładka pokazuje stan
          na teraz, więc bywa krótsza; tu nic nie znika po gwizdku.
        </p>
      )}

      {typy.length >= PROG_FILTRA && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {FILTRY.map((f) => (
            <button
              key={f.kod}
              onClick={() => setFiltr(f.kod)}
              aria-pressed={f.kod === filtr}
              className={`rounded-(--radius-control) border px-3 py-1.5 text-xs transition-colors ${
                f.kod === filtr
                  ? "border-brand bg-brand-wash font-semibold text-brand-deep"
                  : "border-hairline bg-card text-muted hover:text-ink"
              }`}
            >
              {f.label}
            </button>
          ))}
          <span className="font-data ml-auto text-xs text-faint">
            {widoczne.length} z {typy.length}
          </span>
        </div>
      )}

      {widoczne.length > 0 ? (
        <div className="mt-3">
          <TabelaTypow
            typy={widoczne}
            pelnyWglad={pelnyWglad}
            poziom={(t) => poziomTypu(t, wybor)}
          />
        </div>
      ) : (
        <p className="mt-3 rounded-(--radius-control) border border-hairline bg-card-soft px-3.5 py-3 text-sm text-muted">
          {typy.length === 0
            ? "Tego dnia nic się nie rozliczyło."
            : filtr === "weszly"
              ? "Tego dnia nie wszedł żaden typ."
              : "Tego dnia weszły wszystkie typy."}
        </p>
      )}
    </div>
  );
}
