import { CalibrationChart } from "@/components/CalibrationChart";
import { KalendarzWynikow } from "@/components/KalendarzWynikow";
import { KuponHistoriaCard } from "@/components/KuponHistoriaCard";
import { PageHeader } from "@/components/PageHeader";
import { Reveal } from "@/components/Reveal";
import { SkutecznoscStrumienie } from "@/components/SkutecznoscStrumienie";
import { SkutecznoscZakladki, type Zakladka } from "@/components/SkutecznoscZakladki";
import { WerdyktModelu } from "@/components/WerdyktModelu";
import { getKalibracja, getMeta, getTypyWyniki } from "@/lib/data";
import { fmtProc, fmtU } from "@/lib/format";

export const metadata = { title: "Skuteczność modelu – FootStats" };

/** Od tylu rozliczeń rynek w tabeli traktujemy jako mówiący cokolwiek. */
const N_ISTOTNE = 10;

/**
 * KONTROLA JAKOŚCI — przebudowa 2026-07-26.
 *
 * Strona miała siedem sekcji jedna pod drugą (Brier, realne typy, kalendarz,
 * strumienie, kupony, kronika wygranych, kalibracja). Każdy dowód potrzebny,
 * ale razem dawały ścianę liczb, przez którą nie było widać odpowiedzi na
 * jedyne pytanie, po które się tu wchodzi. Teraz: werdykt na górze, dowody
 * w zakładkach — jedna rzecz naraz, nic nie usunięte.
 */

/** Nagłówek sekcji WEWNĄTRZ zakładki: tytuł + jedno zdanie kontekstu. */
function Sekcja({
  tytul,
  opis,
  children,
}: {
  tytul: string;
  opis: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h3 className="text-base font-bold tracking-tight">{tytul}</h3>
      <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-muted">
        {opis}
      </p>
      <div className="mt-4">{children}</div>
    </section>
  );
}

