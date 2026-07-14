import { GeneratorKuponu } from "@/components/GeneratorKuponu";
import { CountUpKurs, PasekSzansy } from "@/components/KuponAnim";
import { PageHeader } from "@/components/PageHeader";
import {
  PominKupon,
  ProfilKuponow,
  ZastosujZamiane,
} from "@/components/PominKupon";
import { Reveal } from "@/components/Reveal";
import { getKupony, getLegiPool, getMeta } from "@/lib/data";
import { fmtDataCzas, fmtKurs, fmtLinia, fmtProc, STRONA_LABEL } from "@/lib/format";
import type { KuponLeg } from "@/lib/types";

/** mini-ikonki kontekstu lega (matchup / debiut w XI / miękka linia) */
function LegBadges({ l }: { l: KuponLeg }) {
  return (
    <>
      {l.matchup && (
        <span
          className="shrink-0 text-[11px]"
          title="Profil rywala wyraźnie sprzyja temu rynkowi (matchup)"
        >
          🎯
        </span>
      )}
      {l.rotacja && (
        <span
          className="shrink-0 text-[11px]"
          title="Pierwszy występ w XI na tym turnieju — linia rynku bywa niedograna"
        >
          ⬆
        </span>
      )}
      {l.miekka_linia && (
        <span
          className="shrink-0 text-[11px]"
          title="Linia płaci więcej, niż wynika z reszty siatki Superbetu"
        >
          ↑
        </span>
      )}
    </>
  );
}

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
    opis: "Tu wchodzą wyłącznie typy, za które bukmacher płaci wyraźnie więcej, niż wynosi ich uczciwy kurs (co najmniej +2% na typ) — i maksymalnie jeden typ z meczu. Trafia rzadziej niż pewniaki, ale przy dłuższej serii to matematyka gra dla Ciebie.",
  },
];

