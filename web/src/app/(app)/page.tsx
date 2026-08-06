import { Hero } from "@/components/Hero";
import { KuponDniaTeaser } from "@/components/KuponDniaTeaser";
import { Reveal } from "@/components/Reveal";
import { SkutecznoscTeaser } from "@/components/SkutecznoscTeaser";
import { ValueBoard } from "@/components/ValueBoard";
import {
  getKuponDnia,
  getMeta,
  getRadar,
  getStsValue,
  getTypyWyniki,
  getValueBets,
  getZawodnicy,
  terazTs,
} from "@/lib/data";

export default async function OkazjePage({
  searchParams,
}: {
  searchParams: Promise<{ mecz?: string; rodzaj?: string }>;
}) {
  const { mecz, rodzaj } = await searchParams;
  const [
    wszystkieBets,
    zawodnicy,
    meta,
    stsValue,
    kuponDnia,
    typyWyniki,
    radar,
  ] = await Promise.all([
    getValueBets(),
    getZawodnicy(),
    getMeta(),
    getStsValue(),
    getKuponDnia(),
    getTypyWyniki(),
    getRadar(),
  ]);
  const pods = typyWyniki.podsumowanie;

  // ta strona to STATYSTYKI ZAWODNIKÓW – typy drużynowe mają własną
  // podstronę /druzyny (osobna funkcja produktu, nie ta sama lista)
  const bets = wszystkieBets.filter((b) => b.podmiot_typ !== "druzyna");
  const druzynowe = wszystkieBets.filter(
    (b) => b.podmiot_typ === "druzyna" && !b.sugestia,
  );
  const druzynoweN = druzynowe.length;

  // ODCHUDZENIE payloadu: ValueBoard/BetCard czytają z zawodnika wyłącznie
  // forma[rynek_kod] typu – a pełna baza (każdy zawodnik × wszystkie rynki
  // × 20 meczów historii) pompowała megabajty do HTML i strumienia RSC
  // i to była główna waga tej strony. Na klienta idzie tylko forma rynków,
  // na które faktycznie są typy.
  const rynkiZawodnika = new Map<number, Set<string>>();
  for (const b of bets) {
    const s = rynkiZawodnika.get(b.podmiot_id) ?? new Set<string>();
    s.add(b.rynek_kod);
    rynkiZawodnika.set(b.podmiot_id, s);
  }
  const zawodnicyLite = zawodnicy
    .filter((z) => rynkiZawodnika.has(z.id))
    .map((z) => ({
      ...z,
      forma: Object.fromEntries(
        Object.entries(z.forma).filter(([kod]) =>
          rynkiZawodnika.get(z.id)!.has(kod),
        ),
      ),
    }));

  const okazje = bets.filter((b) => !b.sugestia);
  const sugestie = bets.filter((b) => b.sugestia);
  // CO KUPUJĄCY DOSTAJE — pierwsza rzecz, o którą pyta ktoś, kto ma zapłacić,
  // a do 2026-08-04 nie było jej nigdzie na stronie. Liczby są FAKTEM z dziś,
  // nie obietnicą („dziś N typów"), więc jutro mogą być inne i to w porządku.
  //
  // ROZBITE NA ZAWODNICZE I DRUŻYNOWE, bo inaczej pasek kłóci się z guzikiem
  // obok: guzik prowadzi do listy NA TEJ stronie (tylko zawodnicy), więc przy
  // „20 typów dziś" i „zobacz 3 okazje" użytkownik nie wie, której liczbie
  // wierzyć. Rozbicie tłumaczy przy okazji strukturę produktu.
  const wszystkieTypy = wszystkieBets.filter((b) => !b.sugestia);
  const konkrety = {
    zawodnicze: okazje.length,
    druzynowe: druzynoweN,
    meczow: new Set(wszystkieTypy.map((b) => b.mecz_id)).size,
  };
  // żywy podgląd w hero: do 4 najlepszych pozycji rankingu silnika
  // (kolejność wejściowa = ranking), sugestie tylko gdy brak innych
  //
  // KARTA POKAZUJE CAŁY SKAN, GDY ZAWODNIKÓW JEST GARSTKA (2026-08-06).
  // Strumień zawodniczy bywa jednoelementowy — Superbet kwotuje propsy
  // praktycznie tylko w Ameryce Południowej. Karta karmiona wyłącznie nim
  // pokazywała wtedy JEDEN typ bez rotacji, a obok, na drugiej zakładce,
  // stało 19 typów drużynowych. Pierwsze wrażenie z produktu było więc
  // „pusto", mimo pełnej listy dwa kliknięcia dalej. Ten sam błąd co
  // w pasku skanu, naprawiony 04.08 — karta została wtedy pominięta.
  const spotlight = (
    okazje.length >= 3
      ? okazje
      : okazje.length + druzynowe.length > 0
        ? [...okazje, ...druzynowe]
        : sugestie
  ).slice(0, 4);
  // PASEK BIERZE CAŁY SKAN, NIE TYLKO TĘ PODSTRONĘ (2026-08-04). Karmiony
  // samymi typami zawodniczymi pokazywał tego dnia JEDEN typ powielony osiem
  // razy — pasek dopełnia się kopiami, żeby taśma nie miała dziur, a typ
  // zawodniczy był wtedy dokładnie jeden. W tym samym czasie mieliśmy 19 typów
  // drużynowych, których nie tykał. To ma być „skan rynków", nie lista tej
  // strony; klik i tak prowadzi tam, gdzie typ naprawdę jest (`hrefPozycji`).
  // NAJWYŻEJ DWA TAKIE SAME ZAKŁADY W PASKU (2026-08-06). Pasek brał
  // czternaście pierwszych pozycji rankingu, a ranking potrafi mieć na czele
  // pięć razy „gole poniżej 0,5" w różnych meczach — bo model widzi dziś
  // przewagę głównie tam. Pierwsze, co widział wchodzący, to wrażenie, że
  // umiemy jedną rzecz. To NIE jest zmiana reguł publikacji: te same typy,
  // inna kolejność w pasku dekoracyjnym.
  const tickerBets: typeof wszystkieBets = [];
  const ileTakich = new Map<string, number>();
  for (const b of wszystkieBets) {
    if (b.sugestia) continue;
    const klucz = `${b.rynek_kod}|${b.strona}`;
    const ile = ileTakich.get(klucz) ?? 0;
    if (ile >= 2) continue;
    ileTakich.set(klucz, ile + 1);
    tickerBets.push(b);
    if (tickerBets.length >= 14) break;
  }
  const aktualizacja = new Intl.DateTimeFormat("pl-PL", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  }).format(new Date(meta.wygenerowano_ts * 1000));

  return (
    <>
      <Hero
        liga={meta.liga}
        sezon={meta.sezon}
        aktualizacja={aktualizacja}
        liczbaOkazji={bets.filter((b) => !b.sugestia).length}
        spotlightBets={spotlight}
        tickerBets={tickerBets}
        konkrety={konkrety}
      />

      {meta.tryb === "demo" ? (
        <div className="mb-6 flex max-w-3xl flex-wrap items-baseline gap-x-3 gap-y-1.5">
          <span className="font-display flex shrink-0 items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-data-amber-ink">
            <span aria-hidden className="h-px w-5 bg-data-amber" />
            tryb pokazowy
          </span>
          <p className="text-xs leading-relaxed text-muted">
            Statystyki zawodników są prawdziwe ({meta.liga} {meta.sezon}), ale
            kursy są przykładowe, bo trwa przerwa między sezonami.
          </p>
        </div>
      ) : null}

      <div id="okazje" className="scroll-mt-24">
      <ValueBoard
        key={rodzaj ?? "domyslny"}
        bets={bets}
        stsAlerty={stsValue.alerty}
        stsGeneratedTs={stsValue.generated_ts}
        radarWpisy={radar.wpisy}
        kwarantanna={meta.kwarantanna}
        zawodnicy={zawodnicyLite}
        teraz={terazTs()}
        initialMatchId={mecz ? Number(mecz) : undefined}
        initialRodzaj={
          rodzaj === "pewniaki" ||
          rodzaj === "value" ||
          rodzaj === "radar" ||
          rodzaj === "wszystko"
            ? rodzaj
            : undefined
        }
      />
      </div>

      {/* most do statystyk drużynowych: banda-przypis, nie karta */}
      {druzynoweN > 0 && (
        <Reveal className="mt-8">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1.5 border-y border-hairline py-3.5">
            <p className="text-sm text-muted">
              Model ma dziś także{" "}
              <strong className="font-semibold text-ink">
                {druzynoweN}{" "}
                {druzynoweN === 1
                  ? "typ drużynowy"
                  : druzynoweN < 5
                    ? "typy drużynowe"
                    : "typów drużynowych"}
              </strong>{" "}
              (gole, rożne i kartki całych drużyn).
            </p>
            <a
              href="/druzyny"
              className="text-sm font-semibold text-brand transition-colors hover:text-brand-bright"
            >
              Zobacz drużyny →
            </a>
          </div>
        </Reveal>
      )}

      {/* pod listą: obietnice hero z pokryciem – bilet kuponu dnia i bliźniacza
          karta trafień (ta sama anatomia); oba znikają same, gdy brak danych */}
      {(kuponDnia || (pods && pods.rozliczone > 0)) && (
        /* ODDECH MIĘDZY SEKCJAMI (2026-08-06). Cała strona szła jednym
           ciągiem: hero, pasek, lista, most, kafelki — to samo tło, ta sama
           szerokość, ten sam odstęp. Oko nie miało gdzie odpocząć i strona
           czytała się jak jedna długa lista.
           Te dwa kafelki to inna rzecz niż typy wyżej (dowód, nie oferta),
           więc dostają własne tło na pełną szerokość okna. Kalkulacja
           `50% − 50vw` jest ta sama co przy aurorze w hero — sprawdzona, nie
           wypycha strony w bok na 390 px (`npm run audyt`). */
        <section
          aria-label="Kupon dnia i skuteczność"
          className="relative mt-14 py-12"
        >
          <div
            aria-hidden
            className="absolute inset-y-0 bg-card-soft"
            style={{ left: "calc(50% - 50vw)", right: "calc(50% - 50vw)" }}
          />
          {/* JEDEN KAFELEK NIE MA WISIEĆ W SIATCE NA DWA (06.08). Kupon dnia
              znika, gdy wszystkie mecze puli już się zaczęły — wtedy przy
              `md:grid-cols-2` zostawała karta wyników i pół ekranu pustki.
              Przy jednym kafelku siatka schodzi do jednej kolumny i wyśrodkowuje. */}
          <div
            className={`relative grid items-stretch gap-5 ${
              kuponDnia && pods && pods.rozliczone > 0
                ? "md:grid-cols-2"
                : "mx-auto max-w-xl"
            }`}
          >
            {kuponDnia && (
              <Reveal className="h-full">
                <KuponDniaTeaser kupon={kuponDnia} />
              </Reveal>
            )}
            {pods && pods.rozliczone > 0 && (
              <Reveal delay={0.08} className="h-full">
                <SkutecznoscTeaser
                  ostatnie={typyWyniki.ostatnie}
                  dni={typyWyniki.skutecznosc_dzienna ?? []}
                  trafione={pods.trafione}
                  rozliczone={pods.rozliczone}
                />
              </Reveal>
            )}
          </div>
        </section>
      )}
    </>
  );
}
