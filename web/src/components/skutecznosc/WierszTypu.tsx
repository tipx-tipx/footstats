"use client";

import { useMemo, useState } from "react";

import {
  fmtKurs,
  fmtLinia,
  nazwaPodmiotu,
  opisZakladu,
  opisZakladuBezLinii,
} from "@/lib/format";
import { odmienLinie } from "@/lib/warianty";
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
 * JEDEN WIERSZ NA ZAKŁAD, NIE NA POPRZECZKĘ (2026-08-02).
 *
 * Model wycenia tę samą rzecz na kilku poprzeczkach naraz. Legia – Zagłębie,
 * rożne w meczu powyżej: 6,5 · 7,5 · 8,5 · 9,5 · 10,5 · 11,5 · 12,5 · 13,5.
 * Osiem wierszy — ale to JEDNA liczba: padło 11 rożnych. Te wiersze nie mogą
 * wypaść niezależnie; wszystko poniżej wchodzi razem, wszystko powyżej razem
 * przepada. Zgłoszenie usera brzmiało „czemu tu jest miliard typów, piszesz
 * po kolei te same typy".
 *
 * Na całej księdze: 586 wierszy = 427 zakładów, a 83 ze 124 zakładów
 * wielopoziomowych kończy się jednolicie.
 *
 * CZEGO TO NIE ROBI: nie zmienia procentu trafień. Liczony uczciwie per
 * zakład wychodzi 57,6% wobec 57,7% per wiersz — praktycznie tyle samo.
 * Chodzi o CZYTELNOŚĆ i o to, żeby „47 typów" w nagłówku dnia nie sugerowało
 * 47 decyzji, gdy podjęto ich 29.
 *
 * POZIOM JEST CZĘŚCIĄ KLUCZA. Typ pokazany i typ policzony „na próbę" nigdy
 * nie wpadają do jednej grupy, choćby dzieliły mecz, rynek i stronę — inaczej
 * zwijanie zacierałoby dokładnie ten podział, który wprowadziliśmy wyżej
 * (Legia: dwie poprzeczki były na stronie, sześć nie).
 */
interface GrupaZakladu {
  klucz: string;
  poziom: 1 | 2 | 3;
  /** wszystkie poprzeczki zakładu, po linii rosnąco */
  linie: TypRozliczony[];
}

