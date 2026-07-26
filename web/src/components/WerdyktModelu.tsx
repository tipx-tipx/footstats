import { fmtProc, fmtU } from "@/lib/format";
import type { Meta, Strumien, TypyWyniki } from "@/lib/types";
import { OSTATNIA_ZMIANA, poZmianie } from "@/lib/zmiany";

/**
 * WERDYKT — jedyna rzecz, którą widać bez przewijania.
 *
 * Zakładka miała siedem sekcji jedna pod drugą i żadna nie odpowiadała na
 * pytanie, po które się tu wchodzi: „czy to zarabia?". Odpowiadamy pierwszym
 * zdaniem, liczbami obok, a dopiero potem wpuszczamy w szczegóły (zakładki
 * niżej). Zero retuszu: gdy model traci, ma być napisane, że traci.
 */

const ETYKIETY: Record<Strumien, string> = {
  pewniaki: "typy zawodnicze",
  druzyny: "rynki drużynowe",
  drabinki: "drabinki",
};

/** "2026-07-26" → "26 lipca" (południe lokalne, żeby strefa nie cofała daty). */
function dataPl(dzien: string): string {
  return new Date(`${dzien}T12:00:00`).toLocaleDateString("pl-PL", {
    day: "numeric",
    month: "long",
  });
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

export function WerdyktModelu({
  typy,
  meta,
}: {
  typy: TypyWyniki;
  meta: Meta;
}) {
  const p = typy.podsumowanie;
  if (!p || p.rozliczone === 0) return null;

  const hit = p.trafione / p.rozliczone;
  // deklaracja modelu = średnia szansa ważona próbą per rynek; to ona ma być
  // zestawiona z trafieniami, bo różnica tych dwóch liczb jest całym problemem
  const n_dekl = typy.po_rynku.reduce((s, r) => s + r.n, 0);
  const deklaracja = n_dekl
    ? typy.po_rynku.reduce((s, r) => s + r.sr_p_model * r.n, 0) / n_dekl
    : null;

  const dni = typy.skutecznosc_dzienna ?? [];
  const naPlusie = dni.filter((d) => d.roi_flat > 0.005).length;
  const naMinusie = dni.filter((d) => d.roi_flat < -0.005).length;
  const zRozliczeniami = naPlusie + naMinusie;

  const zarabia = p.roi_flat > 0;
  const strumienie = typy.skutecznosc_strumienie ?? {};
  // strumień, który najmocniej ciągnie wynik w dół — reszta zdania „skąd strata"
  const wgStraty = (["pewniaki", "druzyny", "drabinki"] as Strumien[])
    .map((k) => ({ k, s: strumienie[k] }))
    .filter((x) => (x.s?.podsumowanie.rozliczone ?? 0) > 0)
    .sort(
      (a, b) =>
        (a.s!.podsumowanie.roi_flat ?? 0) - (b.s!.podsumowanie.roi_flat ?? 0),
    );
  const winowajca = wgStraty[0];
  const udzialWinowajcy =
    winowajca && p.roi_flat < 0
      ? winowajca.s!.podsumowanie.roi_flat / p.roi_flat
      : 0;

  const wstrzymane = Object.values(meta.kwarantanna ?? {});
  const swiezych = dni.filter((d) => poZmianie(d.dzien)).length;

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
              Na razie{" "}
              <span className="text-data-green">wychodzi na plus</span>
            </>
          ) : (
            <>
              Model{" "}
              <span className="text-data-red">jeszcze nie zarabia</span>
            </>
          )}
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
          Na {p.rozliczone} rozliczonych typach bilans to{" "}
          <strong className="font-semibold text-ink">{fmtU(p.roi_flat)}</strong>{" "}
          przy stawce jednej jednostki na typ.
          {deklaracja != null && (
            <>
              {" "}
              Trafia {fmtProc(hit)}, choć zapowiadał {fmtProc(deklaracja)} —
              i to ta różnica, nie sam pech, robi wynik.
            </>
          )}
          {winowajca && udzialWinowajcy > 0.6 && (
            <>
              {" "}
              Prawie cała strata siedzi w jednym miejscu:{" "}
              <strong className="font-semibold text-ink">
                {ETYKIETY[winowajca.k]}
              </strong>{" "}
              ({fmtU(winowajca.s!.podsumowanie.roi_flat)} z{" "}
              {fmtU(p.roi_flat)}).
            </>
          )}
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-y-5 px-5 py-5 sm:flex sm:items-stretch sm:px-6">
        <Liczba
          etykieta="bilans (1 j. na typ)"
          wartosc={fmtU(p.roi_flat)}
          ton={p.roi_flat > 0 ? "dodatni" : p.roi_flat < 0 ? "ujemny" : undefined}
          tytul="Suma wypłat minus suma stawek, przy jednej jednostce na każdy typ z kursem"
        />
        <div className="min-w-0 sm:ml-6 sm:border-l sm:border-hairline-strong/60 sm:pl-6">
          <Liczba
            etykieta={`trafione (${p.trafione}/${p.rozliczone})`}
            wartosc={fmtProc(hit)}
          />
        </div>
        {deklaracja != null && (
          <div className="min-w-0 sm:ml-6 sm:border-l sm:border-hairline-strong/60 sm:pl-6">
            <Liczba
              etykieta="tyle zapowiadał"
              wartosc={fmtProc(deklaracja)}
              tytul="Średnia szansa, jaką model dawał tym typom, ważona liczbą rozliczeń"
            />
          </div>
        )}
        {p.clv_sr_pct != null && (p.clv_n ?? 0) > 0 && (
          <div className="min-w-0 sm:ml-6 sm:border-l sm:border-hairline-strong/60 sm:pl-6">
            <Liczba
              etykieta={`kurs vs zamknięcie (${p.clv_n})`}
              wartosc={`${p.clv_sr_pct >= 0 ? "+" : "−"}${Math.abs(p.clv_sr_pct).toFixed(1).replace(".", ",")}%`}
              ton={p.clv_sr_pct > 0 ? "dodatni" : p.clv_sr_pct < 0 ? "ujemny" : undefined}
              tytul="CLV: o ile procent kurs wzięty przy publikacji był lepszy od kursu tuż przed meczem. Dodatni = bierzemy lepszą cenę niż rynek na koniec."
            />
          </div>
        )}
      </dl>

      {zRozliczeniami > 0 && (
        <div className="border-t border-hairline px-5 py-4 sm:px-6">
          <div className="flex items-center justify-between gap-4 text-xs">
            <span className="text-muted">
              <strong className="font-semibold text-ink">{naPlusie}</strong> z{" "}
              {zRozliczeniami} dni na plusie
            </span>
            <span className="text-faint">{naMinusie} dni stratnych</span>
          </div>
          <div
            className="mt-2 flex h-2 overflow-hidden rounded-full bg-paper"
            role="img"
            aria-label={`${naPlusie} dni zyskownych, ${naMinusie} stratnych`}
          >
            <span
              className="bg-data-green/70"
              style={{ width: `${(naPlusie / zRozliczeniami) * 100}%` }}
            />
            <span
              className="bg-data-red/60"
              style={{ width: `${(naMinusie / zRozliczeniami) * 100}%` }}
            />
          </div>
        </div>
      )}

      {OSTATNIA_ZMIANA && wstrzymane.length > 0 && (
        <p className="border-t border-hairline px-5 py-4 text-xs leading-relaxed text-muted sm:px-6">
          <strong className="font-semibold text-ink">Co z tym robimy:</strong>{" "}
          od {dataPl(OSTATNIA_ZMIANA.od)} {OSTATNIA_ZMIANA.opis} Wstrzymane
          właśnie {wstrzymane.length === 1 ? "jest" : "są"}:{" "}
          {wstrzymane.map((k) => k.nazwa.toLowerCase()).join(", ")} — nie
          publikujemy stamtąd typów, dopóki nie przestaną tracić.{" "}
          {swiezych > 0
            ? `Dni po zmianie: ${swiezych} — na ocenę wciąż za mało.`
            : "Nowe zasady nie mają jeszcze ani jednego rozliczenia."}
        </p>
      )}
    </div>
  );
}
