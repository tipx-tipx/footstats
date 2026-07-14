import { fmtDataCzas, fmtKurs, fmtLinia, fmtProc, STRONA_LABEL } from "@/lib/format";
import type { KuponHistoria } from "@/lib/types";

/**
 * Karta kuponu w historii — zamrożona przy publikacji, rozwijana do pełnego
 * składu legów (zgrupowanych po meczu). Używana i w „Kupony — historia",
 * i w sekcji wszystkich wygranych kuponów.
 */
export function KuponHistoriaCard({
  k,
  name,
}: {
  k: KuponHistoria;
  /** grupa <details name> — rozwinięcie jednego zamyka sąsiada */
  name?: string;
}) {
  const rozliczone = k.legi_rozliczone ?? 0;
  const trafione = k.legi_trafione ?? 0;
  return (
    <details
      name={name}
      className={`group rounded-xl border bg-card shadow-(--shadow-card) ${
        k.wynik === "wygrany"
          ? "border-data-green/40"
          : k.wynik === "przegrany"
            ? "border-data-red/30"
            : "border-hairline"
      }`}
    >
      <summary className="cursor-pointer list-none px-4 py-3.5 [&::-webkit-details-marker]:hidden">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-2">
            <span className="font-data rounded-md bg-brand px-2 py-0.5 text-sm font-bold text-on-brand">
              ×{k.cel_label ?? k.cel}
            </span>
            <span className="text-xs text-muted">
              {k.horyzont === "dzienny"
                ? "dzienny"
                : k.horyzont === "value"
                  ? "value"
                  : "długoterminowy"}{" "}
              · {k.dzien}
            </span>
            {k.pominiety && (
              <span
                className="rounded bg-paper px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-faint"
                title={
                  k.pomin_powod
                    ? `Pominięty (${k.pomin_powod}) — niezagrany, rozliczony tylko do nauki modelu`
                    : "Pominięty przyciskiem — niezagrany, rozliczony tylko po to, żeby model się uczył"
                }
              >
                pominięty
              </span>
            )}
          </span>
          <span
            className={`text-xs font-semibold ${
              k.wynik === "wygrany"
                ? "text-data-green"
                : k.wynik === "przegrany"
                  ? "text-data-red"
                  : k.wynik === "anulowany"
                    ? "text-faint"
                    : "text-data-amber-ink"
            }`}
            title={k.powod}
          >
            {k.wynik === "wygrany"
              ? `✓ wygrany${k.kurs_rozliczony ? ` @${k.kurs_rozliczony.toFixed(2).replace(".", ",")}` : ""}`
              : k.wynik === "przegrany"
                ? "✗ przegrany"
                : k.wynik === "anulowany"
                  ? "anulowany (składy)"
                  : k.wynik === "zwrot"
                    ? "zwrot (stawka wraca)"
                    : "w grze"}
          </span>
        </div>
        <p className="font-data mt-2 flex items-center justify-between text-xs text-muted">
          <span>
            kurs {k.kurs_laczny.toFixed(2).replace(".", ",")} · szansa{" "}
            {fmtProc(k.p_model)} · legi: {trafione}/{rozliczone} rozliczonych z{" "}
            {k.legi.length}
          </span>
          <span className="text-faint transition-transform group-open:rotate-180">
            ▾
          </span>
        </p>
      </summary>
      {/* rozwinięcie: pełny kupon — legi zgrupowane po meczu */}
      <div className="border-t border-hairline pb-2">
        {k.legi.map((l, li) => {
          const nowyMecz = li === 0 || k.legi[li - 1].mecz_id !== l.mecz_id;
          return (
            <div key={`${l.mecz_id}-${l.podmiot}-${l.rynek}-${li}`}>
              {nowyMecz && (
                <p className="flex items-baseline justify-between gap-2 border-b border-hairline bg-paper px-4 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-ink-soft">
                  {l.mecz}
                  <span className="font-normal normal-case tracking-normal text-faint">
                    {fmtDataCzas(l.kickoff_ts)}
                  </span>
                </p>
              )}
              <div className="flex items-center gap-2.5 px-4 py-2">
                <span
                  aria-hidden
                  className={`h-2 w-2 shrink-0 rounded-full ${
                    l.wynik === "wygrany"
                      ? "bg-data-green"
                      : l.wynik === "przegrany"
                        ? "bg-data-red"
                        : l.wynik === "zwrot"
                          ? "bg-data-amber"
                          : "bg-hairline"
                  }`}
                  title={
                    l.wynik === "wygrany"
                      ? "trafiony"
                      : l.wynik === "przegrany"
                        ? "nietrafiony"
                        : l.wynik === "zwrot"
                          ? "zwrot (nie zagrał / brak danych)"
                          : "w grze"
                  }
                />
                <p className="min-w-0 flex-1 truncate text-sm">
                  <span
                    className={`font-semibold ${
                      l.wynik === "przegrany"
                        ? "text-data-red"
                        : l.wynik === "zwrot"
                          ? "text-faint line-through"
                          : ""
                    }`}
                  >
                    {l.podmiot}
                  </span>{" "}
                  <span className="text-muted">
                    {l.rynek.toLowerCase()} {STRONA_LABEL[l.strona]}{" "}
                    {fmtLinia(l.linia)}
                  </span>
                </p>
                <span className="font-data shrink-0 text-xs text-muted">
                  {fmtProc(l.p_model)}
                </span>
                <span className="font-data shrink-0 rounded-md bg-paper px-1.5 py-0.5 text-xs font-semibold">
                  {fmtKurs(l.kurs)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </details>
  );
}
