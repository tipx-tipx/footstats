import { CalibrationChart } from "@/components/CalibrationChart";
import { getKalibracja, getMeta } from "@/lib/data";

export const metadata = { title: "Skuteczność modelu — FootStats" };

export default async function ModelPage() {
  const [kal, meta] = await Promise.all([getKalibracja(), getMeta()]);

  return (
    <div className="pt-10">
      <h1 className="text-2xl font-bold">Skuteczność modelu</h1>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
        Zanim zaufasz jakiejkolwiek predykcji, sprawdź, czy model mówi prawdę.
        Ta strona to uczciwy test: model przewidywał zdarzenia w{" "}
        {meta.meczow_kalibracja} meczach, których <strong>nie widział</strong>{" "}
        podczas nauki, a potem porównaliśmy przewidywania z tym, co naprawdę
        się wydarzyło.
        {meta.tryb === "ms2026" && (
          <>
            {" "}
            Test przeprowadzono na Premier League — to ten sam rdzeń modelu,
            który liczy predykcje MŚ.
          </>
        )}
      </p>

      {kal.razem && (
        <div className="mt-6 inline-flex flex-wrap items-center gap-x-8 gap-y-3 rounded-(--radius-card) border border-hairline bg-card px-5 py-4 shadow-(--shadow-card)">
          <div>
            <p className="text-xs text-faint">sprawdzonych predykcji</p>
            <p className="font-data text-2xl font-semibold">{kal.razem.n}</p>
          </div>
          <div>
            <p className="text-xs text-faint">
              wynik Briera{" "}
              <span title="Średni kwadrat błędu prognozy: 0 = ideał, 0,25 = rzut monetą. Im niżej, tym lepiej.">
                ⓘ
              </span>
            </p>
            <p className="font-data text-2xl font-semibold">
              {kal.razem.brier.toFixed(3).replace(".", ",")}
            </p>
          </div>
          <p className="max-w-xs text-xs leading-relaxed text-muted">
            0 = jasnowidz, 0,25 = rzut monetą. Wynik poniżej 0,20 oznacza,
            że model realnie rozróżnia, co jest prawdopodobne, a co nie.
          </p>
        </div>
      )}

      <h2 className="mt-10 text-lg font-semibold">Kalibracja po rynkach</h2>
      <p className="mt-1 max-w-3xl text-sm text-muted">
        Punkt na przekątnej = model idealnie skalibrowany (gdy mówi „60%”,
        zdarzenie zachodzi w 60% przypadków). Wielkość punktu = liczba
        predykcji w kubełku.
      </p>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {kal.rynki.map((r) => (
          <div
            key={r.kod}
            className="rounded-(--radius-card) border border-hairline bg-card p-4 shadow-(--shadow-card)"
          >
            <div className="mb-1 flex items-baseline justify-between">
              <h3 className="font-semibold">{r.nazwa}</h3>
              <span className="font-data text-xs text-muted">
                Brier {r.brier.toFixed(3).replace(".", ",")} · n={r.n}
              </span>
            </div>
            <CalibrationChart bins={r.kubelki} size={240} />
          </div>
        ))}
      </div>

      {kal.rynki.length === 0 && (
        <p className="mt-6 rounded-lg border border-hairline bg-card p-4 text-sm text-muted">
          Za mało danych do kalibracji — uruchom dłuższy backfill w pipeline.
        </p>
      )}
    </div>
  );
}
