"use client";

import { useMemo, useState } from "react";

import { TabelaTypow } from "./WierszTypu";
import { useBilans } from "../useBilans";
import { fmtDzien, odmien } from "@/lib/format";
import type { SkutecznoscDnia } from "@/lib/types";

/**
 * Panel JEDNEGO DNIA — pod kalendarzem, zawsze otwarty na którymś dniu.
 *
 * Jedna oś czasu, dwa sposoby ruszania się po niej: kliknięcie w kafelek
 * (skok w konkretną datę) i strzałki tutaj (krok po kolejnych dniach
 * z rozliczeniami). To NIE jest dawny osobny pager z własnej zakładki —
 * obie drogi ustawiają ten sam wybór, a kalendarz przewija się za nim, więc
 * podświetlony kafelek zawsze odpowiada temu, co widać niżej.
 *
 * Filtr wyniku pojawia się dopiero przy dłuższej liście: przy trzech typach
 * jest szumem, przy trzydziestu — jedynym sposobem, żeby szybko zobaczyć,
 * co konkretnie nie weszło.
 */

type Filtr = "wszystko" | "weszly" | "nie";

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
 * Padło 11 rożnych — trzy ostatnie wchodzą RAZEM. Zgłoszenie usera
 * 2026-08-01 („czemu tu jest miliard typów?") dotyczyło dokładnie tego.
 * Publikacja wystawia od tej pory jedną linię na stronę, ale w księdze
 * zostają dni sprzed zmiany — i one nadal mają się czytać uczciwie.
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
}: {
  dzien: SkutecznoscDnia;
  /** false = widok klienta: bez typów liczonych „na próbę" */
  pelnyWglad?: boolean;
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
  // niżej — ZWINIĘTE domyślnie, bo potrafią zająć połowę listy (zmierzone
  // 2026-08-01: 27 z 60 ostatnich rozliczeń).
  const [pokazNaProbe, setPokazNaProbe] = useState(false);
  // `?? []` w ciele komponentu tworzyłoby nową tablicę co render i unieważniało
  // useMemo niżej przy każdym przerysowaniu
  const typy = useMemo(
    () =>
      (dzien.typy ?? []).filter(
        (t) => !t.poza_publikacja || (pelnyWglad && pokazNaProbe),
      ),
    [dzien.typy, pelnyWglad, pokazNaProbe],
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
          <p className="mt-0.5 text-xs text-muted">
            <span className="font-data font-semibold text-ink">
              {dzien.trafione}/{dzien.rozliczone}
            </span>{" "}
            weszło ({proc}%) · bilans{" "}
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

      {widoczne.length > zakladow && (
        <p className="mt-3 rounded-(--radius-control) border border-hairline bg-card-soft px-3.5 py-2.5 text-xs leading-relaxed text-muted">
          <span className="font-data font-semibold text-ink">
            {widoczne.length}{" "}
            {odmien(widoczne.length, "wiersz", "wiersze", "wierszy")} ={" "}
            {zakladow} {odmien(zakladow, "zakład", "zakłady", "zakładów")}
          </span>{" "}
          — ta sama drużyna i ten sam rynek stoją tu w kilku liniach naraz
          (np. „poniżej 13,5”, „poniżej 14,5”, „poniżej 15,5”). Takie linie
          wchodzą albo przepadają <strong>razem</strong>, więc to jeden wynik
          meczu, nie kilka trafień. Od 1 sierpnia wystawiamy już tylko jedną
          linię na stronę.
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
          <TabelaTypow typy={widoczne} pelnyWglad={pelnyWglad} />
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
