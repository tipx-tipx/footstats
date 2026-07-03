import { CalibrationChart } from "@/components/CalibrationChart";
import { PageHeader } from "@/components/PageHeader";
import { Reveal } from "@/components/Reveal";
import { getKalibracja, getMeta } from "@/lib/data";

export const metadata = { title: "Skuteczność modelu — FootStats" };

export default async function ModelPage() {
  const [kal, meta] = await Promise.all([getKalibracja(), getMeta()]);

  return (
    <div>
      <PageHeader
        eyebrow="kontrola jakości"
        title="Czy model mówi prawdę?"
        lead={
          <>
            Zanim zaufasz jakiejkolwiek predykcji, sprawdź ją. Model przewidywał
            zdarzenia w {meta.meczow_kalibracja} meczach, których{" "}
            <strong>nie widział podczas nauki</strong> — a potem porównaliśmy
            przewidywania z tym, co naprawdę się wydarzyło.
            {meta.tryb === "ms2026" &&
              " Test przeprowadzono na Premier League — to ten sam rdzeń modelu, który liczy predykcje MŚ."}
          </>
        }
      />

      {kal.razem && (
        <Reveal className="mt-7">
          <div className="grid max-w-2xl grid-cols-2 gap-2.5 sm:grid-cols-3">
            <div className="rounded-xl border border-hairline bg-card px-4 py-3.5 shadow-(--shadow-card)">
              <p className="font-data text-3xl font-semibold">{kal.razem.n}</p>
              <p className="mt-0.5 text-[11px] leading-tight text-faint">
                sprawdzonych predykcji
              </p>
            </div>
            <div className="rounded-xl border border-hairline bg-card px-4 py-3.5 shadow-(--shadow-card)">
              <p className="font-data text-3xl font-semibold text-data-green">
                {kal.razem.brier.toFixed(3).replace(".", ",")}
              </p>
              <p
                className="mt-0.5 text-[11px] leading-tight text-faint"
                title="Średni kwadrat błędu prognozy: 0 = ideał, 0,25 = rzut monetą. Im niżej, tym lepiej."
              >
                wynik Briera ⓘ
              </p>
            </div>
            <div className="col-span-2 flex items-center rounded-xl border border-hairline bg-paper px-4 py-3.5 text-xs leading-relaxed text-muted sm:col-span-1">
              0 = jasnowidz, 0,25 = rzut monetą. Poniżej 0,20 model realnie
              rozróżnia, co jest prawdopodobne.
            </div>
          </div>
        </Reveal>
      )}

      <Reveal className="mt-10">
        <h2 className="text-lg font-semibold">Kalibracja po rynkach</h2>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          Punkt na przekątnej = model idealnie skalibrowany (gdy mówi „60%”,
          zdarzenie zachodzi w 60% przypadków). Wielkość punktu = liczba
          predykcji w kubełku.
        </p>
      </Reveal>

      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {kal.rynki.map((r, i) => (
          <Reveal key={r.kod} delay={Math.min(i * 0.05, 0.25)}>
            <div className="rounded-2xl border border-hairline bg-card p-4 shadow-(--shadow-card) transition-shadow hover:shadow-(--shadow-card-hover)">
              <div className="mb-1 flex items-baseline justify-between">
                <h3 className="font-semibold">{r.nazwa}</h3>
                <span className="font-data text-xs text-muted">
                  Brier {r.brier.toFixed(3).replace(".", ",")} · n={r.n}
                </span>
              </div>
              <CalibrationChart bins={r.kubelki} size={240} />
            </div>
          </Reveal>
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
