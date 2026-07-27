"use client";

import { motion, useReducedMotion } from "framer-motion";
import { useMemo, useState } from "react";

import { KalendarzWynikow } from "./KalendarzWynikow";
import { KrzywaWyniku } from "./skutecznosc/KrzywaWyniku";
import { TypyDnia } from "./skutecznosc/TypyDnia";
import { WerdyktModelu, type WerdyktDane } from "./WerdyktModelu";
import { fmtProc } from "@/lib/format";
import type {
  Meta,
  SkutecznoscDnia,
  SkutecznoscStrumienia,
  Strumien,
  TypRozliczony,
  TypyWyniki,
} from "@/lib/types";
import { poZmianie } from "@/lib/zmiany";

/**
 * Cała interaktywna część zakładki Skuteczność w JEDNYM stanie.
 *
 * Dotąd wybór produktu (zawodnicy / drużyny / drabinki) stał w dwóch
 * miejscach — w sekcji strumieni i w kalendarzu — z osobnym stanem każdy.
 * Ustawiałeś „Drużyny" w kalendarzu, przechodziłeś wyżej, a tam znowu
 * „Pewniaki". Teraz filtr jest jeden, na górze, i obowiązuje wszystko pod
 * spodem: werdykt, krzywą, kalendarz i tabelę rynków.
 *
 * Hierarchia jest twarda i czytelnik schodzi nią w dół, nigdy w bok:
 *   CO (produkt) → KIEDY (krzywa + kalendarz + dzień) → DLACZEGO (rynki).
 *
 * DWA WIDOKI (2026-07-27, przygotowanie strony pod klienta zewnętrznego):
 *
 *   klient — strona liniowa, ZERO zakładek. Werdykt w złotówkach, krzywa
 *            i kalendarz obok siebie, pod nimi wybrany dzień. Koniec.
 *   admin  — to samo plus zakładki z kuchnią: tabela rynków (obiecywał vs
 *            weszło), bilans kuponów, sprawdzian na meczach spoza nauki.
 *
 * Podział nie jest kosmetyczny. Tabela rynków dosłownie mówi „nasz model
 * przeszacowuje o 12 pp" — dla nas to najważniejsza diagnostyka, dla klienta
 * argument przeciwko produktowi. Sprawdzian modelu i typy liczone „na próbę"
 * to z kolei narzędzia inżynierskie: nikt z zewnątrz nie wie, co znaczy punkt
 * na przekątnej. Admin ma przełącznik „pokaż jak widzi klient", bo inaczej
 * przygotowanie tej strony pod sprzedaż byłoby zgadywanką.
 */

type Wybor = "wszystko" | Strumien;

const NAZWY: Record<Wybor, string> = {
  wszystko: "Wszystko",
  pewniaki: "Zawodnicy",
  druzyny: "Drużyny",
  drabinki: "Drabinki",
};

/** Dopełniacz do zdania werdyktu: „na 331 rozliczonych TYPACH…". */
const W_ZDANIU: Record<Wybor, string> = {
  wszystko: "typach",
  pewniaki: "typach zawodniczych",
  druzyny: "typach drużynowych",
  drabinki: "kartach drabinek",
};

const OPISY: Record<Strumien, string> = {
  pewniaki:
    "Typy na pojedynczych zawodników (strzały, faule, odbiory), liczone przez nasz model.",
  druzyny:
    "Typy na całe drużyny: gole, rożne, kartki, strzały zespołu. Inny rodzaj zakładu i inne ryzyko niż typy na zawodników.",
  drabinki:
    "Najlepszy typ z każdej karty w zakładce Drabinki. Szansę liczymy tu inaczej niż w modelu: od tego, jak często zawodnik przebijał daną linię, poprawionego o rywala, sędziego i przewidywany przebieg meczu.",
};

