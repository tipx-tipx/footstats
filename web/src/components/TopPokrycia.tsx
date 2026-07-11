import { fmtKurs, fmtLinia } from "@/lib/format";
import type { WierszPokrycia } from "@/lib/pokrycie";

/**
 * Tabela TOP POKRYCIA: zawodnicy z najlepszym pokryciem historycznym linii.
 * Zielony boks = mecz pokrył linię, czerwony = nie. Kursy dziś tylko Superbet
 * (kolejne buki + kolumna „Lepszy" w przyszłości).
 */
export function TopPokrycia({ wiersze }: { wiersze: WierszPokrycia[] }) {
  if (wiersze.length === 0) {
    return (
      <p className="mt-4 rounded-xl border border-hairline bg-card px-4 py-3.5 text-sm text-muted shadow-(--shadow-card)">
        Brak zawodników z pokryciem ≥ 60% w ostatnich 5 meczach — pojawią się,
        gdy zbierze się dość historii (albo po ogłoszeniu składów).
      </p>
    );
  }
  return (
    <div className="mt-4 overflow-x-auto rounded-2xl border border-hairline bg-card shadow-(--shadow-card)">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="border-b border-hairline text-left text-[11px] uppercase tracking-wide text-faint">
            <th className="px-4 py-2.5 font-medium">rynek</th>
            <th className="px-4 py-2.5 font-medium">zawodnik</th>
            <th className="px-4 py-2.5 font-medium">ostatnie</th>
            <th className="px-4 py-2.5 font-medium">pokrycie</th>
            <th className="px-4 py-2.5 font-medium">linia</th>
            <th className="px-4 py-2.5 font-medium">Superbet</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {wiersze.map((w, i) => (
            <tr
              key={`${w.player_id}-${w.rynek_kod}-${w.linia}-${i}`}
              className="transition-colors hover:bg-paper/60"
            >
              <td className="whitespace-nowrap px-4 py-2.5 font-medium">
                {w.rynek}
              </td>
              <td className="px-4 py-2.5">
                <span className="font-medium">{w.zawodnik}</span>
                <span className="ml-1.5 text-xs text-faint">{w.druzyna}</span>
              </td>
              <td className="px-4 py-2.5">
                <span className="flex gap-1">
                  {w.ostatnie.map((v, vi) => {
                    const pokryl = v >= w.prog;
                    return (
                      <span
                        key={vi}
                        className={`font-data inline-flex h-5 w-5 items-center justify-center rounded text-[11px] font-semibold text-white ${
                          pokryl ? "bg-data-green" : "bg-data-red"
                        }`}
                        title={pokryl ? "pokrył linię" : "nie pokrył"}
                      >
                        {v}
                      </span>
                    );
                  })}
                </span>
              </td>
              <td className="px-4 py-2.5">
                <span
                  className={`font-data font-semibold ${
                    w.pokryte === w.probka ? "text-data-green" : "text-brand-deep"
                  }`}
                >
                  {w.pokryte}/{w.probka}
                </span>
              </td>
              <td className="font-data whitespace-nowrap px-4 py-2.5">
                +{fmtLinia(w.linia)}
              </td>
              <td className="font-data px-4 py-2.5">
                {w.kurs != null ? (
                  <span className="font-semibold">{fmtKurs(w.kurs)}</span>
                ) : (
                  <span className="text-faint">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
