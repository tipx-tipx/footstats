import { PageHeader } from "@/components/PageHeader";
import { Reveal } from "@/components/Reveal";
import { getKupony, getMeta } from "@/lib/data";
import { fmtDataCzas, fmtKurs, fmtLinia, fmtProc, STRONA_LABEL } from "@/lib/format";

export const metadata = { title: "Kupony — FootStats" };

const HORYZONTY: {
  kod: "dzienny" | "dlugoterminowy" | "value";
  tytul: string;
  opis: string;
}[] = [
  {
    kod: "dzienny",
    tytul: "Na dziś",
    opis: "Mecze z dzisiaj (a gdy gra mało drużyn — także z jutra). Krótkie oczekiwanie, więcej wydarzeń z jednego meczu.",
  },
  {
    kod: "dlugoterminowy",
    tytul: "Długoterminowe (1–4 dni)",
    opis: "Legi rozłożone na kilka dni — model wybiera z pełnej puli nadchodzących meczów, więc jakość legów jest najwyższa.",
  },
  {
    kod: "value",
    tytul: "Value",
    opis: "Wyłącznie typy z matematyczną przewagą nad bukmacherem, maksymalnie jeden z meczu — kupon nastawiony na zysk w długiej serii.",
  },
];

export default async function KuponyPage() {
  const [kupony, meta] = await Promise.all([getKupony(), getMeta()]);

  return (
    <div>
      <PageHeader
        eyebrow="ako po analizie"
        title="Kupony budowane przez model"
        lead={
          <>
            Każdy leg przechodzi pełną analizę modelu (historia, minuty, składy
            z dwóch źródeł, matchup), a do kuponu wchodzą legi o najlepszym
            stosunku pewności do kursu — do 4 wydarzeń z jednego meczu, z karą
            korelacyjną za łączenie w ramach meczu. Szansa kuponu = iloczyn
            szans legów.
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
        HORYZONTY.map((h) => {
          const grupa = kupony.filter((k) => (k.horyzont ?? "value") === h.kod);
          if (grupa.length === 0) return null;
          return (
            <section key={h.kod} className="mt-9">
              <Reveal>
                <h2 className="text-lg font-semibold">{h.tytul}</h2>
                <p className="mt-1 max-w-3xl text-sm text-muted">{h.opis}</p>
              </Reveal>
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                {grupa.map((k, i) => (
            <Reveal key={`${k.horyzont}-${k.cel}`} delay={Math.min(i * 0.06, 0.25)}>
              <article className="flex h-full flex-col rounded-2xl border border-hairline bg-card shadow-(--shadow-card) transition-shadow hover:shadow-(--shadow-card-hover)">
                <header className="flex items-center justify-between gap-3 border-b border-hairline px-5 py-4">
                  <span className="flex items-center gap-2">
                    <span className="font-data rounded-lg bg-brand px-3 py-1 text-lg font-bold text-white">
                      ×{k.cel_label ?? k.cel}
                    </span>
                    <span
                      className={`rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                        k.styl === "value"
                          ? "bg-data-green-wash text-brand-deep"
                          : "bg-paper text-muted"
                      }`}
                    >
                      {k.styl === "value" ? "value" : "pewniaki"}
                    </span>
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
            </section>
          );
        })
      )}
    </div>
  );
}