// Zakładka „Co weszło" (pełna lista wszystkich rozliczonych typów) ZNIKNĘŁA
// 2026-07-27 na prośbę usera: przy kilkuset rozliczeniach była ścianą tekstu,
// przez którą nie dało się przejść. Wróciliśmy do modelu „kalendarz + dzień",
// ale bez wady, która tamtą listę zrodziła — patrz komentarz przy `wybranyDzien`.
//
// Kalendarz i dzień wyszły PONAD zakładki (2026-07-27): to nie jest „jeden
// z dowodów", tylko główna treść strony, a chowanie jej za zakładką obok
// diagnostyki modelu zrównywało rzeczy o zupełnie różnej wadze. W zakładkach
// została sama kuchnia — i dlatego widzi je wyłącznie admin.
const ZAKLADKI = [
  { id: "rynki", label: "Rynki" },
  { id: "kupony", label: "Kupony" },
  { id: "test", label: "Test na danych z przeszłości" },
] as const;

type IdZakladki = (typeof ZAKLADKI)[number]["id"];

/** Od tylu rozliczeń rynek w tabeli traktujemy jako mówiący cokolwiek. */
const N_ISTOTNE = 10;

/**
 * Do którego produktu należy typ — awaryjnie, po samym rekordzie.
 *
 * Backend liczy ten podział sam (`skutecznosc_strumienie`), ale dane sprzed
 * jego wdrożenia go nie mają i wtedy filtr produktu w ogóle nie pojawiał się
 * na stronie — user nie miał jak zobaczyć, co weszło z drużyn, a co
 * z drabinek. `klasa` (top/mocny/solidny) występuje wyłącznie na kartach
 * Drabinek, a rynki drużynowe mają kod z przedrostkiem `team_`.
 */
function strumienTypu(t: TypRozliczony): Strumien {
  if (t.klasa) return "drabinki";
  return t.rynek_kod.startsWith("team_") ? "druzyny" : "pewniaki";
}

/** Awaryjne rozbicie dni na produkty, gdy backend go jeszcze nie przysłał. */
function strumienieZDni(
  dni: SkutecznoscDnia[],
): Partial<Record<Strumien, SkutecznoscStrumienia>> {
  const out: Partial<Record<Strumien, SkutecznoscStrumienia>> = {};
  for (const k of ["pewniaki", "druzyny", "drabinki"] as Strumien[]) {
    const wDni = dni
      .map((d) => {
        const typy = (d.typy ?? []).filter((t) => strumienTypu(t) === k);
        const publikowane = typy.filter((t) => !t.poza_publikacja);
        const zKursem = publikowane.filter((t) => t.kurs != null && !t.sugestia);
        return {
          dzien: d.dzien,
          rozliczone: publikowane.length,
          trafione: publikowane.filter((t) => t.wynik === "wygrany").length,
          okazje: zKursem.length,
          roi_flat:
            Math.round(
              zKursem.reduce(
                (a, t) => a + (t.wynik === "wygrany" ? t.kurs! - 1 : -1),
                0,
              ) * 100,
            ) / 100,
          poza_n: typy.filter((t) => t.poza_publikacja).length,
          poza_trafione: typy.filter(
            (t) => t.poza_publikacja && t.wynik === "wygrany",
          ).length,
          typy,
        };
      })
      .filter((d) => d.typy.length > 0);
    const rozliczone = wDni.reduce((a, d) => a + d.rozliczone, 0);
    if (!rozliczone) continue;
    const trafione = wDni.reduce((a, d) => a + d.trafione, 0);
    out[k] = {
      dni: wDni,
      podsumowanie: {
        rozliczone,
        trafione,
        skutecznosc: Math.round((trafione / rozliczone) * 1000) / 1000,
        okazje_rozliczone: wDni.reduce((a, d) => a + d.okazje, 0),
        roi_flat: Math.round(wDni.reduce((a, d) => a + d.roi_flat, 0) * 100) / 100,
        poza_n: wDni.reduce((a, d) => a + (d.poza_n ?? 0), 0),
        poza_trafione: wDni.reduce((a, d) => a + (d.poza_trafione ?? 0), 0),
      },
    };
  }
  return out;
}

