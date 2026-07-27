"use client";

import { useStawka } from "./useStawka";
import { fmtProc, fmtU } from "@/lib/format";
import { OSTATNIA_ZMIANA } from "@/lib/zmiany";

/**
 * WERDYKT — jedyna rzecz, którą widać bez przewijania.
 *
 * Zakładka miała siedem sekcji jedna pod drugą i żadna nie odpowiadała na
 * pytanie, po które się tu wchodzi: „czy to zarabia?". Odpowiadamy pierwszym
 * zdaniem, liczbami obok, a dopiero potem wpuszczamy w szczegóły.
 *
 * DWA WIDOKI TYCH SAMYCH LICZB (2026-07-27, przygotowanie pod klienta):
 *
 *   klient — trzy liczby i złotówki. „−46,8u" nie znaczy nic, „−936 zł przy
 *            20 zł na typ" znaczy wszystko. „Ile trzeba trafiać" i „tyle sam
 *            obiecywał" to pytania, na które klient nie umie odpowiedzieć,
 *            więc tylko dokładają szumu.
 *   admin  — komplet, bo to są liczby DIAGNOSTYCZNE: różnica „obiecywał vs
 *            trafia" mówi, czy model kłamie o własnej pewności, a próg
 *            opłacalności — ile realnie brakuje do zysku. Mylenie tych dwóch
 *            to najczęstszy błąd w rozmowie o wyniku.
 *
 * PRÓG OPŁACALNOŚCI liczymy z realnych kursów rozliczonych typów
 * (1 / średni kurs), nie z założenia.
 */

/** "2026-07-26" → "26 lipca" (południe lokalne, żeby strefa nie cofała daty). */
function dataPl(dzien: string): string {
  return new Date(`${dzien}T12:00:00`).toLocaleDateString("pl-PL", {
    day: "numeric",
    month: "long",
  });
}