function grupujZaklady(
  typy: TypRozliczony[],
  poziom: (t: TypRozliczony) => 1 | 2 | 3,
): GrupaZakladu[] {
  const wg = new Map<string, GrupaZakladu>();
  const kolejnosc: string[] = [];
  for (const t of typy) {
    const p = poziom(t);
    const k = `${t.mecz}|${t.rynek_kod}|${t.podmiot}|${t.strona}|${p}`;
    const g = wg.get(k);
    if (g) g.linie.push(t);
    else {
      wg.set(k, { klucz: k, poziom: p, linie: [t] });
      kolejnosc.push(k);
    }
  }
  return kolejnosc.map((k) => {
    const g = wg.get(k)!;
    return { ...g, linie: [...g.linie].sort((a, b) => a.linia - b.linia) };
  });
}

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
  poziom = () => 1,
}: {
  typy: TypRozliczony[];
  /** false = widok klienta: bez kolumny „było" i oznaczeń „na próbę" */
  pelnyWglad?: boolean;
  /** 1 = stał na tej zakładce, 2 = na innej, 3 = nigdy nie był na stronie
   *  (patrz `poziomTypu` w TypyDnia – kolor mówi „czy to widziałeś") */
  poziom?: (t: TypRozliczony) => 1 | 2 | 3;
}) {
  const grupy = useMemo(() => grupujZaklady(typy, poziom), [typy, poziom]);
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
            <th className="hidden w-40 pb-1.5 pr-3 font-medium sm:table-cell">
              typ
            </th>
            {/* szersza niż wcześniej: przy zwiniętym zakładzie stoi tu ZAKRES
                („1,30–1,95"), a przy 3,5rem łamał się na dwie linie i tabela
                wyglądała na rozjechaną – dokładnie to, na co user narzekał
                przy pierwszej wersji tej siatki */}
            <th className="w-24 pb-1.5 pr-3 text-right font-medium">kurs</th>
            {pelnyWglad && (
              <th className="hidden w-12 pb-1.5 pr-3 text-right font-medium md:table-cell">
                było
              </th>
            )}
            <th className="w-20 pb-1.5 text-right font-medium">wynik</th>
          </tr>
        </thead>
        <tbody>
          {grupy.map((g, i) => (
            <WierszTypu
              key={`${g.klucz}-${i}`}
              g={g}
              pelnyWglad={pelnyWglad}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WierszTypu({
  g,
  pelnyWglad,
}: {
  g: GrupaZakladu;
  pelnyWglad: boolean;
}) {
  const [otwarty, setOtwarty] = useState(false);
  const { poziom, linie } = g;
  const t = linie[0];
  const wiele = linie.length > 1;
  const weszly = linie.filter((l) => l.wynik === "wygrany").length;
  const rozstrzygniete = linie.filter(
    (l) => l.wynik === "wygrany" || l.wynik === "przegrany",
  ).length;
  // Wynik CAŁEGO zakładu. Przy jednej poprzeczce to po prostu jej wynik; przy
  // kilku – czy weszła WIĘKSZOŚĆ, bo to jedno zdarzenie meczu widziane
  // z kilku wysokości. Kropka ma powiedzieć „ten pomysł się sprawdził albo
  // nie", a rozbicie stoi obok w kolumnie wyniku („5 z 8 weszło").
  const wygral = wiele ? weszly * 2 > rozstrzygniete : t.wynik === "wygrany";
  const przegral = wiele
    ? weszly * 2 < rozstrzygniete
    : t.wynik === "przegrany";
  // KOLOR MÓWI „CZY TO WIDZIAŁEŚ", nie „czy weszło" – od tego jest kolumna
  // wyniku. Poziom 2 (był na stronie, ale na innej zakładce) blednie, poziom 3
  // (nigdy nie był na stronie) traci kolor kropki i dostaje kreskowaną krawędź,
  // żeby nie dało się go pomylić z wynikiem produktu.
  const przygaszony = poziom > 1;
  // wszystkie poprzeczki dzielą JEDNĄ liczbę z meczu („padło 11 rożnych"),
  // więc pokazujemy ją raz – powielona sugerowałaby kilka zdarzeń
  const faktyczna = linie.find((l) => l.faktyczna != null)?.faktyczna ?? null;
  const kursy = linie.map((l) => l.kurs).filter((k): k is number => k != null);
  const opis = wiele
    ? `${opisZakladuBezLinii(t)} ${linie.map((l) => fmtLinia(l.linia)).join(" · ")}`
    : opisZakladu(t);

  return (
    <>
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
                  ? przygaszony
                    ? "bg-data-green/45"
                    : "bg-data-green"
                  : przegral
                    ? przygaszony
                      ? "bg-data-red/45"
                      : "bg-data-red"
                    : "bg-data-amber"
              }`}
            />
          )}
        </td>
        <td className="py-2 pr-3">
          <span className="block truncate font-medium">{nazwaPodmiotu(t)}</span>
          {/* na telefonie kolumna „typ" znika, więc rynek i poprzeczki schodzą
              tutaj – bez tego wiersz mówiłby „Kowalski 1,19 ✓" i nic poza tym */}
          <span className="block truncate text-xs text-muted sm:hidden">
            {opis}
          </span>
          <span className="block truncate text-xs text-faint">{t.mecz}</span>
        </td>
        <td className="hidden py-2 pr-3 text-muted sm:table-cell">
          <span className="block truncate">{opis}</span>
          {wiele && (
            <button
              onClick={() => setOtwarty((v) => !v)}
              aria-expanded={otwarty}
              title="Te poprzeczki opisują jedną liczbę z meczu – wchodzą albo przepadają razem"
              className="mt-0.5 block text-[10px] uppercase tracking-wide text-faint transition-colors hover:text-ink"
            >
              {odmienLinie(linie.length)} · jeden wynik meczu{" "}
              <span aria-hidden>{otwarty ? "▴" : "▾"}</span>
            </button>
          )}
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
          className="font-data py-2 pr-3 text-right tabular-nums whitespace-nowrap text-ink-soft"
          title={
            wiele
              ? "Zakres kursów wszystkich poprzeczek tego zakładu"
              : "Kurs z chwili, gdy typ pojawił się na stronie"
          }
        >
          {kursy.length === 0
            ? "–"
            : wiele
              ? `${fmtKurs(Math.min(...kursy))}–${fmtKurs(Math.max(...kursy))}`
              : fmtKurs(kursy[0])}
        </td>
        {pelnyWglad && (
          <td
            className="font-data hidden py-2 pr-3 text-right tabular-nums text-muted md:table-cell"
            title="Ile zawodnik albo drużyna faktycznie zanotowali w tym meczu"
          >
            {faktyczna != null ? faktyczna : "–"}
          </td>
        )}
        <td
          className={`py-2 text-right text-xs font-semibold whitespace-nowrap ${
            wygral
              ? przygaszony
                ? "text-data-green/60"
                : "text-data-green"
              : przegral
                ? przygaszony
                  ? "text-data-red/60"
                  : "text-data-red"
                : "text-data-amber-ink"
          }`}
        >
          {wiele
            ? `${weszly} z ${linie.length} weszło`
            : wygral
              ? "✓ weszło"
              : przegral
                ? "✗ nie"
                : "zwrot"}
        </td>
      </tr>

      {/* rozwinięcie: poszczególne poprzeczki tego samego zakładu */}
      {wiele && otwarty && (
        <tr className="border-t border-dotted border-hairline">
          <td />
          <td colSpan={pelnyWglad ? 5 : 4} className="pb-2.5 pr-3">
            <ul className="space-y-1">
              {linie.map((l, i) => (
                <li
                  key={`${l.linia}-${i}`}
                  className="flex items-baseline gap-3 text-xs"
                >
                  <span className="font-data w-12 shrink-0 tabular-nums text-muted">
                    {fmtLinia(l.linia)}
                  </span>
                  <span className="font-data w-12 shrink-0 tabular-nums text-ink-soft">
                    {l.kurs != null ? fmtKurs(l.kurs) : "–"}
                  </span>
                  <span
                    className={
                      l.wynik === "wygrany"
                        ? "text-data-green"
                        : l.wynik === "przegrany"
                          ? "text-data-red"
                          : "text-data-amber-ink"
                    }
                  >
                    {l.wynik === "wygrany"
                      ? "✓ weszło"
                      : l.wynik === "przegrany"
                        ? "✗ nie"
                        : "zwrot"}
                  </span>
                </li>
              ))}
            </ul>
          </td>
        </tr>
      )}
    </>
  );
}
