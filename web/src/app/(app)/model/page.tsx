import { CalibrationChart } from "@/components/CalibrationChart";
import { KalendarzWynikow } from "@/components/KalendarzWynikow";
import { KuponHistoriaCard } from "@/components/KuponHistoriaCard";
import { PageHeader } from "@/components/PageHeader";
import { Reveal } from "@/components/Reveal";
import { SkutecznoscDzienna } from "@/components/SkutecznoscDzienna";
import { getKalibracja, getMeta, getTypyWyniki } from "@/lib/data";
import { fmtProc } from "@/lib/format";

export const metadata = { title: "Skuteczność modelu – FootStats" };

/** Nagłówek sekcji: eyebrow z kreską marki + tytuł display. */
function SectionHead({
  eyebrow,
  title,
}: {
  eyebrow: string;
  title: React.ReactNode;
}) {
  return (
    <>
      <p className="flex items-center gap-2.5 text-xs font-semibold uppercase tracking-widest text-brand">
        <span aria-hidden className="h-px w-6 bg-brand-bright" />
        {eyebrow}
      </p>
      <h2 className="mt-2 text-xl font-bold tracking-tight sm:text-2xl">
        {title}
      </h2>
    </>
  );
}

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
            <strong>nie widział podczas nauki</strong>, a potem porównaliśmy
            przewidywania z tym, co naprawdę się wydarzyło.
            {meta.tryb === "ms2026" &&
              " Test przeprowadzono na Premier League. To ten sam rdzeń modelu, który liczy predykcje MŚ."}
          </>
        }
      />

      {kal.razem && (
        <Reveal className="mt-7">
          <div className="max-w-3xl rounded-(--radius-card) border border-hairline bg-card px-5 py-4 shadow-(--shadow-card) sm:px-6 sm:py-5">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
              <dl className="flex items-stretch">
                <div className="min-w-0">
                  <dd className="font-data text-3xl font-semibold leading-none">
                    {kal.razem.n}
                  </dd>
                  <dt className="mt-1.5 text-[11px] leading-tight text-faint">
                    sprawdzonych predykcji
                  </dt>
                </div>
                <div
                  className="ml-6 min-w-0 border-l border-hairline-strong/60 pl-6"
                  title="Średni kwadrat błędu prognozy: 0 = ideał, 0,25 = rzut monetą. Im niżej, tym lepiej."
                >
                  <dd className="font-data text-3xl font-semibold leading-none text-data-green">
                    {kal.razem.brier.toFixed(3).replace(".", ",")}
                  </dd>
                  <dt className="mt-1.5 text-[11px] leading-tight text-faint">
                    wynik Briera ⓘ
                  </dt>
                </div>
              </dl>
              <p className="text-xs leading-relaxed text-muted sm:ml-6 sm:max-w-56 sm:border-l sm:border-hairline-strong/60 sm:pl-6">
                0 = jasnowidz, 0,25 = rzut monetą. Poniżej 0,20 model realnie
                rozróżnia, co jest prawdopodobne.
              </p>
            </div>
          </div>
        </Reveal>
      )}

      {/* rozliczenia realnych typów — automatyczne po każdym meczu */}
      <Reveal className="mt-12">
        <SectionHead eyebrow="test na żywo" title="Realne typy" />
        <p className="mt-2 max-w-3xl text-sm text-muted">
          Każdy publikowany typ trafia do logu z zamrożoną szansą i kursem,
          a po meczu system sam sprawdza wynik (statystyki per strzał i per
          zawodnik). Od 25 rozliczonych typów na rynek model zacznie dokręcać
          kalibrację na tej podstawie.
        </p>
        {pods && pods.rozliczone > 0 ? (
          <>
            <div className="mt-5 max-w-3xl rounded-(--radius-card) border border-hairline bg-card px-5 py-4 shadow-(--shadow-card) sm:px-6 sm:py-5">
              <dl className="grid grid-cols-2 gap-y-5 sm:flex sm:items-stretch sm:gap-0">
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
                ].map((s, i) => (
                  <div
                    key={s.label}
                    className={`min-w-0 ${
                      i > 0
                        ? "sm:ml-6 sm:border-l sm:border-hairline-strong/60 sm:pl-6"
                        : ""
                    }`}
                    title={"title" in s ? (s.title as string) : undefined}
                  >
                    <dd
                      className={`font-data text-[1.45rem] font-semibold leading-none ${"tone" in s ? s.tone : ""}`}
                    >
                      {s.value}
                    </dd>
                    <dt className="mt-1.5 text-[11px] leading-tight text-faint">
                      {s.label}
                    </dt>
                  </div>
                ))}
              </dl>
            </div>
            {typy.po_rynku.length > 0 && (
              <div className="mt-4 max-w-3xl overflow-x-auto rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card)">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-hairline bg-card-soft text-left text-[11px] uppercase tracking-wide text-faint">
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
                      <tr
                        key={r.rynek_kod}
                        className="even:bg-card-soft transition-colors hover:bg-brand-wash/40"
                      >
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
            {/* lista rozliczonych typów przeniesiona do „Skuteczność dzień
                po dniu" (per dzień, co siadło) — tu już jej nie dublujemy */}
          </>
        ) : (
          <p className="mt-4 max-w-3xl rounded-(--radius-card) border border-hairline bg-card px-4 py-3.5 text-sm text-muted shadow-(--shadow-card)">
            Log już zbiera publikowane typy. Pierwsze rozliczenia pojawią się
            automatycznie po zakończeniu najbliższych meczów
            {pods ? ` (w logu: ${pods.opublikowane})` : ""}.
          </p>
        )}
      </Reveal>

      {/* kalendarz wyników — bilans każdego dnia, nic nie znika */}
      {(typy.skutecznosc_dzienna?.length ?? 0) > 0 && (
        <Reveal className="mt-12">
          <SectionHead eyebrow="kalendarz wyników" title="Dzień po dniu, bez retuszu" />
          <p className="mt-2 max-w-3xl text-sm text-muted">
            Bilans realnych typów każdego dnia przy stawce 1 jednostki na typ.
            Dni stratne zostają w kalendarzu tak samo jak zyskowne.
          </p>
          <div className="mt-4 max-w-3xl">
            <KalendarzWynikow dni={typy.skutecznosc_dzienna!} />
          </div>
        </Reveal>
      )}

      {/* skuteczność dzień po dniu — przełącznik (realne typy, bez osobnych) */}
      {(typy.skutecznosc_dzienna?.length ?? 0) > 0 && (
        <Reveal className="mt-12">
          <SectionHead eyebrow="dzień po dniu" title="Skuteczność" />
          <p className="mt-2 max-w-3xl text-sm text-muted">
            Trafienia i ROI realnych typów rozliczonych danego dnia. Przełączaj
            się strzałkami albo klikaj słupki, cofniesz się nawet o ~2 tygodnie.
          </p>
          <SkutecznoscDzienna dni={typy.skutecznosc_dzienna!} />
        </Reveal>
      )}

      {/* historia kuponów — zamrażane przy starcie 1. meczu, rozliczane z legów */}
      {(typy.kupony?.length ?? 0) > 0 && (
        <Reveal className="mt-12">
          <SectionHead eyebrow="historia" title="Kupony" />
          <p className="mt-2 max-w-3xl text-sm text-muted">
            Kupon zamraża się w chwili publikacji. Zmienia się tylko wtedy,
            gdy ogłoszone składy wywrócą któryś typ (wtedy jest anulowany
            i powstaje nowy). Jedno pudło = kupon przegrany, a zwrot typu
            (zawodnik nie zagrał) wyłącza go z kursu, jak u bukmachera.
            Statystyki liczone w regularnym czasie gry, bez dogrywek.
          </p>
          {/* ROI kuponów per horyzont: stawka 1 j./kupon, pominięte nie grają */}
          {typy.kupony_roi && Object.keys(typy.kupony_roi).length > 0 && (
            <div className="mt-5 max-w-4xl overflow-hidden rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card)">
              <div className="grid divide-y divide-hairline sm:grid-cols-3 sm:divide-x sm:divide-y-0">
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
                    <div key={h} className="px-5 py-4">
                      <p className="text-[10px] uppercase tracking-wide text-faint">
                        kupony {label} · zagrane {d.n}
                      </p>
                      <p className="font-data mt-1.5 text-xl font-semibold leading-none">
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
                      <p className="mt-1.5 text-xs text-muted">
                        wygrane {d.wygrane}/{d.n} · z {d.n} j. wróciło{" "}
                        {d.zwrot_j.toFixed(2).replace(".", ",")} j.
                      </p>
                    </div>
                  );
                })}
              </div>
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
        <Reveal className="mt-12">
          <SectionHead
            eyebrow="kronika trafień"
            title={
              <>
                Wygrane kupony{" "}
                <span className="font-data text-base font-normal text-data-green">
                  ({typy.kupony_wygrane!.length})
                </span>
              </>
            }
          />
          <p className="mt-2 max-w-3xl text-sm text-muted">
            Każdy kupon, który się kiedykolwiek trafił, zostaje tu na stałe,
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

      <Reveal className="mt-12">
        <SectionHead eyebrow="po rynkach" title="Kalibracja" />
        <p className="mt-2 max-w-3xl text-sm text-muted">
          Punkt na przekątnej = model idealnie skalibrowany (gdy mówi „60%”,
          zdarzenie zachodzi w 60% przypadków). Wielkość punktu = liczba
          predykcji w kubełku.
        </p>
      </Reveal>

      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {kal.rynki.map((r, i) => (
          <Reveal key={r.kod} delay={Math.min(i * 0.05, 0.25)}>
            <div className="rounded-(--radius-card) border border-hairline bg-card p-4 shadow-(--shadow-card) transition-shadow hover:shadow-(--shadow-card-hover)">
              <div className="mb-1 flex items-baseline justify-between gap-3">
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
        <p className="mt-6 rounded-(--radius-card) border border-hairline bg-card p-4 text-sm text-muted shadow-(--shadow-card)">
          Za mało danych do kalibracji. Uruchom dłuższy backfill w pipeline.
        </p>
      )}
    </div>
  );
}