export default async function ModelPage() {
  const [kal, meta, typy] = await Promise.all([
    getKalibracja(),
    getMeta(),
    getTypyWyniki(),
  ]);
  const pods = typy.podsumowanie;
  const dni = typy.skutecznosc_dzienna ?? [];
  const zakladki: Zakladka[] = [];

  // --- TYPY: co model obiecywał i co z tego wyszło, rynek po rynku ---
  if (pods && pods.rozliczone > 0) {
    zakladki.push({
      id: "typy",
      label: "Typy",
      licznik: String(pods.rozliczone),
      panel: (
        <div className="space-y-8">
          <Sekcja
            tytul="Rynek po rynku"
            opis={
              <>
                Każdy publikowany typ trafia do logu z zamrożoną szansą
                i kursem, a po meczu system sam sprawdza wynik. Kolumny
                „mówił” i „było” obok siebie pokazują, gdzie model
                przeszacowuje — to jego najczęstszy błąd. Rynki z próbą
                poniżej {N_ISTOTNE} rozliczeń są wyszarzone: jeszcze nic nie
                znaczą.
              </>
            }
          >
            {typy.po_rynku.length > 0 && (
              <div className="max-w-3xl overflow-x-auto rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card)">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-hairline bg-card-soft text-left text-[11px] uppercase tracking-wide text-faint">
                      <th className="px-4 py-2.5 font-medium">rynek</th>
                      <th className="px-4 py-2.5 font-medium">trafione</th>
                      <th
                        className="px-4 py-2.5 font-medium"
                        title="Średnia szansa, jaką dawał model"
                      >
                        mówił
                      </th>
                      <th className="px-4 py-2.5 font-medium">było</th>
                      <th className="px-4 py-2.5 font-medium">różnica</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {[...typy.po_rynku]
                      // najgorsze przeszacowanie na górze, ale WYŁĄCZNIE wśród
                      // rynków z sensowną próbą — inaczej listę otwiera „0/1
                      // przy 70%", które nie mówi nic poza tym, że raz nie weszło
                      .sort((a, b) => {
                        const chude = (r: typeof a) => (r.n < N_ISTOTNE ? 1 : 0);
                        return (
                          chude(a) - chude(b) ||
                          a.czestosc - a.sr_p_model - (b.czestosc - b.sr_p_model)
                        );
                      })
                      .map((r) => {
                        const roznica = r.czestosc - r.sr_p_model;
                        const chudy = r.n < N_ISTOTNE;
                        return (
                          <tr
                            key={r.rynek_kod}
                            className={`even:bg-card-soft transition-colors hover:bg-brand-wash/40 ${
                              chudy ? "text-faint" : ""
                            }`}
                            title={
                              chudy
                                ? `Za mała próba (${r.n}) — liczby nic jeszcze nie znaczą`
                                : undefined
                            }
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
                            <td
                              className={`font-data px-4 py-2.5 font-semibold ${
                                chudy
                                  ? ""
                                  : roznica >= 0
                                    ? "text-data-green"
                                    : roznica < -0.1
                                      ? "text-data-red"
                                      : "text-data-amber-ink"
                              }`}
                              title="Trafienia minus deklaracja. Ujemna = model był zbyt pewny siebie."
                            >
                              {roznica >= 0 ? "+" : "−"}
                              {Math.abs(roznica * 100).toFixed(0)} pp
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            )}
          </Sekcja>

          {dni.length > 0 && (
            <Sekcja
              tytul="Trzy produkty, trzy osobne liczniki"
              opis={
                <>
                  Typ zawodniczy z silnika, rynek drużynowy i karta z Drabinek
                  mają inne źródło prawdopodobieństwa i inne ryzyko. Uśrednienie
                  ich w jedną liczbę nie odpowiadałoby na żadne pytanie, więc
                  każdy liczy się osobno.
                </>
              }
            >
              <SkutecznoscStrumienie
                strumienie={typy.skutecznosc_strumienie}
                fallbackDni={dni}
              />
            </Sekcja>
          )}
        </div>
      ),
    });
  }

  // --- KALENDARZ: bilans dnia po dniu, z podziałem na strumienie ---
  if (dni.length > 0) {
    zakladki.push({
      id: "kalendarz",
      label: "Kalendarz",
      licznik: `${dni.filter((d) => d.roi_flat > 0.005).length}/${dni.length}`,
      panel: (
        <Sekcja
          tytul="Dzień po dniu, bez retuszu"
          opis={
            <>
              Bilans realnych typów każdego dnia przy stawce 1 jednostki na typ.
              Przełącznik pokazuje, który produkt zrobił wynik — a wyblakłe dni
              są sprzed ostatniej zmiany zasad selekcji.
            </>
          }
        >
          <div className="max-w-3xl">
            <KalendarzWynikow
              dni={dni}
              strumienie={typy.skutecznosc_strumienie}
            />
          </div>
        </Sekcja>
      ),
    });
  }

  // --- KUPONY: ROI per horyzont + historia + kronika wygranych ---
  if ((typy.kupony?.length ?? 0) > 0 || (typy.kupony_wygrane?.length ?? 0) > 0) {
    zakladki.push({
      id: "kupony",
      label: "Kupony",
      licznik: typy.kupony_wygrane?.length
        ? `${typy.kupony_wygrane.length} wygranych`
        : undefined,
      panel: (
        <div className="space-y-8">
          <Sekcja
            tytul="Bilans kuponów"
            opis={
              <>
                Kupon zamraża się w chwili publikacji. Zmienia się tylko wtedy,
                gdy ogłoszone składy wywrócą któryś typ. Jedno pudło = kupon
                przegrany, a zwrot typu (zawodnik nie zagrał) wyłącza go
                z kursu, jak u bukmachera.
              </>
            }
          >
            {typy.kupony_roi && Object.keys(typy.kupony_roi).length > 0 && (
              <div className="max-w-4xl overflow-hidden rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card)">
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
                            {fmtU(d.roi_j)}
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
          </Sekcja>

          {(typy.kupony?.length ?? 0) > 0 && (
            <Sekcja
              tytul="Ostatnie kupony"
              opis="Dwanaście najświeższych, razem z tymi, które nie weszły."
            >
              {/* items-start: rozwinięcie jednego kuponu nie rozciąga sąsiada */}
              <div className="grid max-w-4xl items-start gap-3 sm:grid-cols-2">
                {typy.kupony!.slice(0, 12).map((k) => (
                  <KuponHistoriaCard
                    key={k.klucz ?? `${k.horyzont}-${k.cel_label}-${k.dzien}`}
                    k={k}
                    name="kupon-historia"
                  />
                ))}
              </div>
            </Sekcja>
          )}

          {(typy.kupony_wygrane?.length ?? 0) > 0 && (
            <Sekcja
              tytul={`Kronika trafień (${typy.kupony_wygrane!.length})`}
              opis="Każdy kupon, który się kiedykolwiek trafił, zostaje tu na stałe — niezależnie od tego, jak dawno temu i czy był grany."
            >
              <div className="grid max-w-4xl items-start gap-3 sm:grid-cols-2">
                {typy.kupony_wygrane!.map((k) => (
                  <KuponHistoriaCard
                    key={k.klucz ?? `${k.horyzont}-${k.cel_label}-${k.dzien}`}
                    k={k}
                    name="kupon-wygrany"
                  />
                ))}
              </div>
            </Sekcja>
          )}
        </div>
      ),
    });
  }

  // --- KALIBRACJA: backtest na meczach spoza nauki ---
  zakladki.push({
    id: "kalibracja",
    label: "Kalibracja",
    licznik: kal.razem ? String(kal.razem.n) : undefined,
    panel: (
      <div className="space-y-6">
        <Sekcja
          tytul="Test na meczach spoza nauki"
          opis={
            <>
              Model przewidywał zdarzenia w {meta.meczow_kalibracja} meczach,
              których <strong>nie widział podczas nauki</strong>. Punkt na
              przekątnej = idealna kalibracja (gdy mówi „60%", zdarzenie
              zachodzi w 60% przypadków). Wielkość punktu = liczba predykcji
              w kubełku.
              {meta.tryb === "ms2026" &&
                " Test przeprowadzono na Premier League — to ten sam rdzeń modelu, który liczy predykcje MŚ."}
            </>
          }
        >
          {kal.razem && (
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
          )}
        </Sekcja>

        {kal.rynki.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {kal.rynki.map((r) => (
              <div
                key={r.kod}
                className="rounded-(--radius-card) border border-hairline bg-card p-4 shadow-(--shadow-card) transition-shadow hover:shadow-(--shadow-card-hover)"
              >
                <div className="mb-1 flex items-baseline justify-between gap-3">
                  <h4 className="font-semibold">{r.nazwa}</h4>
                  <span className="font-data text-xs text-muted">
                    Brier {r.brier.toFixed(3).replace(".", ",")} · n={r.n}
                  </span>
                </div>
                <CalibrationChart bins={r.kubelki} size={240} />
              </div>
            ))}
          </div>
        ) : (
          <p className="rounded-(--radius-card) border border-hairline bg-card p-4 text-sm text-muted shadow-(--shadow-card)">
            Za mało danych do kalibracji. Uruchom dłuższy backfill w pipeline.
          </p>
        )}
      </div>
    ),
  });

  return (
    <div>
      <PageHeader
        eyebrow="kontrola jakości"
        title="Czy model mówi prawdę?"
        lead={
          <>
            Wszystkie liczby na tej stronie liczą się same, z rozliczeń realnych
            typów — nikt ich nie wybiera ręcznie i nic z nich nie znika. Zacznij
            od werdyktu, a jeśli chcesz sprawdzić, skąd się wziął, wejdź
            w zakładki niżej.
          </>
        }
      />

      <Reveal className="mt-7">
        <div className="max-w-3xl">
          <WerdyktModelu typy={typy} meta={meta} />
        </div>
      </Reveal>

      {pods && pods.rozliczone === 0 && (
        <p className="mt-6 max-w-3xl rounded-(--radius-card) border border-hairline bg-card px-4 py-3.5 text-sm text-muted shadow-(--shadow-card)">
          Log już zbiera publikowane typy ({pods.opublikowane}). Pierwsze
          rozliczenia pojawią się automatycznie po zakończeniu najbliższych
          meczów.
        </p>
      )}

      <Reveal className="mt-10">
        <SkutecznoscZakladki zakladki={zakladki} />
      </Reveal>
    </div>
  );
}
