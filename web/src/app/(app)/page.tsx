import { Hero } from "@/components/Hero";
import { KuponDniaTeaser } from "@/components/KuponDniaTeaser";
import { Reveal } from "@/components/Reveal";
import { SkutecznoscTeaser } from "@/components/SkutecznoscTeaser";
import { ValueBoard } from "@/components/ValueBoard";
import {
  getKuponDnia,
  getMeta,
  getStsValue,
  getTypyWyniki,
  getValueBets,
  getZawodnicy,
} from "@/lib/data";

export default async function OkazjePage({
  searchParams,
}: {
  searchParams: Promise<{ mecz?: string; rodzaj?: string }>;
}) {
  const { mecz, rodzaj } = await searchParams;
  const [wszystkieBets, zawodnicy, meta, stsValue, kuponDnia, typyWyniki] =
    await Promise.all([
      getValueBets(),
      getZawodnicy(),
      getMeta(),
      getStsValue(),
      getKuponDnia(),
      getTypyWyniki(),
    ]);
  const pods = typyWyniki.podsumowanie;

  // ta strona to STATYSTYKI ZAWODNIKÓW — typy drużynowe mają własną
  // podstronę /druzyny (osobna funkcja produktu, nie ta sama lista)
  const bets = wszystkieBets.filter((b) => b.podmiot_typ !== "druzyna");
  const druzynoweN = wszystkieBets.filter(
    (b) => b.podmiot_typ === "druzyna" && !b.sugestia,
  ).length;

  // ODCHUDZENIE payloadu: ValueBoard/BetCard czytają z zawodnika wyłącznie
  // forma[rynek_kod] typu — a pełna baza (każdy zawodnik × wszystkie rynki
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
  // żywy podgląd w hero: do 4 najlepszych pozycji rankingu silnika
  // (kolejność wejściowa = ranking), sugestie tylko gdy brak innych
  const spotlight = (okazje.length > 0 ? okazje : sugestie).slice(0, 4);
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
        tickerBets={bets.filter((b) => !b.sugestia).slice(0, 14)}
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
        zawodnicy={zawodnicyLite}
        initialMatchId={mecz ? Number(mecz) : undefined}
        initialRodzaj={
          rodzaj === "pewniaki" || rodzaj === "value" || rodzaj === "wszystko"
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

      {/* pod listą: obietnice hero z pokryciem — bilet kuponu dnia i bliźniacza
          karta trafień (ta sama anatomia); oba znikają same, gdy brak danych */}
      {(kuponDnia || (pods && pods.rozliczone > 0)) && (
        <section
          aria-label="Kupon dnia i skuteczność"
          className="mt-14 grid items-stretch gap-5 md:grid-cols-2"
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
        </section>
      )}
    </>
  );
}
