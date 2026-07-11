import { CalibrationChart } from "@/components/CalibrationChart";
import { KuponHistoriaCard } from "@/components/KuponHistoriaCard";
import { PageHeader } from "@/components/PageHeader";
import { Reveal } from "@/components/Reveal";
import { SkutecznoscDzienna } from "@/components/SkutecznoscDzienna";
import { getKalibracja, getMeta, getTypyWyniki } from "@/lib/data";
import { fmtLinia, fmtProc } from "@/lib/format";

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

      {/* skuteczność dzień po dniu — przełącznik (realne typy, bez osobnych) */}
      {(typy.skutecznosc_dzienna?.length ?? 0) > 0 && (
        <Reveal className="mt-10">
          <h2 className="text-lg font-semibold">Skuteczność dzień po dniu</h2>
          <p className="mt-1 max-w-3xl text-sm text-muted">
            Trafienia i ROI realnych typów rozliczonych danego dnia. Przełączaj
            się strzałkami albo klikaj słupki — cofniesz się nawet o ~2 tygodnie.
          </p>
          <SkutecznoscDzienna dni={typy.skutecznosc_dzienna!} />
        </Reveal>
      )}

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
          {/* ROI kuponów per horyzont: stawka 1 j./kupon, pominięte nie grają */}
          {typy.kupony_roi && Object.keys(typy.kupony_roi).length > 0 && (
            <div className="mt-4 grid max-w-4xl gap-3 sm:grid-cols-3">
              {(["dzienny", "dlugoterminowy", "value"] as const).map((h) => {
                const d = typy.kupony_roi![h];
                if (!d) return null;
                const label =
                  h === "dzienny"
                    ? "dzienne"
                    : h === "value"
                      ? "value"
                      : "długoterminowe";
                return (
                  <div
                    key={h}
                    className="rounded-xl border border-hairline bg-card px-4 py-3 shadow-(--shadow-card)"
                  >
                    <p className="text-[10px] uppercase tracking-wide text-faint">
                      kupony {label} · zagrane {d.n}
                    </p>
                    <p className="font-data mt-1 text-lg font-semibold">
                      <span
                        className={
                          d.roi_j > 0
                            ? "text-data-green"
                            : d.roi_j < 0
                              ? "text-data-red"
                              : ""
                        }
                      >
                        {d.roi_j > 0 ? "+" : ""}
                        {d.roi_j.toFixed(2).replace(".", ",")} j.
                      </span>
                    </p>
                    <p className="mt-0.5 text-xs text-muted">
                      wygrane {d.wygrane}/{d.n} · z {d.n} j. wróciło{" "}
                      {d.zwrot_j.toFixed(2).replace(".", ",")} j.
                    </p>
                  </div>
                );
              })}
            </div>
          )}
          {/* items-start: rozwinięcie jednego kuponu nie rozciąga sąsiada
              w rzędzie (puste białe tło) — każda karta trzyma swoją wysokość */}
          <div className="mt-4 grid max-w-4xl items-start gap-3 sm:grid-cols-2">
            {typy.kupony!.slice(0, 12).map((k) => (
              <KuponHistoriaCard
                key={k.klucz ?? `${k.horyzont}-${k.cel_label}-${k.dzien}`}
                k={k}
                name="kupon-historia"
              />
            ))}
          </div>
        </Reveal>
      )}

      {/* WSZYSTKIE wygrane kupony — trwały log, nigdy nie znikają */}
      {(typy.kupony_wygrane?.length ?? 0) > 0 && (
        <Reveal className="mt-10">
          <h2 className="text-lg font-semibold">
            Wygrane kupony{" "}
            <span className="font-data text-base font-normal text-data-green">
              ({typy.kupony_wygrane!.length})
            </span>
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-muted">
            Każdy kupon, który się kiedykolwiek trafił — zostaje tu na stałe,
            niezależnie od tego, jak dawno temu (i czy był grany, czy pominięty).
            To pełna kronika trafień modelu.
          </p>
          <div className="mt-4 grid max-w-4xl items-start gap-3 sm:grid-cols-2">
            {typy.kupony_wygrane!.map((k) => (
              <KuponHistoriaCard
                key={k.klucz ?? `${k.horyzont}-${k.cel_label}-${k.dzien}`}
                k={k}
                name="kupon-wygrany"
              />
            ))}
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
