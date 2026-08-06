import { CalibrationChart } from "@/components/CalibrationChart";
import { KuponHistoriaCard } from "@/components/KuponHistoriaCard";
import { PageHeader } from "@/components/PageHeader";
import { PrzelacznikWidoku } from "@/components/PrzelacznikWidoku";
import { Reveal } from "@/components/Reveal";
import { SkutecznoscScena } from "@/components/SkutecznoscScena";
import { getKalibracja, getMeta, getTypyWyniki } from "@/lib/data";
import { okrojDlaKlienta } from "@/lib/okrojDlaKlienta";
import { fmtU } from "@/lib/format";
import { czyPelnyWglad, czytajRole } from "@/lib/rola";

export const metadata = { title: "Skuteczność modelu – FootStats" };

/**
 * KONTROLA JAKOŚCI – przebudowa 2026-07-26.
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

export default async function ModelPage({
  searchParams,
}: {
  searchParams: Promise<{ widok?: string }>;
}) {
  const [kal, meta, typySurowe, rola, params] = await Promise.all([
    getKalibracja(),
    getMeta(),
    getTypyWyniki(),
    czytajRole(),
    searchParams,
  ]);
  // admin może podejrzeć własny produkt oczami klienta (?widok=klient)
  const podglad = params.widok === "klient";
  const pelnyWglad = czyPelnyWglad(rola, podglad);
  // UKRYCIE W INTERFEJSIE TO ZA MAŁO: scena jest komponentem klienckim, więc
  // wszystko, co dostanie w propsach, ląduje w źródle strony – nawet jeśli
  // nic tego nie renderuje. Kuchnię modelu wycinamy z DANYCH, nie z widoku.
  const typy = pelnyWglad ? typySurowe : okrojDlaKlienta(typySurowe);
  // TO SAMO DOTYCZY `meta`: stan warstw uczenia to czysta kuchnia (nazwy
  // warstw, treść wyjątków, rozmiary prób). Scena dostaje `meta` w propsach
  // niezależnie od roli, więc wycinamy tutaj, a nie w widoku.
  const metaWidok = pelnyWglad ? meta : { ...meta, uczenie_stan: undefined };
  const pods = typy.podsumowanie;

  // --- KUPONY: bilans per horyzont + historia + kronika wygranych ---
  // (zakładka wyłącznie dla admina – klientowi nie budujemy jej wcale, bo
  //  React i tak wysłałby ją do przeglądarki jako props sceny)
  const kuponyPanel = !pelnyWglad ? null :
    (typy.kupony?.length ?? 0) > 0 || (typy.kupony_wygrane?.length ?? 0) > 0 ? (
      <div className="space-y-8">
        <Sekcja
          tytul="Bilans kuponów"
          opis={
            <>
              Kupon zapisujemy w chwili, gdy pojawia się na stronie, i już go nie
              zmieniamy – chyba że ogłoszone składy wywrócą któryś typ. Jeden
              nietrafiony typ przekreśla cały kupon, a typ, który poszedł na
              zwrot (bo zawodnik nie zagrał), wypada z kursu – dokładnie tak,
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
                        kupony {label} · rozliczone {d.n}
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
                        weszły {d.wygrane} z {d.n} · z {d.n} stawek wróciło{" "}
                        {d.zwrot_j.toFixed(2).replace(".", ",")}
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
            opis="Dwanaście ostatnich, razem z tymi, które nie weszły."
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
            opis="Każdy kupon, który kiedykolwiek wszedł, zostaje tu na stałe – niezależnie od tego, jak dawno temu i czy akurat go zagrałeś."
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
        Żaden kupon się jeszcze nie zakończył.
      </p>
    );

  // --- TEST NA MECZACH SPOZA NAUKI ---
  // To INNE dane niż wszystko powyżej (tysiące prognoz ze sprawdzianu, a nie
  // realne zakłady), a licznik obok „331 typów" sugerował tę samą próbę.
  const testPanel = !pelnyWglad ? null : (
    <div className="max-w-4xl space-y-6">
      <Sekcja
        tytul="Test na meczach spoza nauki"
        opis={
          <>
            To nie są realne zakłady, tylko egzamin dla modelu: kazaliśmy mu
            typować {meta.meczow_kalibracja} meczów, których{" "}
            <strong>nie widział, gdy się uczył</strong>. Chodzi o jedno – czy
            model mówi prawdę o własnej pewności. Jeśli obiecuje „60%”, to
            takie zdarzenia powinny zachodzić mniej więcej w 6 przypadkach na
            10. Na wykresie idealnie uczciwy model układa się wzdłuż przekątnej;
            im większa kropka, tym więcej prognoz się na nią złożyło.
            {meta.tryb === "ms2026" &&
              " Egzamin zdawał na Premier League – to ten sam silnik, który liczy typy na MŚ."}
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
                    sprawdzonych prognoz
                  </dt>
                </div>
                <div
                  className="ml-6 min-w-0 border-l border-hairline-strong/60 pl-6"
                  title="Standardowa miara celności prognoz (wynik Briera): średni kwadrat pomyłki. 0 to ideał, 0,25 to rzut monetą."
                >
                  <dd className="font-data text-3xl font-semibold leading-none text-data-green">
                    {kal.razem.brier.toFixed(3).replace(".", ",")}
                  </dd>
                  <dt className="mt-1.5 text-[11px] leading-tight text-faint">
                    celność prognoz ⓘ
                  </dt>
                </div>
              </dl>
              <p className="text-xs leading-relaxed text-muted sm:ml-6 sm:max-w-56 sm:border-l sm:border-hairline-strong/60 sm:pl-6">
                0 znaczy „jasnowidz”, 0,25 znaczy „rzut monetą”. Poniżej 0,20
                model naprawdę odróżnia to, co prawdopodobne, od reszty.
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
                <span
                  className="font-data text-xs text-muted"
                  title="Celność prognoz na tym rynku (0 = ideał, 0,25 = rzut monetą) i liczba sprawdzonych prognoz"
                >
                  celność {r.brier.toFixed(3).replace(".", ",")} · {r.n} prognoz
                </span>
              </div>
              <CalibrationChart bins={r.kubelki} size={240} />
            </div>
          ))}
        </div>
      ) : (
        <p className="rounded-(--radius-card) border border-hairline bg-card p-4 text-sm text-muted shadow-(--shadow-card)">
          Za mało danych, żeby zrobić ten sprawdzian. Potrzeba więcej
          rozegranych meczów.
        </p>
      )}
    </div>
  );

  return (
    <div>
      <PageHeader
        eyebrow={pelnyWglad ? "kontrola jakości" : "wyniki"}
        title={pelnyWglad ? "Czy model mówi prawdę?" : "Co z tego wyszło"}
        lead={
          pelnyWglad ? (
            <>
              <strong className="font-semibold text-ink">
                Każdy typ, który kiedykolwiek pokazaliśmy, trafia tu sam – razem
                z tymi, które nie weszły.
              </strong>{" "}
              Nic nie da się stąd usunąć ani dopisać ręcznie: liczby liczą się
              z rozliczeń meczów. Zacznij od werdyktu na górze, a jeśli chcesz
              sprawdzić, skąd się wziął, schodź niżej.
            </>
          ) : (
            <>
              <strong className="font-semibold text-ink">
                Wszystkie nasze typy, dzień po dniu – te, które weszły, i te,
                które nie.
              </strong>{" "}
              Wyniki dopisują się same po ostatnim gwizdku. Kliknij dowolny
              dzień w kalendarzu, żeby zobaczyć, co wtedy typowaliśmy i po
              jakim kursie.
            </>
          )
        }
      />

      {pods && pods.rozliczone === 0 ? (
        <p className="mt-7 max-w-3xl rounded-(--radius-card) border border-hairline bg-card px-4 py-3.5 text-sm text-muted shadow-(--shadow-card)">
          Mamy już zapisane {pods.opublikowane} pokazanych typów. Pierwsze
          wyniki pojawią się tu same, gdy skończą się najbliższe mecze.
        </p>
      ) : (
        <Reveal className="mt-7">
          <SkutecznoscScena
            typy={typy}
            meta={metaWidok}
            kuponyPanel={kuponyPanel}
            testPanel={testPanel}
            pelnyWglad={pelnyWglad}
            przelacznikWidoku={
              rola === "admin" ? (
                <PrzelacznikWidoku podglad={podglad} />
              ) : undefined
            }
          />
        </Reveal>
      )}
    </div>
  );
}