export default async function KuponyPage() {
  const [kupony, meta, legiPool] = await Promise.all([
    getKupony(),
    getMeta(),
    getLegiPool(),
  ]);

  return (
    <div>
      <PageHeader
        eyebrow="ako po analizie"
        title="Kupony budowane przez model"
        lead={
          <>
            Każdy leg przechodzi pełną analizę modelu (historia, minuty, składy
            z dwóch źródeł, matchup), a do kuponu wchodzą legi o najlepszym
            stosunku pewności do kursu. Kupon po publikacji jest zamrożony —
            nowy w danym przedziale powstaje, gdy poprzedni się rozliczy,
            gdy ogłoszone składy wywrócą któryś leg albo gdy sam go pominiesz
            przyciskiem pod kartą (pominięty i tak rozliczy się w tle, żeby
            model się uczył). Szansa kuponu = iloczyn szans legów (z karą
            korelacyjną w ramach meczu).
          </>
        }
      />
      <ProfilKuponow />

      {legiPool.length > 0 && (
        <Reveal className="mt-6">
          <details className="group rounded-(--radius-card) border border-hairline bg-paper/40">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-sm font-semibold">
              <span>🧩 Zbuduj własny kupon</span>
              <span className="text-xs font-normal text-faint group-open:hidden">
                wybierz mecze i kurs →
              </span>
            </summary>
            <div className="border-t border-hairline p-3 sm:p-4">
              <p className="mb-3 text-xs leading-relaxed text-muted">
                Złóż kupon z tej samej przeanalizowanej puli, której model używa
                automatycznie — te same bezpieczniki, kary korelacji i premia za
                wartość. Wybierz mecze (albo zostaw wszystkie), ustaw kurs docelowy
                i charakter.
              </p>
              <GeneratorKuponu pool={legiPool} kary={meta.kary_korelacji} />
            </div>
          </details>
        </Reveal>
      )}

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
              {meta.sezon}).
            </p>
          </div>
        </Reveal>
      ) : (
        HORYZONTY.map((h) => {
          const grupa = kupony.filter((k) => (k.horyzont ?? "value") === h.kod);
          // sloty to MAKSIMA (1 kupon na przedział kursowy) — przedział bez
          // kuponu czeka, aż pula legów pozwoli domknąć kurs w widełkach
          const przedzialy =
            h.kod === "dzienny"
              ? ["5–10", "10–15", "15–20", "20–25"]
              : h.kod === "dlugoterminowy"
                ? ["10–15", "15–20", "20–25", "25–35"]
                : ["4–8", "8–16"];
          const puste = przedzialy.filter(
            (p) => !grupa.some((k) => (k.cel_label ?? String(k.cel)) === p),
          );
          if (grupa.length === 0 && puste.length === 0) return null;
          return (
            <section key={h.kod} className="mt-9">
              <Reveal>
                <h2 className="text-lg font-semibold">{h.tytul}</h2>
                <p className="mt-1 max-w-3xl text-sm text-muted">{h.opis}</p>
              </Reveal>
              {/* columns (masonry): karty układają się gęsto w dwóch
                  kolumnach — nieparzysty kupon nie wisi samotnie w rzędzie */}
              <div className="mt-4 columns-1 gap-4 lg:columns-2">
                {grupa.map((k, i) => {
                  // najsłabsze ogniwo: z pipeline'u, awaryjnie liczone z legów
                  const weakIdx =
                    k.najslabszy_idx ??
                    k.legi.reduce(
                      (mi, l, ix, arr) => (l.p_model < arr[mi].p_model ? ix : mi),
                      0,
                    );
                  return (
            <Reveal
              key={k.klucz ?? `${k.horyzont}-${k.cel_label ?? k.cel}`}
              delay={Math.min(i * 0.06, 0.25)}
              className="mb-4 break-inside-avoid"
            >
              <PominKupon
                klucz={k.klucz}
                pokazPrzebuduj={k.horyzont === "dzienny"}
              >
              <article className="flex h-full flex-col rounded-2xl border border-hairline bg-card shadow-(--shadow-card) transition-shadow hover:shadow-(--shadow-card-hover)">
                <header className="flex flex-col gap-3 border-b border-hairline px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
                  <span className="flex items-center gap-2">
                    <span className="font-data rounded-lg bg-brand px-3 py-1 text-lg font-bold text-on-brand">
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
                  <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-left sm:text-right">
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-faint">
                        kurs łączny
                      </p>
                      <CountUpKurs
                        value={k.kurs_laczny}
                        prefix=""
                        className="font-data text-lg font-semibold"
                      />
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
                        z 10 zł robi się
                      </p>
                      <p className="font-data text-lg font-semibold">
                        {Math.round(k.kurs_laczny * 10)} zł
                      </p>
                    </div>
                  </div>
                </header>
                <PasekSzansy p={k.p_model} className="mt-3" />
                {/* oś czasu: który mecz kiedy gra i jak stoją jego legi */}
                {(() => {
                  const mecze: {
                    mecz: string;
                    kickoff: number;
                    legi: typeof k.legi;
                  }[] = [];
                  for (const l of k.legi) {
                    const m = mecze.find((x) => x.mecz === l.mecz);
                    if (m) m.legi.push(l);
                    else
                      mecze.push({ mecz: l.mecz, kickoff: l.kickoff_ts, legi: [l] });
                  }
                  if (mecze.length < 2) return null;
                  return (
                    <div className="flex flex-wrap items-center gap-1.5 border-b border-hairline bg-paper/50 px-4 py-2 sm:px-5">
                      {mecze.map((m) => {
                        const wyniki = m.legi.map((l) => l.wynik);
                        const kolor = wyniki.some((w) => w === "przegrany")
                          ? "bg-data-red"
                          : wyniki.length &&
                              wyniki.every((w) => w === "wygrany" || w === "zwrot")
                            ? "bg-data-green"
                            : "bg-hairline-strong";
                        return (
                          <span
                            key={m.mecz}
                            className="inline-flex items-center gap-1.5 rounded-md bg-card px-2 py-0.5 text-[10px] text-muted"
                            title={m.mecz}
                          >
                            <span
                              className={`h-1.5 w-1.5 rounded-full ${kolor}`}
                              aria-hidden
                            />
                            {fmtDataCzas(m.kickoff)} ·{" "}
                            {m.legi.length === 1 ? "1 typ" : `${m.legi.length} typy`}
                          </span>
                        );
                      })}
                    </div>
                  );
                })()}
                {/* legi zgrupowane po meczu — jak w bet builderze */}
                <div className="flex-1">
                  {k.legi.map((l, li) => {
                    const nowyMecz =
                      li === 0 || k.legi[li - 1].mecz_id !== l.mecz_id;
                    return (
                      <div key={`${l.mecz_id}-${l.value_bet_id}-${li}`}>
                        {nowyMecz && (
                          <p className="flex items-baseline justify-between gap-2 border-y border-hairline bg-paper px-5 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-soft first:border-t-0">
                            {l.mecz}
                            <span className="font-normal normal-case tracking-normal text-faint">
                              {fmtDataCzas(l.kickoff_ts)}
                            </span>
                          </p>
                        )}
                        <div className="px-4 py-2.5 sm:px-5">
                          <div className="flex items-center gap-3">
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-semibold">
                                {l.podmiot}
                                <span className="ml-1.5 font-normal text-muted">
                                  {l.rynek.toLowerCase()} {STRONA_LABEL[l.strona]}{" "}
                                  {fmtLinia(l.linia)}
                                </span>
                              </p>
                            </div>
                            <LegBadges l={l} />
                            {li === weakIdx && k.legi.length > 1 && (
                              <span
                                className="shrink-0 rounded-md bg-data-amber-wash px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-data-amber-ink"
                                title="Leg o najniższej szansie — to on najmocniej ciągnie szansę kuponu w dół"
                              >
                                ⚠ najsłabsze
                              </span>
                            )}
                            <span className="font-data shrink-0 text-xs text-muted">
                              {fmtProc(l.p_model)}
                            </span>
                            <span className="font-data shrink-0 rounded-md bg-paper px-2 py-0.5 text-sm font-semibold">
                              {fmtKurs(l.kurs)}
                            </span>
                          </div>
                          {/* pasek szansy lega — rentgen kuponu na jeden rzut oka */}
                          <div
                            className="mt-1.5 h-[3px] overflow-hidden rounded-full bg-paper"
                            aria-hidden
                          >
                            <div
                              className={`h-full rounded-full ${
                                l.p_model >= 0.65
                                  ? "bg-data-green/80"
                                  : l.p_model >= 0.5
                                    ? "bg-data-amber/80"
                                    : "bg-data-red/70"
                              }`}
                              style={{ width: `${Math.round(l.p_model * 100)}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* rentgen: propozycja wymiany najsłabszego ogniwa (doradcza) */}
                {k.alternatywa && (
                  <div className="border-t border-dashed border-brand/30 bg-brand-wash/40 px-4 py-3.5 sm:px-5">
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-brand">
                      ✦ mocniejsza wersja tego kuponu
                    </p>
                    <p className="mt-1.5 text-sm leading-relaxed">
                      <span className="text-muted line-through decoration-data-red/50">
                        {k.legi[k.alternatywa.zamiast_idx]?.podmiot}{" "}
                        {k.legi[k.alternatywa.zamiast_idx]?.rynek.toLowerCase()}{" "}
                        {fmtLinia(k.legi[k.alternatywa.zamiast_idx]?.linia ?? 0)}
                      </span>{" "}
                      →{" "}
                      <strong>{k.alternatywa.podmiot}</strong>{" "}
                      <span className="text-muted">
                        {k.alternatywa.rynek.toLowerCase()}{" "}
                        {STRONA_LABEL[k.alternatywa.strona]}{" "}
                        {fmtLinia(k.alternatywa.linia)}
                      </span>{" "}
                      <span className="font-data font-semibold">
                        @{fmtKurs(k.alternatywa.kurs)}
                      </span>
                    </p>
                    <p className="font-data mt-1 text-xs text-muted">
                      szansa {fmtProc(k.p_model)} →{" "}
                      <strong className="text-brand-deep">
                        {fmtProc(k.alternatywa.p_po)}
                      </strong>{" "}
                      · kurs {fmtKurs(k.kurs_laczny)} →{" "}
                      {fmtKurs(k.alternatywa.kurs_po)}
                    </p>
                    <ZastosujZamiane klucz={k.klucz} />
                  </div>
                )}
                {/* wariant B: wyraźnie inny zestaw z tej samej puli */}
                {k.wariant_b && (
                  <details className="border-t border-dashed border-hairline">
                    <summary className="cursor-pointer list-none px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted transition-colors hover:text-ink-soft sm:px-5 [&::-webkit-details-marker]:hidden">
                      ⇄ pokaż inny wariant — kurs{" "}
                      {fmtKurs(k.wariant_b.kurs_laczny)}, szansa{" "}
                      {fmtProc(k.wariant_b.p_model)}
                    </summary>
                    <div className="space-y-1 px-4 pb-3 sm:px-5">
                      {k.wariant_b.legi.map((l, wi) => (
                        <p
                          key={`${l.mecz_id}-${l.value_bet_id}-${wi}`}
                          className="flex items-baseline justify-between gap-2 text-xs"
                        >
                          <span className="min-w-0 truncate">
                            <strong>{l.podmiot}</strong>{" "}
                            <span className="text-muted">
                              {l.rynek.toLowerCase()} {STRONA_LABEL[l.strona]}{" "}
                              {fmtLinia(l.linia)} · {l.mecz}
                            </span>
                          </span>
                          <span className="font-data shrink-0">
                            {fmtKurs(l.kurs)}
                          </span>
                        </p>
                      ))}
                      <p className="pt-1 text-[10px] text-faint">
                        wariant podglądowy — jeśli wolisz ten zestaw, zagraj go
                        ręcznie (slot zajmuje wariant główny)
                      </p>
                    </div>
                  </details>
                )}
                {/* rentgen v2: dołożenie pewnego lega, gdy kurs wisi nisko */}
                {k.dolozenie && (
                  <div className="border-t border-dashed border-hairline bg-paper/60 px-4 py-3 sm:px-5">
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-muted">
                      + dobij kurs pewnym legiem
                    </p>
                    <p className="mt-1 text-sm leading-relaxed">
                      <strong>{k.dolozenie.podmiot}</strong>{" "}
                      <span className="text-muted">
                        {k.dolozenie.rynek.toLowerCase()}{" "}
                        {STRONA_LABEL[k.dolozenie.strona]}{" "}
                        {fmtLinia(k.dolozenie.linia)}
                      </span>{" "}
                      <span className="font-data font-semibold">
                        @{fmtKurs(k.dolozenie.kurs)}
                      </span>
                    </p>
                    <p className="font-data mt-1 text-xs text-muted">
                      kurs {fmtKurs(k.kurs_laczny)} →{" "}
                      {fmtKurs(k.dolozenie.kurs_po)} · szansa{" "}
                      {fmtProc(k.p_model)} → {fmtProc(k.dolozenie.p_po)}
                    </p>
                  </div>
                )}
                <footer className="border-t border-hairline px-5 py-3 text-xs leading-relaxed text-faint">
                  taki kupon trafia się statystycznie ~1 na{" "}
                  {Math.max(2, Math.round(1 / Math.max(k.p_model, 1e-9)))} prób ·{" "}
                  {k.legi.length}{" "}
                  {k.legi.length === 1 ? "typ" : k.legi.length < 5 ? "typy" : "typów"}{" "}
                  · kursy: {k.legi[0]?.bukmacher ?? "Superbet"}
                  {k.mecze_lacznie != null && k.mecze_ze_skladami != null && (
                    <>
                      {" "}· składy przy budowie: {k.mecze_ze_skladami}/
                      {k.mecze_lacznie} meczów
                    </>
                  )}
                  {k.styl === "value" && k.ev_pct > 0 && (
                    <span className="mt-0.5 block">
                      wg modelu ten kupon jest wart kurs{" "}
                      <span className="font-data text-ink-soft">
                        {fmtKurs(k.fair_kurs)}
                      </span>
                      , a bukmacher płaci{" "}
                      <span className="font-data text-ink-soft">
                        {fmtKurs(k.kurs_laczny)}
                      </span>{" "}
                      — to jest cała przewaga tego kuponu
                    </span>
                  )}
                </footer>
              </article>
              </PominKupon>
            </Reveal>
                  );
                })}
                {puste.map((p) => (
                  <div
                    key={p}
                    className="mb-4 break-inside-avoid rounded-2xl border border-dashed border-hairline bg-paper/40 px-5 py-6 text-center"
                  >
                    <p className="font-data text-sm font-semibold text-faint">
                      ×{p}
                    </p>
                    <p className="mx-auto mt-1 max-w-[30ch] text-xs leading-relaxed text-faint">
                      przedział czeka — kupon powstanie, gdy z puli legów da
                      się złożyć kurs w tych widełkach (zwykle bliżej meczów)
                    </p>
                  </div>
                ))}
              </div>
            </section>
          );
        })
      )}
    </div>
  );
}
