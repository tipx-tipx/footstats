import { CountUpKurs, PasekSzansy } from "./KuponAnim";
import {
  fmtDataCzas,
  fmtKurs,
  fmtLinia,
  fmtProc,
  STRONA_LABEL,
} from "@/lib/format";
import type { Kupon, KuponLeg } from "@/lib/types";

/** mini-znaczniki kontekstu typu (matchup / debiut w XI / miękka linia) */
function LegBadges({ l }: { l: KuponLeg }) {
  return (
    <>
      {l.matchup && (
        <span
          className="shrink-0 text-[11px] font-semibold text-brand"
          title="Profil rywala wyraźnie sprzyja temu rynkowi (matchup)"
        >
          ◎
        </span>
      )}
      {l.rotacja && (
        <span
          className="shrink-0 text-[11px] font-semibold text-data-amber-ink"
          title="Pierwszy występ w XI na tym turnieju, linia rynku bywa niedograna"
        >
          ↥
        </span>
      )}
      {l.miekka_linia && (
        <span
          className="shrink-0 text-[11px] font-semibold text-brand"
          title="Linia płaci więcej, niż wynika z reszty siatki Superbetu"
        >
          ↑
        </span>
      )}
    </>
  );
}

/**
 * Bilet kuponu — jedna anatomia wszędzie (scena na /kupony, zajawka na
 * głównej ma swoją wersję mini): gradientowy nagłówek z liczbami, pasek
 * szansy, perforacja, typy pogrupowane po meczu, krótka stopka faktów.
 * Cała głębia (rentgen, warianty, akcje) żyje POZA biletem — bilet ma
 * wyglądać jak coś, co chce się zagrać, nie jak panel administracyjny.
 */
export function KuponBilet({
  kupon: k,
  stawka = 10,
}: {
  kupon: Kupon;
  /** globalna stawka użytkownika do przelicznika „z X zł robi się" */
  stawka?: number;
}) {
  const weakIdx =
    k.najslabszy_idx ??
    k.legi.reduce((mi, l, ix, arr) => (l.p_model < arr[mi].p_model ? ix : mi), 0);

  // oś czasu meczów (tylko gdy kupon łączy 2+ meczów)
  const mecze: { mecz: string; kickoff: number; legi: KuponLeg[] }[] = [];
  for (const l of k.legi) {
    const m = mecze.find((x) => x.mecz === l.mecz);
    if (m) m.legi.push(l);
    else mecze.push({ mecz: l.mecz, kickoff: l.kickoff_ts, legi: [l] });
  }

  return (
    <article className="flex h-full flex-col overflow-hidden rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card) transition-shadow hover:shadow-(--shadow-card-hover)">
      {/* nagłówek biletu */}
      <header className="bg-gradient-to-br from-brand-wash via-brand-wash/60 to-card px-4 pb-4 pt-4 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="font-display flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-brand">
            <span aria-hidden className="h-px w-5 bg-brand-bright" />
            kupon ×{k.cel_label ?? k.cel}
          </p>
          <span
            className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
              k.styl === "value"
                ? "bg-data-green-wash text-data-green-ink"
                : "bg-card-soft text-muted"
            }`}
          >
            {k.styl === "value" ? "value" : "pewniaki"}
          </span>
        </div>
        <div className="mt-3.5 flex flex-wrap items-end gap-x-7 gap-y-2.5">
          <div title="Kursy wszystkich typów pomnożone przez siebie: tyle razy rośnie stawka, gdy wejdzie całość">
            <p className="text-[10px] uppercase tracking-wide text-faint">
              kurs łączny
            </p>
            <CountUpKurs
              value={k.kurs_laczny}
              prefix="×"
              className="font-data mt-0.5 block text-[1.7rem] font-bold leading-none"
            />
          </div>
          <div title="Prawdopodobieństwo, że wejdą wszystkie typy naraz (wg modelu, z karą za typy z jednego meczu)">
            <p className="text-[10px] uppercase tracking-wide text-faint">
              szansa modelu
            </p>
            <p className="font-data mt-0.5 text-lg font-semibold leading-tight">
              {fmtProc(k.p_model)}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wide text-faint">
              z {stawka} zł robi się
            </p>
            <p className="font-data mt-0.5 text-lg font-semibold leading-tight">
              {Math.round(k.kurs_laczny * stawka)} zł
            </p>
          </div>
        </div>
        <PasekSzansy p={k.p_model} className="mt-3.5" />
      </header>

      {/* perforacja biletu */}
      <div aria-hidden className="relative">
        <span className="absolute -left-2.5 top-1/2 h-5 w-5 -translate-y-1/2 rounded-full border border-hairline bg-paper" />
        <span className="absolute -right-2.5 top-1/2 h-5 w-5 -translate-y-1/2 rounded-full border border-hairline bg-paper" />
        <span className="mx-4 block border-t border-dashed border-hairline-strong sm:mx-5" />
      </div>

      {/* oś czasu: który mecz kiedy gra i jak stoją jego typy */}
      {mecze.length >= 2 && (
        <div className="flex flex-wrap items-center gap-1.5 px-4 pb-2.5 pt-3 sm:px-5">
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
                className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-card-soft px-2 py-0.5 text-[10px] text-muted"
                title={m.mecz}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${kolor}`} aria-hidden />
                {fmtDataCzas(m.kickoff)} ·{" "}
                {m.legi.length === 1 ? "1 typ" : `${m.legi.length} typy`}
              </span>
            );
          })}
        </div>
      )}

      {/* typy zgrupowane po meczu — jak w bet builderze */}
      <div className="flex-1">
        {k.legi.map((l, li) => {
          const nowyMecz = li === 0 || k.legi[li - 1].mecz_id !== l.mecz_id;
          return (
            <div key={`${l.mecz_id}-${l.value_bet_id}-${li}`}>
              {nowyMecz && (
                <p className="flex items-baseline justify-between gap-2 border-b border-hairline bg-card-soft px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-soft sm:px-5">
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
                      className="shrink-0 rounded-full bg-data-amber-wash px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-data-amber-ink"
                      title="Typ o najniższej szansie. To on najmocniej ciągnie szansę kuponu w dół"
                    >
                      najsłabszy
                    </span>
                  )}
                  <span className="font-data shrink-0 text-xs text-muted">
                    {fmtProc(l.p_model)}
                  </span>
                  <span className="font-data shrink-0 rounded-(--radius-control) border border-hairline bg-card-soft px-2 py-0.5 text-sm font-semibold">
                    {fmtKurs(l.kurs)}
                  </span>
                </div>
                {/* pasek szansy typu — rentgen na jeden rzut oka */}
                <div
                  className="mt-1.5 h-[3px] overflow-hidden rounded-full bg-hairline/60"
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

      {/* krótka stopka faktów; interpretacje żyją w panelu obok biletu */}
      <footer className="border-t border-hairline bg-card-soft/70 px-4 py-2.5 text-xs text-faint sm:px-5">
        {k.legi.length}{" "}
        {k.legi.length === 1 ? "typ" : k.legi.length < 5 ? "typy" : "typów"} ·
        kursy: {k.legi[0]?.bukmacher ?? "Superbet"}
        {k.mecze_lacznie != null && k.mecze_ze_skladami != null && (
          <>
            {" "}
            · składy przy budowie: {k.mecze_ze_skladami}/{k.mecze_lacznie}{" "}
            meczów
          </>
        )}
      </footer>
    </article>
  );
}