/** Średni kurs rozliczonych typów z dni — podstawa progu opłacalności. */
function progOplacalnosci(dni: SkutecznoscDnia[]): number | null {
  let suma = 0;
  let n = 0;
  for (const d of dni) {
    for (const t of d.typy ?? []) {
      if (t.poza_publikacja || t.kurs == null || t.kurs <= 1) continue;
      if (t.wynik !== "wygrany" && t.wynik !== "przegrany") continue;
      suma += t.kurs;
      n += 1;
    }
  }
  return n >= 20 ? 1 / (suma / n) : null;
}

export function SkutecznoscScena({
  typy,
  meta,
  kuponyPanel,
  testPanel,
  pelnyWglad = true,
  przelacznikWidoku,
}: {
  typy: TypyWyniki;
  meta: Meta;
  /** panele niezależne od filtru produktu — renderowane na serwerze */
  kuponyPanel: React.ReactNode;
  testPanel: React.ReactNode;
  /** false = widok klienta: bez kuchni modelu (patrz komentarz na górze) */
  pelnyWglad?: boolean;
  /** przełącznik „pokaż jak widzi klient" — tylko dla admina */
  przelacznikWidoku?: React.ReactNode;
}) {
  const reduced = useReducedMotion();
  const [wybor, setWybor] = useState<Wybor>("wszystko");
  const [zakladka, setZakladka] = useState<IdZakladki>("rynki");
  const [dzien, setDzien] = useState<string | null>(null);

  const wszystkieDni = useMemo(
    () => typy.skutecznosc_dzienna ?? [],
    [typy.skutecznosc_dzienna],
  );
  // podział na produkty: z backendu, a gdy go tam jeszcze nie ma — policzony
  // z listy dni (patrz strumienieZDni). Bez tego filtr znikał i user nie miał
  // jak zobaczyć, co weszło z drużyn i z drabinek.
  const strumienie = useMemo(
    () =>
      typy.skutecznosc_strumienie &&
      Object.keys(typy.skutecznosc_strumienie).length > 0
        ? typy.skutecznosc_strumienie
        : strumienieZDni(wszystkieDni),
    [typy.skutecznosc_strumienie, wszystkieDni],
  );
  const dostepne = useMemo(
    () =>
      (["pewniaki", "druzyny", "drabinki"] as Strumien[]).filter(
        (k) => (strumienie[k]?.podsumowanie.rozliczone ?? 0) > 0,
      ),
    [strumienie],
  );

  // useMemo, a nie zwykłe wyrażenie: `?? []` dawałoby nową tablicę co render
  // i unieważniało wszystkie useMemo, które biorą `dni` w zależnościach
  const dni = useMemo(
    () => (wybor === "wszystko" ? wszystkieDni : (strumienie[wybor]?.dni ?? [])),
    [wybor, wszystkieDni, strumienie],
  );

  /**
   * Dni, które mają co pokazać — od najnowszego (tak przychodzą z backendu).
   * Kalendarz rysuje kafelki wyłącznie z nich, więc panel i siatka operują na
   * dokładnie tym samym zbiorze i nawigacja strzałkami nie trafia w pustkę.
   */
  const dniZTypami = useMemo(
    () => dni.filter((d) => d.rozliczone > 0),
    [dni],
  );

  /**
   * ZAWSZE któryś dzień jest otwarty — i to jest sedno tej przebudowy.
   *
   * Pełna lista typów („Co weszło") powstała dlatego, że kafelki kalendarza
   * nie wyglądały na klikalne: kto o tym nie wiedział, nie zobaczył ani jednego
   * typu. Odpowiedzią było wysypanie wszystkiego na jedną stronę, co zamieniło
   * problem odkrywalności w ścianę tekstu.
   *
   * Domyślne otwarcie najnowszego dnia rozwiązuje jedno i drugie: interakcja
   * pokazuje się sama (widać otwarty panel i podświetlony kafelek nad nim),
   * a treści jest tyle, ile człowiek przeczyta. Gdy filtr produktu zmieni się
   * tak, że zapamiętany dzień w nim nie istnieje, wracamy do najnowszego —
   * dlatego to wyliczenie, a nie efekt synchronizujący stan.
   */
  const wybranyDzien =
    dniZTypami.find((d) => d.dzien === dzien) ?? dniZTypami[0] ?? null;
  const idxDnia = wybranyDzien
    ? dniZTypami.findIndex((d) => d.dzien === wybranyDzien.dzien)
    : -1;

  // --- WERDYKT dla aktualnego filtru ---
  const werdykt: WerdyktDane | null = useMemo(() => {
    const pods = typy.podsumowanie;
    if (wybor !== "wszystko") {
      const s = strumienie[wybor]?.podsumowanie;
      if (!s || s.rozliczone === 0) return null;
    } else if (!pods || pods.rozliczone === 0) {
      return null;
    }
    const s =
      wybor === "wszystko"
        ? {
            rozliczone: pods!.rozliczone,
            trafione: pods!.trafione,
            roi_flat: pods!.roi_flat,
          }
        : strumienie[wybor]!.podsumowanie;

    // deklaracja: średnia ważona z rynków należących do tego produktu
    const rynki = typy.po_rynku.filter((r) =>
      wybor === "druzyny"
        ? r.rynek_kod.startsWith("team_")
        : wybor === "pewniaki"
          ? !r.rynek_kod.startsWith("team_")
          : true,
    );
    const nDekl = rynki.reduce((a, r) => a + r.n, 0);
    const deklaracja =
      wybor === "drabinki" || !nDekl
        ? null
        : rynki.reduce((a, r) => a + r.sr_p_model * r.n, 0) / nDekl;

    // winowajca: tylko w widoku całości i tylko gdy jeden produkt dominuje
    let winowajca: WerdyktDane["winowajca"] = null;
    if (wybor === "wszystko" && s.roi_flat < 0) {
      const naj = dostepne
        .map((k) => ({ k, roi: strumienie[k]!.podsumowanie.roi_flat }))
        .sort((a, b) => a.roi - b.roi)[0];
      if (naj && naj.roi / s.roi_flat > 0.6) {
        winowajca = { nazwa: NAZWY[naj.k].toLowerCase(), roi: naj.roi };
      }
    }

    return {
      coLiczymy: W_ZDANIU[wybor],
      rozliczone: s.rozliczone,
      trafione: s.trafione,
      roi: s.roi_flat,
      deklaracja,
      prog: progOplacalnosci(dni),
      clv: wybor === "wszystko" ? pods?.clv_sr_pct : null,
      clvN: wybor === "wszystko" ? pods?.clv_n : 0,
      naPlusie: dni.filter((d) => d.roi_flat > 0.005).length,
      naMinusie: dni.filter((d) => d.roi_flat < -0.005).length,
      winowajca,
      // wstrzymane RYNKI i wstrzymane POWODY typowania — dla czytelnika to
      // jedna lista („czego teraz nie pokazujemy i dlaczego”)
      wstrzymane: [
        ...Object.values(meta.kwarantanna ?? {}),
        ...Object.values(meta.kwarantanna_powodow ?? {}),
      ].map((k) => k.nazwa.toLowerCase()),
      dniPoZmianie: dni.filter((d) => poZmianie(d.dzien)).length,
    };
  }, [wybor, typy, strumienie, dni, dostepne, meta]);

  // --- TABELA RYNKÓW dla aktualnego filtru ---
  const rynkiWidoku = useMemo(() => {
    if (wybor === "drabinki") return [];
    return [...typy.po_rynku]
      .filter((r) =>
        wybor === "druzyny"
          ? r.rynek_kod.startsWith("team_")
          : wybor === "pewniaki"
            ? !r.rynek_kod.startsWith("team_")
            : true,
      )
      .sort((a, b) => {
        const chudy = (n: number) => (n < N_ISTOTNE ? 1 : 0);
        return (
          chudy(a.n) - chudy(b.n) ||
          a.czestosc - a.sr_p_model - (b.czestosc - b.sr_p_model)
        );
      });
  }, [typy.po_rynku, wybor]);

  const poza = wybor === "wszystko" ? null : strumienie[wybor]?.podsumowanie;
  const klasy = wybor === "drabinki" ? strumienie.drabinki?.klasy : undefined;

  return (
    <div>
      {przelacznikWidoku}

      {werdykt && (
        <div className="max-w-3xl">
          <WerdyktModelu d={werdykt} pelnyWglad={pelnyWglad} />
        </div>
      )}

      {/* FILTR PRODUKTU — jeden na całą stronę. Każdy chip niesie własny
          bilans, więc „gdzie tracimy" widać bez wchodzenia w cokolwiek. */}
      {dostepne.length > 1 && (
        <div className="mt-6 max-w-3xl">
          <p className="text-[10px] uppercase tracking-widest text-faint">
            który rodzaj typów oglądasz
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {(["wszystko", ...dostepne] as Wybor[]).map((k) => {
              const aktywny = k === wybor;
              const n =
                k === "wszystko"
                  ? (typy.podsumowanie?.rozliczone ?? 0)
                  : strumienie[k]!.podsumowanie.rozliczone;
              return (
                <button
                  key={k}
                  onClick={() => {
                    setWybor(k);
                    setDzien(null);
                  }}
                  aria-pressed={aktywny}
                  title={k === "wszystko" ? undefined : OPISY[k as Strumien]}
                  className={`rounded-(--radius-control) border px-3.5 py-2 text-left text-sm transition-colors ${
                    aktywny
                      ? "border-brand bg-brand-wash text-brand-deep"
                      : "border-hairline bg-card text-muted hover:border-hairline-strong hover:text-ink"
                  }`}
                >
                  <span className="font-semibold">{NAZWY[k]}</span>
                  {/* Bilans STĄD ZNIKNĄŁ (decyzja usera 2026-07-27). Chip jest
                      przełącznikiem, a nie tablicą wyników: cztery kwoty obok
                      siebie konkurowały z werdyktem wyżej, który mówi to samo
                      dokładniej. Zostaje sama liczba rozliczeń — mówi, ile
                      danych stoi za tym, co zobaczysz po kliknięciu. */}
                  <span className="font-data ml-2 text-xs text-faint">
                    ({n})
                  </span>
                </button>
              );
            })}
          </div>
          {wybor !== "wszystko" && (
            <p className="mt-2 max-w-prose text-xs leading-relaxed text-muted">
              {OPISY[wybor as Strumien]}
            </p>
          )}
        </div>
      )}

      {/* DOWÓD — trzy bloki, dwa różne układy.

          Wersja z 27.07 stawiała krzywą obok kalendarza, a dzień pod spodem.
          Karty w wierszu mają różną wysokość (krzywa ~260 px, kalendarz ~570),
          więc pod krzywą zostawała pusta kolumna — i to samo pod dniem, bo był
          węższy od siatki nad nim. Zgłoszone wprost: „pusta przestrzeń góra
          dół".

          Na szerokim ekranie kalendarz trzyma prawą kolumnę na całą swoją
          wysokość (`row-span-2`), a lewa układa krzywą i wybrany dzień jedno
          pod drugim. Dwa krótkie bloki dopełniają jeden wysoki — nie ma czego
          wypełniać. Przy okazji wychodzi to lepiej logicznie: klikasz dzień
          i jego typy są OBOK, na wysokości wzroku.

          Na wąskim ekranie liczy się KOLEJNOŚĆ, nie wypełnienie: kalendarz
          musi iść PRZED dniem, bo to nim się dzień wybiera. Dlatego trzy
          osobne dzieci siatki i jawne `col/row-start` dopiero od XL —
          w jednej kolumnie układają się w naturalnej kolejności czytania. */}
      <div className="mt-8 grid max-w-3xl gap-5 xl:max-w-6xl xl:grid-cols-[minmax(0,1fr)_26rem]">
        {dni.length > 1 && (
          <div className="min-w-0 xl:col-start-1 xl:row-start-1">
            <KrzywaWyniku dni={dni} pelnyWglad={pelnyWglad} />
          </div>
        )}

        <div className="min-w-0 xl:col-start-2 xl:row-span-2 xl:row-start-1">
          <KalendarzWynikow
            dni={dni}
            wszystkieDni={wszystkieDni}
            wybrany={wybranyDzien?.dzien ?? null}
            onWybierz={setDzien}
            pelnyWglad={pelnyWglad}
          />
        </div>

        <div className="min-w-0 space-y-3 xl:col-start-1 xl:row-start-2">
          {wybranyDzien ? (
            <TypyDnia
              dzien={wybranyDzien}
              pelnyWglad={pelnyWglad}
              // strzałki chodzą po TEJ SAMEJ liście co kafelki, a kalendarz
              // przewija się za wyborem (patrz KalendarzWynikow) — więc to
              // nadal jedna oś czasu, tylko dostępna bez celowania w siatkę
              nowszy={
                idxDnia > 0
                  ? () => setDzien(dniZTypami[idxDnia - 1].dzien)
                  : undefined
              }
              starszy={
                idxDnia >= 0 && idxDnia < dniZTypami.length - 1
                  ? () => setDzien(dniZTypami[idxDnia + 1].dzien)
                  : undefined
              }
              pozycja={idxDnia + 1}
              ile={dniZTypami.length}
            />
          ) : (
            <p className="rounded-(--radius-card) border border-hairline bg-card px-4 py-3.5 text-sm text-muted shadow-(--shadow-card)">
              Nic tu jeszcze nie ma — żaden typ tego rodzaju się nie rozliczył.
            </p>
          )}
          {pelnyWglad && (poza?.poza_n ?? 0) > 0 && (
            <p className="rounded-(--radius-card) border border-hairline bg-card px-4 py-3 text-xs leading-relaxed text-muted">
              <span className="font-data font-semibold text-ink">
                {poza!.poza_trafione ?? 0}/{poza!.poza_n}
              </span>{" "}
              typów policzyliśmy{" "}
              <strong className="font-semibold">tylko na próbę</strong> — nie
              było ich na stronie, bo albo dany rynek był chwilowo wstrzymany,
              albo nie zmieściły się w limicie typów z jednego meczu. Nie
              wliczamy ich do bilansu; na liście mają oznaczenie „na próbę”.
            </p>
          )}
        </div>
      </div>

      {/* ZAKŁADKI — sama kuchnia modelu, wyłącznie dla admina */}
      {pelnyWglad && (
      <div className="mt-10">
        <div
          role="tablist"
          aria-label="Dowody skuteczności"
          className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1"
        >
          {ZAKLADKI.map((z) => {
            const aktywna = z.id === zakladka;
            return (
              <button
                key={z.id}
                role="tab"
                id={`zakladka-${z.id}`}
                aria-selected={aktywna}
                aria-controls={`panel-${z.id}`}
                onClick={() => setZakladka(z.id)}
                className={`relative shrink-0 rounded-(--radius-control) px-3.5 py-2 text-sm transition-colors ${
                  aktywna
                    ? "font-semibold text-brand-deep"
                    : "text-muted hover:bg-paper hover:text-ink"
                }`}
              >
                {aktywna && (
                  <motion.span
                    layoutId="pastylka-skutecznosc"
                    aria-hidden
                    transition={
                      reduced
                        ? { duration: 0 }
                        : { type: "spring", stiffness: 520, damping: 42 }
                    }
                    className="absolute inset-0 rounded-(--radius-control) bg-brand-wash"
                  />
                )}
                <span className="relative whitespace-nowrap">{z.label}</span>
              </button>
            );
          })}
        </div>

        <div
          role="tabpanel"
          id={`panel-${zakladka}`}
          aria-labelledby={`zakladka-${zakladka}`}
          className="mt-5"
        >
          {zakladka === "rynki" && (
            <div className="max-w-3xl">
              {klasy && (
                <div className="mb-4 rounded-(--radius-card) border border-hairline bg-card px-4 py-3.5">
                  <p
                    className="text-[10px] uppercase tracking-wide text-faint"
                    title="Karty oznaczone jako TOP powinny wchodzić częściej niż solidne. Jeśli tak nie jest, oznaczenia trzeba poprawić."
                  >
                    czy oznaczenia kart się bronią
                  </p>
                  <div className="mt-1.5 flex flex-wrap gap-x-5 gap-y-1">
                    {["top", "mocny", "solidny"]
                      .filter((k) => klasy[k])
                      .map((k) => (
                        <span
                          key={k}
                          className="font-data text-[11px] text-ink-soft"
                        >
                          <span className="text-faint">{k}</span>{" "}
                          <span className="font-semibold">
                            {Math.round(klasy[k].skutecznosc * 100)}%
                          </span>
                          <span className="text-faint">
                            {" "}
                            ({klasy[k].trafione}/{klasy[k].n})
                          </span>
                        </span>
                      ))}
                  </div>
                </div>
              )}

              {rynkiWidoku.length > 0 ? (
                <>
                  <p className="mb-3 max-w-prose text-sm leading-relaxed text-muted">
                    Dla każdego rynku porównujemy dwie rzeczy: ile model{" "}
                    <strong className="font-semibold">obiecywał</strong>, a ile
                    faktycznie <strong className="font-semibold">weszło</strong>
                    . Ostatnia kolumna to różnica między nimi — na minusie
                    znaczy, że model był zbyt pewny siebie. Rynki, na których
                    rozliczyło się mniej niż {N_ISTOTNE} typów, są wyszarzone:
                    to jeszcze o niczym nie świadczy.
                  </p>
                  <div className="overflow-x-auto rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card)">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-hairline bg-card-soft text-left text-[11px] uppercase tracking-wide text-faint">
                          <th className="px-4 py-2.5 font-medium">rynek</th>
                          <th className="px-4 py-2.5 font-medium">weszło</th>
                          <th className="hidden px-4 py-2.5 font-medium sm:table-cell">
                            obiecywał
                          </th>
                          <th className="hidden px-4 py-2.5 font-medium sm:table-cell">
                            wyszło
                          </th>
                          <th className="px-4 py-2.5 font-medium">różnica</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-hairline">
                        {rynkiWidoku.map((r) => {
                          const roznica = r.czestosc - r.sr_p_model;
                          const chudy = r.n < N_ISTOTNE;
                          return (
                            <tr
                              key={r.rynek_kod}
                              className={`even:bg-card-soft transition-colors hover:bg-brand-wash/40 ${
                                chudy ? "text-faint" : ""
                              }`}
                              title={
                                chudy
                                  ? `Za mało rozliczeń (${r.n}) — te liczby jeszcze nic nie znaczą`
                                  : undefined
                              }
                            >
                              <td className="px-4 py-2.5 font-medium">
                                {r.rynek}
                              </td>
                              <td className="font-data px-4 py-2.5">
                                {r.trafione}/{r.n}
                              </td>
                              <td className="font-data hidden px-4 py-2.5 text-muted sm:table-cell">
                                {fmtProc(r.sr_p_model)}
                              </td>
                              <td className="font-data hidden px-4 py-2.5 sm:table-cell">
                                {fmtProc(r.czestosc)}
                              </td>
                              <td
                                className={`font-data px-4 py-2.5 font-semibold ${
                                  chudy
                                    ? ""
                                    : roznica >= 0
                                      ? "text-data-green"
                                      : roznica < -0.1
                                        ? "text-data-red"
                                        : "text-data-amber-ink"
                                }`}
                              >
                                {roznica >= 0 ? "+" : "−"}
                                {Math.abs(roznica * 100).toFixed(0)} pp
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                </>
              ) : (
                <p className="rounded-(--radius-card) border border-hairline bg-card px-4 py-3.5 text-sm text-muted shadow-(--shadow-card)">
                  Drabinki liczą szansę zupełnie inaczej niż model, więc nie ma
                  sensu wrzucać ich do jednej tabeli — mieszalibyśmy dwie różne
                  rzeczy. Ich jakość widać wyżej, w rozbiciu na klasy kart.
                </p>
              )}
            </div>
          )}

          {zakladka === "kupony" && kuponyPanel}
          {zakladka === "test" && testPanel}
        </div>
      </div>
      )}
    </div>
  );
}