/** Bilans w jednostkach → złotówki przy stawce usera ("+124 zł", "−936 zł"). */
function zlote(jednostki: number, stawka: number): string {
  const v = Math.round(jednostki * stawka);
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v)} zł`;
}

function Liczba({
  etykieta,
  wartosc,
  ton,
  tytul,
}: {
  etykieta: React.ReactNode;
  wartosc: string;
  ton?: "dodatni" | "ujemny";
  tytul?: string;
}) {
  return (
    <div className="min-w-0" title={tytul}>
      <p
        className={`font-data text-2xl font-semibold leading-none sm:text-[1.75rem] ${
          ton === "dodatni"
            ? "text-data-green"
            : ton === "ujemny"
              ? "text-data-red"
              : "text-ink"
        }`}
      >
        {wartosc}
      </p>
      <p className="mt-1.5 text-[11px] leading-tight text-faint">{etykieta}</p>
    </div>
  );
}

/** Kolumna z pionową kreską oddzielającą (na desktopie). */
function Kolumna({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-w-0 sm:ml-6 sm:border-l sm:border-hairline-strong/60 sm:pl-6">
      {children}
    </div>
  );
}

export interface WerdyktDane {
  /** nazwa filtra w zdaniu: "typach", "typach drużynowych", "kartach drabinek" */
  coLiczymy: string;
  rozliczone: number;
  trafione: number;
  roi: number;
  /** średnia szansa deklarowana przez model (ważona próbą); null gdy brak */
  deklaracja: number | null;
  /** próg opłacalności: 1 / średni kurs rozliczonych typów; null gdy brak kursów */
  prog: number | null;
  clv?: number | null;
  clvN?: number;
  naPlusie: number;
  naMinusie: number;
  /** zdanie „prawie cała strata siedzi w…" — tylko gdy jeden produkt dominuje */
  winowajca?: { nazwa: string; roi: number } | null;
  /** rynki i powody wstrzymane przez kwarantannę (nazwy po polsku) */
  wstrzymane: string[];
  /** ile dni z rozliczeniami mamy JUŻ po zmianie zasad */
  dniPoZmianie: number;
}

export function WerdyktModelu({
  d,
  pelnyWglad = true,
}: {
  d: WerdyktDane;
  /** false = widok klienta: trzy liczby, złotówki, bez kuchni */
  pelnyWglad?: boolean;
}) {
  const [stawka, setStawka] = useStawka();
  if (d.rozliczone === 0) return null;

  const hit = d.trafione / d.rozliczone;
  const zarabia = d.roi > 0;
  const zRozliczeniami = d.naPlusie + d.naMinusie;
  // różnicę liczymy z liczb, KTÓRE POKAZUJEMY (po zaokrągleniu) — inaczej
  // czytelnik widzi „60% wobec 63%" i obok „brakuje 4 pp"
  const brakuje =
    d.prog != null ? Math.round(d.prog * 100) - Math.round(hit * 100) : null;

  return (
    <div className="rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card)">
      <div className="border-b border-hairline px-5 py-5 sm:px-6">
        <p className="flex items-center gap-2.5 text-xs font-semibold uppercase tracking-widest text-brand">
          <span aria-hidden className="h-px w-6 bg-brand-bright" />
          werdykt
        </p>
        <h2 className="mt-2.5 text-xl font-bold tracking-tight sm:text-2xl">
          {zarabia ? (
            <>
              Na razie <span className="text-data-green">wychodzi na plus</span>
            </>
          ) : (
            <>
              Na razie <span className="text-data-red">jesteśmy pod kreską</span>
            </>
          )}
        </h2>

        {pelnyWglad ? (
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
            Na {d.rozliczone} rozliczonych {d.coLiczymy} bilans to{" "}
            <strong className="font-semibold text-ink">{fmtU(d.roi)}</strong>.
            {brakuje != null && d.prog != null && (
              <>
                {" "}
                Trafia{" "}
                <strong className="font-semibold text-ink">{fmtProc(hit)}</strong>
                , a przy tych kursach musi{" "}
                <strong className="font-semibold text-ink">
                  {fmtProc(d.prog)}
                </strong>
                , żeby wyjść na zero —{" "}
                {brakuje > 0
                  ? `brakuje ${brakuje} ${brakuje === 1 ? "punktu procentowego" : "punktów procentowych"}`
                  : brakuje < 0
                    ? `ma ${Math.abs(brakuje)} pp zapasu`
                    : "jest dokładnie na progu"}
                .
              </>
            )}
            {d.deklaracja != null && <> Sam obiecywał {fmtProc(d.deklaracja)}.</>}
            {d.winowajca && (
              <>
                {" "}
                Prawie cała strata siedzi w jednym miejscu:{" "}
                <strong className="font-semibold text-ink">
                  {d.winowajca.nazwa}
                </strong>{" "}
                ({fmtU(d.winowajca.roi)} z {fmtU(d.roi)}).
              </>
            )}
          </p>
        ) : (
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
            Grając po {stawka} zł na każdy z {d.rozliczone} rozliczonych typów,
            miałbyś dziś{" "}
            <strong
              className={`font-semibold ${zarabia ? "text-data-green" : "text-data-red"}`}
            >
              {zlote(d.roi, stawka)}
            </strong>
            . Weszło {d.trafione} z {d.rozliczone}.
          </p>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-y-5 px-5 py-5 sm:flex sm:items-stretch sm:px-6">
        <Liczba
          etykieta={pelnyWglad ? "bilans" : `bilans przy ${stawka} zł na typ`}
          wartosc={pelnyWglad ? fmtU(d.roi) : zlote(d.roi, stawka)}
          ton={d.roi > 0 ? "dodatni" : d.roi < 0 ? "ujemny" : undefined}
          tytul="Ile zostałoby w kieszeni, gdybyś zagrał każdy z tych typów tą samą stawką: wypłaty minus to, co postawione"
        />
        <Kolumna>
          <Liczba
            etykieta={`weszło (${d.trafione}/${d.rozliczone})`}
            wartosc={fmtProc(hit)}
          />
        </Kolumna>
        {!pelnyWglad && (
          <Kolumna>
            <Liczba
              etykieta="rozliczonych typów"
              wartosc={String(d.rozliczone)}
              tytul="Wszystko, co kiedykolwiek pokazaliśmy i co już się zakończyło — razem z tym, co nie weszło"
            />
          </Kolumna>
        )}
        {pelnyWglad && d.prog != null && (
          <Kolumna>
            <Liczba
              etykieta="ile trzeba trafiać"
              wartosc={fmtProc(d.prog)}
              tytul="Przy takich kursach dopiero od tylu trafień wychodzi się na zero. Niżej — dokładasz, wyżej — zarabiasz."
            />
          </Kolumna>
        )}
        {pelnyWglad && d.deklaracja != null && (
          <Kolumna>
            <Liczba
              etykieta="tyle sam obiecywał"
              wartosc={fmtProc(d.deklaracja)}
              tytul="Średnia szansa, jaką model dawał tym typom. Jeśli jest wyraźnie wyżej niż „weszło”, znaczy, że model jest zbyt pewny siebie."
            />
          </Kolumna>
        )}
        {pelnyWglad && d.clv != null && (d.clvN ?? 0) > 0 && (
          <Kolumna>
            <Liczba
              etykieta={`lepszy kurs niż przed meczem (${d.clvN})`}
              wartosc={`${d.clv >= 0 ? "+" : "−"}${Math.abs(d.clv).toFixed(1).replace(".", ",")}%`}
              ton={d.clv > 0 ? "dodatni" : d.clv < 0 ? "ujemny" : undefined}
              tytul="O ile procent kurs, który pokazaliśmy, był lepszy od kursu tuż przed pierwszym gwizdkiem. Na plusie znaczy, że łapiemy cenę, zanim bukmacher ją poprawi."
            />
          </Kolumna>
        )}
      </dl>

      {zRozliczeniami > 0 && (
        <div className="border-t border-hairline px-5 py-4 sm:px-6">
          <div className="flex items-center justify-between gap-4 text-xs">
            <span className="text-muted">
              <strong className="font-semibold text-ink">{d.naPlusie}</strong> z{" "}
              {zRozliczeniami} dni na plusie
            </span>
            <span className="text-faint">{d.naMinusie} dni stratnych</span>
          </div>
          <div
            className="mt-2 flex h-2 overflow-hidden rounded-full bg-paper"
            role="img"
            aria-label={`${d.naPlusie} dni zyskownych, ${d.naMinusie} stratnych`}
          >
            <span
              className="bg-data-green/70"
              style={{ width: `${(d.naPlusie / zRozliczeniami) * 100}%` }}
            />
            <span
              className="bg-data-red/60"
              style={{ width: `${(d.naMinusie / zRozliczeniami) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* STAWKA — dla klienta to jedyny sposób, żeby liczby znaczyły cokolwiek
          osobistego; dla admina jednostki wystarczą, więc nie zabieramy miejsca */}
      {!pelnyWglad && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-hairline px-5 py-3.5 text-xs text-muted sm:px-6">
          <label htmlFor="stawka-werdykt">Przelicz na moją stawkę:</label>
          <input
            id="stawka-werdykt"
            type="number"
            min={1}
            step={1}
            value={stawka}
            onChange={(e) => setStawka(Number(e.target.value))}
            className="font-data w-20 rounded-(--radius-control) border border-hairline bg-card-soft px-2 py-1 text-sm text-ink"
          />
          <span>zł na każdy typ</span>
        </div>
      )}

      {/* JEDNOSTKA I KOLORY wyjaśnione RAZ, zamiast w pięciu tooltipach */}
      {pelnyWglad && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-hairline px-5 py-3.5 text-[11px] text-faint sm:px-6">
          <span>
            <strong className="font-semibold text-ink-soft">1u</strong> = jedna
            stawka. {fmtU(d.roi)} to{" "}
            <strong className="font-semibold text-ink-soft">
              {zlote(d.roi, stawka)}
            </strong>{" "}
            przy {stawka} zł na typ.
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="h-2.5 w-2.5 rounded-[3px] bg-data-green" />
            zysk
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="h-2.5 w-2.5 rounded-[3px] bg-data-red" />
            strata
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="h-2.5 w-2.5 rounded-[3px] bg-data-amber" />
            za mała próba
          </span>
          <span className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="h-2.5 w-2.5 rounded-[3px] border border-hairline bg-card-soft opacity-55"
            />
            stare zasady
          </span>
        </div>
      )}

      {pelnyWglad && OSTATNIA_ZMIANA && d.wstrzymane.length > 0 && (
        <p className="border-t border-hairline px-5 py-4 text-xs leading-relaxed text-muted sm:px-6">
          <strong className="font-semibold text-ink">Co z tym robimy:</strong>{" "}
          od {dataPl(OSTATNIA_ZMIANA.od)} {OSTATNIA_ZMIANA.opis} Wstrzymane
          właśnie {d.wstrzymane.length === 1 ? "jest" : "są"}:{" "}
          {d.wstrzymane.join(", ")} — nie publikujemy stamtąd typów, dopóki nie
          przestaną tracić.{" "}
          {d.dniPoZmianie > 0
            ? `Dni po zmianie: ${d.dniPoZmianie} — na ocenę wciąż za mało.`
            : "Nowe zasady nie mają jeszcze ani jednego rozliczenia."}
        </p>
      )}
    </div>
  );
}
