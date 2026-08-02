"use client";

import { fmtKurs, nazwaPodmiotu, opisZakladu } from "@/lib/format";
import type { TypRozliczony } from "@/lib/types";

/**
 * Jeden rozliczony typ – WIERSZ TABELI, nie karta.
 *
 * Karta jest dobra dla trzech rzeczy naraz. Przy kilkunastu typach dziennie
 * oko musi jechać w dół KOLUMNY, nie czytać każdego wiersza od nowa.
 *
 * KOLUMNY SĄ TWARDO USTALONE (`table-fixed` + szerokości na `th`). Pierwsza
 * wersja opierała je na sztuczce `max-w-0` + `truncate` – działa to tylko przy
 * sprzyjających treściach, a przy długich nazwach klubów tabela się
 * rozjeżdżała (zgłoszone 2026-07-27: „nierówne, z dupy wszystko"). Stała
 * siatka jest nudna i zawsze wygląda tak samo – o to właśnie chodzi.
 */

/** Typ rozliczony w tle: czemu nie było go na liście. Po ludzku, bez żargonu. */
export const POZA_LABEL: Record<string, string> = {
  kwarantanna_rynku:
    "Ten rynek był chwilowo wstrzymany, bo tracił pieniądze – typ policzył się tylko na próbę",
  kwarantanna_kategorii:
    "Ten powód typowania był chwilowo wstrzymany, bo tracił pieniądze – typ policzył się tylko na próbę",
  rozjazd_z_rynkiem:
    "Nasza szansa za mocno rozjeżdżała się z kursem – typ policzył się tylko na próbę",
  limit_meczu:
    "Z jednego meczu pokazujemy ograniczoną liczbę typów; ten się nie zmieścił",
  ujemna_po_korekcie:
    "Po urealnieniu szansy na rozliczeniach ten zakład wychodził na minus – typ policzył się tylko na próbę",
  stare_dane: "Zawodnik dawno nie grał, więc typ policzył się tylko na próbę",
  za_pozno: "Powstał za blisko pierwszego gwizdka – nie zdążyłbyś go obstawić",
};

/**
 * Cała tabela typów – nagłówek i wiersze w jednym pliku, celowo.
 *
 * Osobne eksportowanie nagłówka i wiersza kusiło, ale rozjeżdżało siatkę:
 * przy `table-fixed` szerokości bierze się z PIERWSZEGO wiersza, więc nagłówek
 * i komórki muszą mieć dokładnie ten sam zestaw kolumn i te same reguły
 * chowania. Rozdzielone na dwa komponenty nic tego nie pilnowało.
 */
