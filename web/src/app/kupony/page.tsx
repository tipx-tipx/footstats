import { PageHeader } from "@/components/PageHeader";
import { Reveal } from "@/components/Reveal";
import { getKupony, getMeta } from "@/lib/data";
import { fmtDataCzas, fmtKurs, fmtLinia, fmtProc, STRONA_LABEL } from "@/lib/format";

export const metadata = { title: "Kupony — FootStats" };

export default async function KuponyPage() {
  const [kupony, meta] = await Promise.all([getKupony(), getMeta()]);

  return (
    <div>
      <PageHeader
        eyebrow="ako po analizie"
        title="Kupony budowane przez model"
        lead={
          <>
            Model składa kupony z pojedynczych typów z wartością — celując w
            łączne kursy ~5, ~10, ~15 i ~20. Zasady twarde: tylko typy z
            dodatnią wartością i pewnością co najmniej średnią, maksymalnie
            jeden typ z meczu (wyniki w meczu są od siebie zależne — sklejanie
            ich zawyża szansę). Szansa kuponu = iloczyn szans, wartość = szansa
            × kurs − 1.
          </>
        }
      />

      {kupony.length === 0 ? (
        <Reveal className="mt-8">
          <div className="rounded-2xl border border-hairline bg-card px-8 py-14 text-center shadow-(--shadow-card)">
            <p className="font-semibold">
              Za mało typów z wartością na sensowny kupon
            </p>
            <p className="mx-auto mt-1.5 max-w-md text-sm leading-relaxed text-muted">
              Kupon wymaga co najmniej dwóch niezależnych typów z dodatnią
              wartością i przyzwoitą pewnością. Model nie skleja legów na siłę
              — kupony pojawią się, gdy rynek da okazje ({meta.liga}{" "}
              {meta.sezon}, kursy odświeżane co ~30 minut).
            </p>
          </div>
        </Reveal>
      ) : (
        <div className="mt-8 grid gap-4 lg:grid-cols-2">
          {kupony.map((k, i) => (
            <Reveal key={k.cel} delay={Math.min(i * 0.06, 0.25)}>
              <article className="flex h-full flex-col rounded-2xl border border-hairline bg-card shadow-(--shadow-card) transition-shadow hover:shadow-(--shadow-card-hover)">
                <header className="flex items-center justify-between gap-3 border-b border-hairline px-5 py-4">
                  <span className="font-data rounded-lg bg-brand px-3 py-1 text-lg font-bold text-white">
                    ×{k.cel}
                  </span>
                  <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-right">
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-faint">
                        kurs łączny
                      </p>
                      <p className="font-data text-lg font-semibold">
                        {fmtKurs(k.kurs_laczny)}
                      </p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-faint">
                        szansa modelu
                      </p>
                      <p className="font-data text-lg font-semibold">
                        {fmtProc(k.p_model)}
                      </p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-faint">
                        wartość
                      </p>
                      <p
                        className={`font-data text-lg font-semibold ${
                          k.ev_pct > 0 ? "text-data-green" : "text-data-red"
                        }`}
                      >
                        {k.ev_pct > 0 ? "+" : ""}
                        {k.ev_pct.toFixed(1).replace(".", ",")}%
                      </p>
                    </div>
                  </div>
                </header>
                <ul className="flex-1 divide-y divide-hairline">
                  {k.legi.map((l) => (
                    <li key={l.value_bet_id} className="flex items-center gap-3 px-5 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold">
                          {l.podmiot}
                          <span className="ml-1.5 font-normal text-muted">
                            {l.rynek.toLowerCase()} {STRONA_LABEL[l.strona]}{" "}
                            {fmtLinia(l.linia)}
                          </span>
                        </p>
                        <p className="truncate text-xs text-faint">
                          {l.mecz} · {fmtDataCzas(l.kickoff_ts)}
                        </p>
                      </div>
                      <span className="font-data text-xs text-muted">
                        {fmtProc(l.p_model)}
                      </span>
                      <span className="font-data rounded-md bg-paper px-2 py-0.5 text-sm font-semibold">
                        {fmtKurs(l.kurs)}
                      </span>
                    </li>
                  ))}
                </ul>
                <footer className="border-t border-hairline px-5 py-3 text-xs text-faint">
                  uczciwy kurs kuponu: {fmtKurs(k.fair_kurs)} · {k.legi.length}{" "}
                  {k.legi.length === 1 ? "typ" : k.legi.length < 5 ? "typy" : "typów"}{" "}
                  · kursy: {k.legi[0]?.bukmacher ?? "Superbet"}
                </footer>
              </article>
            </Reveal>
          ))}
        </div>
      )}
    </div>
  );
}
