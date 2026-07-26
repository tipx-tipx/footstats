import { CalibrationChart } from "@/components/CalibrationChart";
import { KuponHistoriaCard } from "@/components/KuponHistoriaCard";
import { PageHeader } from "@/components/PageHeader";
import { Reveal } from "@/components/Reveal";
import { SkutecznoscScena } from "@/components/SkutecznoscScena";
import { getKalibracja, getMeta, getTypyWyniki } from "@/lib/data";
import { fmtU } from "@/lib/format";

export const metadata = { title: "Skuteczność modelu – FootStats" };

/**
 * KONTROLA JAKOŚCI — przebudowa 2026-07-26.
 *
 * Strona miała siedem sekcji jedna pod drugą i dwa niezależne przełączniki
 * tego samego (produkt), plus dwie nawigacje po czasie. Teraz: werdykt,
 * jeden filtr produktu, krzywa wyniku, a dowody w zakładkach. Serwer robi
 * to, co statyczne (kupony, test kalibracji), scena kliencka trzyma stan.
 */

/** Nagłówek sekcji WEWNĄTRZ panelu: tytuł + jedno zdanie kontekstu. */
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

  // --- KUPONY: bilans per horyzont + historia + kronika wygranych ---
  const kuponyPanel =
    (typy.kupony?.length ?? 0) > 0 || (typy.kupony_wygrane?.length ?? 0) > 0 ? (
      <div className="space-y-8">
        <Sekcja
          tytul="Bilans kuponów"
          opis={
            <>
              Kupon zamraża się w chwili publikacji. Zmienia się tylko wtedy,
              gdy ogłoszone składy wywrócą któryś typ. Jedno pudło = kupon
              przegrany, a zwrot typu (zawodnik nie zagrał) wyłącza go z kursu,
              jak u bukmachera.
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
                        wygrane {d.wygrane}/{d.n} · z {d.n}u wróciło{" "}
                        {d.zwrot_j.toFixed(2).replace(".", ",")}u
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
    ) : (
      <p className="max-w-3xl rounded-(--radius-card) border border-hairline bg-card px-4 py-3.5 text-sm text-muted shadow-(--shadow-card)">
        Żaden kupon nie doczekał się jeszcze rozliczenia.
      </p>
    );

  // --- TEST LABORATORYJNY: backtest na meczach spoza nauki ---
  // Nazwa nie jest ozdobna: to INNE dane niż wszystko powyżej (tysiące
  // predykcji z backtestu, nie realne zakłady), a licznik obok „331 typów"
  // sugerował, że mowa o tej samej próbie.
  const testPanel = (
    <div className="max-w-4xl space-y-6">
      <Sekcja
        tytul="Test na meczach spoza nauki"
        opis={
          <>
            To NIE są realne zakłady, tylko sprawdzian silnika: model
            przewidywał zdarzenia w {meta.meczow_kalibracja} meczach, których{" "}
            <strong>nie widział podczas nauki</strong>. Punkt na przekątnej =
            idealna kalibracja (gdy mówi „60%”, zdarzenie zachodzi w 60%
            przypadków). Wielkość punktu = liczba predykcji w kubełku.
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
  );

  return (
    <div>
      <PageHeader
        eyebrow="kontrola jakości"
        title="Czy model mówi prawdę?"
        lead={
          <>
            Wszystkie liczby na tej stronie liczą się same, z rozliczeń realnych
            typów — nikt ich nie wybiera ręcznie i nic z nich nie znika. Zacznij
            od werdyktu, a jeśli chcesz sprawdzić, skąd się wziął, schodź niżej.
          </>
        }
      />

      {pods && pods.rozliczone === 0 ? (
        <p className="mt-7 max-w-3xl rounded-(--radius-card) border border-hairline bg-card px-4 py-3.5 text-sm text-muted shadow-(--shadow-card)">
          Log już zbiera publikowane typy ({pods.opublikowane}). Pierwsze
          rozliczenia pojawią się automatycznie po zakończeniu najbliższych
          meczów.
        </p>
      ) : (
        <Reveal className="mt-7">
          <SkutecznoscScena
            typy={typy}
            meta={meta}
            kuponyPanel={kuponyPanel}
            testPanel={testPanel}
          />
        </Reveal>
      )}
    </div>
  );
}
