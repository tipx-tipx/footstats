import { CalibrationChart } from "@/components/CalibrationChart";
import { PageHeader } from "@/components/PageHeader";
import { Reveal } from "@/components/Reveal";
import { getKalibracja, getMeta, getTypyWyniki } from "@/lib/data";
import {
  fmtDataCzas,
  fmtKurs,
  fmtLinia,
  fmtProc,
  STRONA_LABEL,
} from "@/lib/format";

export const metadata = { title: "Skuteczność modelu — FootStats" };

export default async function ModelPage() {
  const [kal, meta, typy] = await Promise.all([
    getKalibracja(),
    getMeta(),
    getTypyWyniki(),
  ]);
  const pods = typy.podsumowanie;

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

      {/* rozliczenia realnych typów — automatyczne po każdym meczu */}
      <Reveal className="mt-10">
        <h2 className="text-lg font-semibold">Realne typy — test na żywo</h2>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          Każdy publikowany typ trafia do logu z zamrożoną szansą i kursem,
          a po meczu system sam sprawdza wynik (statystyki per strzał i per
          zawodnik). Od 25 rozliczonych typów na rynek model zacznie dokręcać
          kalibrację na tej podstawie.
        </p>
        {pods && pods.rozliczone > 0 ? (
          <>
            <dl className="mt-4 grid max-w-3xl grid-cols-2 gap-2.5 sm:grid-cols-4">
              {[
                { label: "typów w logu", value: String(pods.opublikowane) },
                { label: "rozliczonych", value: String(pods.rozliczone) },
                {
                  label: "trafionych",
                  value: `${pods.trafione}/${pods.rozliczone} (${Math.round(
                    (pods.trafione / Math.max(pods.rozliczone, 1)) * 100,
                  )}%)`,
                },
                {
                  label: "ROI (stawka 1 j. na okazję)",
                  value: `${pods.roi_flat >= 0 ? "+" : ""}${pods.roi_flat
                    .toFixed(2)
                    .replace(".", ",")} j.`,
                  tone:
                    pods.roi_flat > 0
                      ? "text-data-green"
                      : pods.roi_flat < 0
                        ? "text-data-red"
                        : "",
                },
                ...(pods.clv_sr_pct != null && (pods.clv_n ?? 0) > 0
                  ? [
                      {
                        label: `śr. CLV (${pods.clv_n} typów) ⓘ`,
                        value: `${pods.clv_sr_pct >= 0 ? "+" : ""}${pods.clv_sr_pct
                          .toFixed(1)
                          .replace(".", ",")}%`,
                        tone:
                          pods.clv_sr_pct > 0
                            ? "text-data-green"
                            : pods.clv_sr_pct < 0
                              ? "text-data-red"
                              : "",
                        title:
                          "Closing Line Value: o ile % kurs wzięty przy publikacji był lepszy od kursu tuż przed meczem. Systematycznie dodatnie CLV = bijemy rynek (najszybszy miernik jakości typów).",
                      },
                    ]
                  : []),
              ].map((s) => (
                <div
                  key={s.label}
                  className="rounded-xl border border-hairline bg-card px-3.5 py-3 shadow-(--shadow-card)"
                  title={"title" in s ? (s.title as string) : undefined}
                >
                  <dd
                    className={`font-data text-xl font-semibold ${"tone" in s ? s.tone : ""}`}
                  >
                    {s.value}
                  </dd>
                  <dt className="mt-0.5 text-[11px] leading-tight text-faint">
                    {s.label}
                  </dt>
                </div>
              ))}
            </dl>
            {typy.po_rynku.length > 0 && (
              <div className="mt-4 max-w-3xl overflow-x-auto rounded-xl border border-hairline bg-card shadow-(--shadow-card)">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-hairline text-left text-[11px] uppercase tracking-wide text-faint">
                      <th className="px-4 py-2.5 font-medium">rynek</th>
                      <th className="px-4 py-2.5 font-medium">trafione</th>
                      <th className="px-4 py-2.5 font-medium" title="Średnia szansa, jaką dawał model">
                        model mówił
                      </th>
                      <th className="px-4 py-2.5 font-medium">było</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {typy.po_rynku.map((r) => (
                      <tr key={r.rynek_kod}>
                        <td className="px-4 py-2.5 font-medium">{r.rynek}</td>
                        <td className="font-data px-4 py-2.5">
                          {r.trafione}/{r.n}
                        </td>
                        <td className="font-data px-4 py-2.5 text-muted">
                          {fmtProc(r.sr_p_model)}
                        </td>
                        <td className="font-data px-4 py-2.5">
                          {fmtProc(r.czestosc)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {typy.ostatnie.length > 0 && (
              <ul className="mt-4 max-w-3xl space-y-1.5">
                {typy.ostatnie.slice(0, 12).map((t, i) => (
                  <li
                    key={`${t.mecz}-${t.podmiot}-${t.rynek_kod}-${i}`}
                    className="flex items-center gap-3 rounded-lg border border-hairline bg-card px-3.5 py-2 text-sm"
                  >
                    <span
                      aria-hidden
                      className={`h-2 w-2 shrink-0 rounded-full ${
                        t.wynik === "wygrany"
                          ? "bg-data-green"
                          : t.wynik === "przegrany"
                            ? "bg-data-red"
                            : "bg-data-amber"
                      }`}
                    />
                    <span className="min-w-0 flex-1 truncate">
                      <span className="font-medium">{t.podmiot}</span>{" "}
                      <span className="text-muted">
                        {t.rynek.toLowerCase()} pow. {fmtLinia(t.linia)} · {t.mecz}
                      </span>
                    </span>
                    <span className="font-data shrink-0 text-xs text-muted">
                      było: {t.faktyczna != null ? t.faktyczna : "—"}
                    </span>
                    {t.clv_pct != null && (
                      <span
                        className={`font-data hidden shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold sm:inline-flex ${
                          t.clv_pct > 0
                            ? "bg-data-green-wash text-brand-deep"
                            : t.clv_pct < 0
                              ? "bg-data-red-wash text-data-red"
                              : "bg-paper text-muted"
                        }`}
                        title={`Wzięty @${t.kurs?.toFixed(2).replace(".", ",")}, zamknięcie @${t.kurs_zamkniecia?.toFixed(2).replace(".", ",")} — dodatnie CLV = kurs lepszy niż wycena rynku na koniec`}
                      >
                        CLV {t.clv_pct > 0 ? "+" : ""}
                        {t.clv_pct.toFixed(0)}%
                      </span>
                    )}
                    <span
                      className={`shrink-0 text-xs font-semibold ${
                        t.wynik === "wygrany"
                          ? "text-data-green"
                          : t.wynik === "przegrany"
                            ? "text-data-red"
                            : "text-[#8a5613]"
                      }`}
                    >
                      {t.wynik === "wygrany" ? "✓ trafiony" : t.wynik === "przegrany" ? "✗ nietrafiony" : "zwrot"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <p className="mt-4 max-w-3xl rounded-xl border border-hairline bg-card px-4 py-3.5 text-sm text-muted shadow-(--shadow-card)">
            Log już zbiera publikowane typy — pierwsze rozliczenia pojawią się
            automatycznie po zakończeniu najbliższych meczów
            {pods ? ` (w logu: ${pods.opublikowane})` : ""}.
          </p>
        )}
      </Reveal>

      {/* historia kuponów — zamrażane przy starcie 1. meczu, rozliczane z legów */}
      {(typy.kupony?.length ?? 0) > 0 && (
        <Reveal className="mt-10">
          <h2 className="text-lg font-semibold">Kupony — historia</h2>
          <p className="mt-1 max-w-3xl text-sm text-muted">
            Kupon zamraża się w chwili publikacji — zmienia się tylko wtedy,
            gdy ogłoszone składy wywrócą któryś leg (wtedy jest anulowany
            i powstaje nowy). Jedno pudło = kupon przegrany, zwrot lega
            (zawodnik nie zagrał) wyłącza go z kursu — jak u bukmachera.
            Statystyki liczone w regularnym czasie gry, bez dogrywek.
          </p>
          {/* items-start: rozwinięcie jednego kuponu nie rozciąga sąsiada
              w rzędzie (puste białe tło) — każda karta trzyma swoją wysokość */}
          <div className="mt-4 grid max-w-4xl items-start gap-3 sm:grid-cols-2">
            {typy.kupony!.slice(0, 12).map((k) => {
              const rozliczone = k.legi_rozliczone ?? 0;
              const trafione = k.legi_trafione ?? 0;
              return (
                <details
                  key={k.klucz ?? `${k.horyzont}-${k.cel_label}-${k.dzien}`}
                  name="kupon-historia"
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
                        <span className="font-data rounded-md bg-brand px-2 py-0.5 text-sm font-bold text-white">
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
                            title="Pominięty przyciskiem — niezagrany, rozliczony tylko po to, żeby model się uczył"
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
                                : "text-[#8a5613]"
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
                        kurs {k.kurs_laczny.toFixed(2).replace(".", ",")} ·
                        szansa {fmtProc(k.p_model)} · legi: {trafione}/
                        {rozliczone} rozliczonych z {k.legi.length}
                      </span>
                      <span className="text-faint transition-transform group-open:rotate-180">
                        ▾
                      </span>
                    </p>
                  </summary>
                  {/* rozwinięcie: pełny kupon — legi zgrupowane po meczu */}
                  <div className="border-t border-hairline pb-2">
                    {k.legi.map((l, li) => {
                      const nowyMecz =
                        li === 0 || k.legi[li - 1].mecz_id !== l.mecz_id;
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
                                {l.rynek.toLowerCase()}{" "}
                                {STRONA_LABEL[l.strona]} {fmtLinia(l.linia)}
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
            })}
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