export function TabelaTypow({
  typy,
  pelnyWglad = true,
  poziom,
}: {
  typy: TypRozliczony[];
  /** false = widok klienta: bez kolumny „było" i oznaczeń „na próbę" */
  pelnyWglad?: boolean;
  /** 1 = stał na tej zakładce, 2 = na innej, 3 = nigdy nie był na stronie
   *  (patrz `poziomTypu` w TypyDnia – kolor mówi „czy to widziałeś") */
  poziom?: (t: TypRozliczony) => 1 | 2 | 3;
}) {
  return (
    <div>
      {/* Szerokości siedzą na `th` przy `table-fixed` – nie w `<colgroup>`.
          Powód jest praktyczny: kolumny muszą ZNIKAĆ na wąskim ekranie
          (`hidden sm:table-cell`), a `display` na `<col>` przeglądarki
          ignorują. Z colgroup tabela nie mieściła się na telefonie i ucinała
          kolumnę „wynik" – czyli jedyną, po którą się tu wchodzi. */}
      <table className="w-full table-fixed text-sm">
        <thead>
          <tr className="text-left text-[10px] uppercase tracking-wide text-faint">
            <th className="w-5 pb-1.5" />
            <th className="pb-1.5 pr-3 font-medium">kto</th>
            <th className="hidden w-44 pb-1.5 pr-3 font-medium sm:table-cell">
              typ
            </th>
            <th className="w-14 pb-1.5 pr-3 text-right font-medium">kurs</th>
            {pelnyWglad && (
              <th className="hidden w-12 pb-1.5 pr-3 text-right font-medium md:table-cell">
                było
              </th>
            )}
            <th className="w-20 pb-1.5 text-right font-medium">wynik</th>
          </tr>
        </thead>
        <tbody>
          {typy.map((t, i) => (
            <WierszTypu
              key={`${t.podmiot}-${t.rynek_kod}-${t.linia}-${i}`}
              t={t}
              pelnyWglad={pelnyWglad}
              poziom={poziom?.(t) ?? 1}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WierszTypu({
  t,
  pelnyWglad,
  poziom = 1,
}: {
  t: TypRozliczony;
  pelnyWglad: boolean;
  poziom?: 1 | 2 | 3;
}) {
  const wygral = t.wynik === "wygrany";
  const przegral = t.wynik === "przegrany";
  // KOLOR MÓWI „CZY TO WIDZIAŁEŚ", nie „czy weszło" – od tego jest kolumna
  // wyniku. Poziom 2 (był na stronie, ale na innej zakładce) blednie, poziom 3
  // (nigdy nie był na stronie) traci kolor kropki i dostaje kreskowaną krawędź,
  // żeby nie dało się go pomylić z wynikiem produktu.
  const przygaszony = poziom > 1;
  return (
    <tr
      className={`align-top transition-colors hover:bg-brand-wash/30 ${
        poziom === 3
          ? "border-t border-dashed border-hairline-strong/70 opacity-55"
          : "border-t border-hairline"
      } ${poziom === 2 ? "opacity-70" : ""}`}
    >
      <td className="py-2">
        {poziom === 3 ? (
          // brak koloru wyniku – ten typ nie był ofertą, tylko pomiarem
          <span
            aria-hidden
            className="mt-1.5 block h-2 w-2 rounded-full border border-dashed border-hairline-strong"
          />
        ) : (
          <span
            aria-hidden
            className={`mt-1.5 block h-2 w-2 rounded-full ${
              wygral
                ? przygaszony ? "bg-data-green/45" : "bg-data-green"
                : przegral
                  ? przygaszony ? "bg-data-red/45" : "bg-data-red"
                  : "bg-data-amber"
            }`}
          />
        )}
      </td>
      <td className="py-2 pr-3">
        <span className="block truncate font-medium">{nazwaPodmiotu(t)}</span>
        {/* na telefonie kolumna „typ" znika, więc rynek i linia schodzą tutaj –
            bez tego wiersz mówiłby „Kowalski 1,19 ✓" i nic poza tym */}
        <span className="block truncate text-xs text-muted sm:hidden">
          {opisZakladu(t)}
        </span>
        <span className="block truncate text-xs text-faint">{t.mecz}</span>
      </td>
      <td className="hidden py-2 pr-3 text-muted sm:table-cell">
        <span className="block truncate">{opisZakladu(t)}</span>
        {/* klasa karty (top/mocny/solidny) – mają ją WYŁĄCZNIE drabinki.
            Wcześniej mieszkała w osobnej liście „Karty rozliczone" pod
            kalendarzem, która przy kilku kartach dziennie powtarzała ten sam
            zestaw co panel dnia (zgłoszone 2026-07-27: „dublowanie"). */}
        {t.klasa && (
          <span
            className={`mt-0.5 inline-block rounded-full px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide ${
              t.klasa === "top"
                ? "bg-data-green-wash text-data-green-ink"
                : t.klasa === "mocny"
                  ? "bg-brand-wash text-brand-deep"
                  : "bg-card-soft text-faint"
            }`}
            title="Ocena karty w chwili, gdy ją pokazaliśmy"
          >
            {t.klasa}
          </span>
        )}
        {pelnyWglad && t.poza_publikacja && (
          <span
            className="block text-[10px] uppercase tracking-wide text-faint"
            title={POZA_LABEL[t.poza_publikacja] ?? "Typ policzony tylko na próbę"}
          >
            na próbę
          </span>
        )}
        {poziom === 2 && (
          <span
            className="block text-[10px] uppercase tracking-wide text-faint"
            title="Był na stronie, ale nie na tej zakładce – nie liczymy go do wyniku powyżej"
          >
            inna zakładka
          </span>
        )}
      </td>
      <td
        className="font-data py-2 pr-3 text-right tabular-nums text-ink-soft"
        title="Kurs z chwili, gdy typ pojawił się na stronie"
      >
        {t.kurs != null ? fmtKurs(t.kurs) : "–"}
      </td>
      {pelnyWglad && (
        <td
          className="font-data hidden py-2 pr-3 text-right tabular-nums text-muted md:table-cell"
          title="Ile zawodnik albo drużyna faktycznie zanotowali w tym meczu"
        >
          {t.faktyczna != null ? t.faktyczna : "–"}
        </td>
      )}
      <td
        className={`py-2 text-right text-xs font-semibold whitespace-nowrap ${
          wygral
            ? przygaszony ? "text-data-green/60" : "text-data-green"
            : przegral
              ? przygaszony ? "text-data-red/60" : "text-data-red"
              : "text-data-amber-ink"
        }`}
      >
        {wygral ? "✓ weszło" : przegral ? "✗ nie" : "zwrot"}
      </td>
    </tr>
  );
}
