import type { PokrycieLiga } from "@/lib/types";

/**
 * POKRYCIE SKANU — „czego umiemy policzyć, a czego nie".
 *
 * Zgłoszenie usera 2026-07-27: „w Meczach miały być tabele pokryć wszystkich
 * naszych statystyk, a obecnie jest nic". Pipeline liczy te dane co cykl
 * (`_dump_pokrycie`), ale do tej pory zostawały w pliku i nigdy nie docierały
 * na stronę.
 *
 * Tabela pokazuje ofertę TAK, JAK MY JĄ WIDZIMY. To celowe: jeśli parser
 * przestanie rozumieć nazwę rynku u bukmachera, słupek spadnie do zera i widać
 * to od razu — dwa takie błędy naraz kosztowały nas tydzień zgadywania.
 */

const NAZWY_RYNKOW: Record<string, string> = {
  team_goals: "Gole drużyny",
  team_corners: "Rzuty rożne drużyny",
  team_cards: "Kartki drużyny",
  team_sot: "Celne strzały drużyny",
  team_shots: "Strzały drużyny",
  team_fouls: "Faule drużyny",
  shots: "Strzały",
  sot: "Strzały celne",
  shots_outside_box: "Strzały zza pola karnego",
  sot_outside_box: "Celne zza pola karnego",
  headed_shots: "Strzały głową",
  headed_sot: "Celne strzały głową",
  fouls_committed: "Faule popełnione",
  fouls_won: "Faule wywalczone",
  tackles: "Odbiory",
  interceptions: "Przechwyty",
  offsides: "Spalone",
  shots_blocked: "Strzały zablokowane",
  shots_off_target: "Strzały niecelne",
  yellow_card: "Żółta kartka",
};

function nazwa(kod: string): string {
  return NAZWY_RYNKOW[kod] ?? kod;
}

function Slupek({ ile, zIlu }: { ile: number; zIlu: number }) {
  const proc = zIlu > 0 ? Math.round((ile / zIlu) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-full max-w-[9rem] overflow-hidden rounded-full bg-hairline">
        <div
          className={`h-full rounded-full ${
            proc >= 60
              ? "bg-data-green"
              : proc >= 25
                ? "bg-data-amber"
                : "bg-data-red"
          }`}
          style={{ width: `${Math.max(proc, 2)}%` }}
        />
      </div>
      <span className="font-data shrink-0 text-xs tabular-nums text-muted">
        {ile}/{zIlu}
      </span>
    </div>
  );
}

export function PokrycieSkanu({ pokrycie }: { pokrycie: PokrycieLiga }) {
  const rynki = pokrycie.rynki;
  const rozgrywki = Object.entries(pokrycie.per_rozgrywki ?? {});
  const wZakresie = rozgrywki
    .filter(([, v]) => v.druzynowe)
    .sort((a, b) => b[1].mecze - a[1].mecze);
  const poza = rozgrywki
    .filter(([, v]) => !v.druzynowe)
    .sort((a, b) => b[1].mecze - a[1].mecze);
  const meczowDruz = rynki?.meczow_druzynowych ?? 0;
  const druzynowe = Object.entries(rynki?.druzynowe ?? {}).sort(
    (a, b) => b[1] - a[1],
  );
  const zawodnicze = Object.entries(rynki?.zawodnicze ?? {}).sort(
    (a, b) => b[1] - a[1],
  );

  if (!rynki && rozgrywki.length === 0) return null;

  return (
    <section className="mt-10 space-y-6">
      <div>
        <h2 className="font-display text-lg font-bold tracking-tight">
          Co umiemy policzyć w tych meczach
        </h2>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
          Statystyka trafia do analizy dopiero wtedy, gdy mamy jedno i drugie:
          historię drużyny albo zawodnika i kurs u bukmachera. Poniżej widać, ile
          z tego faktycznie mamy — a puste miejsca mówią, czego dziś nie
          policzymy, nawet gdyby mecz był idealny.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {druzynowe.length > 0 && (
          <div className="rounded-(--radius-card) border border-hairline bg-card p-5 shadow-(--shadow-card)">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-faint">
              Statystyki drużyn
            </h3>
            <p className="mt-1 text-xs text-muted">
              w ilu z {meczowDruz} meczów naszych lig jest kurs
            </p>
            <ul className="mt-4 space-y-2.5">
              {druzynowe.map(([kod, ile]) => (
                <li key={kod} className="text-sm">
                  <p className="mb-1 font-medium">{nazwa(kod)}</p>
                  <Slupek ile={ile} zIlu={meczowDruz} />
                </li>
              ))}
            </ul>
          </div>
        )}

        {zawodnicze.length > 0 && (
          <div className="rounded-(--radius-card) border border-hairline bg-card p-5 shadow-(--shadow-card)">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-faint">
              Statystyki zawodników
            </h3>
            <p className="mt-1 text-xs text-muted">
              ile par zawodnik–statystyka ma kurs w tym skanie
            </p>
            <ul className="mt-4 space-y-1.5">
              {zawodnicze.slice(0, 12).map(([kod, ile]) => (
                <li
                  key={kod}
                  className="flex items-baseline justify-between gap-3 text-sm"
                >
                  <span className="min-w-0 truncate">{nazwa(kod)}</span>
                  <span className="font-data shrink-0 tabular-nums text-muted">
                    {ile}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {rozgrywki.length > 0 && (
        <div className="rounded-(--radius-card) border border-hairline bg-card p-5 shadow-(--shadow-card)">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-faint">
            Rozgrywki w skanie
          </h3>
          <p className="mt-1 text-xs text-muted">
            „sparowane" = mecz, który udało się połączyć z ofertą bukmachera.
            Bez pary nie ma kursów, więc nie ma czego analizować.
          </p>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[28rem] text-sm">
              <thead>
                <tr className="border-b border-hairline text-left text-[11px] uppercase tracking-wide text-faint">
                  <th className="pb-2 font-semibold">Rozgrywki</th>
                  <th className="pb-2 font-semibold">Kraj</th>
                  <th className="pb-2 text-right font-semibold">Mecze</th>
                  <th className="pb-2 text-right font-semibold">Sparowane</th>
                </tr>
              </thead>
              <tbody>
                {wZakresie.map(([nazwaLigi, v]) => (
                  <tr key={nazwaLigi} className="border-b border-hairline/60">
                    <td className="py-2 font-medium">{nazwaLigi}</td>
                    <td className="py-2 text-muted">{v.kraj}</td>
                    <td className="font-data py-2 text-right tabular-nums">
                      {v.mecze}
                    </td>
                    <td className="font-data py-2 text-right tabular-nums">
                      {v.sparowane}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {poza.length > 0 && (
            <details className="mt-4">
              <summary className="cursor-pointer text-xs font-medium text-muted hover:text-ink">
                Poza naszym zakresem: {poza.length} rozgrywek,{" "}
                {poza.reduce((s, [, v]) => s + v.mecze, 0)} meczów
              </summary>
              <p className="mt-2 text-xs leading-relaxed text-muted">
                Te mecze są w skanie, ale nie liczymy dla nich statystyk
                drużynowych — nie mamy stamtąd historii, więc każda liczba
                byłaby zgadywaniem.
              </p>
              <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
                {poza.map(([nazwaLigi, v]) => (
                  <li key={nazwaLigi}>
                    {nazwaLigi}{" "}
                    <span className="font-data tabular-nums">({v.mecze})</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
