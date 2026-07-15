import { Hero } from "@/components/Hero";
import { ValueBoard } from "@/components/ValueBoard";
import { getMeta, getValueBets, getZawodnicy } from "@/lib/data";

export default async function OkazjePage({
  searchParams,
}: {
  searchParams: Promise<{ mecz?: string; rodzaj?: string }>;
}) {
  const { mecz, rodzaj } = await searchParams;
  const [bets, zawodnicy, meta] = await Promise.all([
    getValueBets(),
    getZawodnicy(),
    getMeta(),
  ]);

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
        <p className="mb-6 inline-flex items-center gap-2 rounded-lg border border-data-amber/40 bg-data-amber-wash px-3 py-2 text-xs text-data-amber-ink">
          <span aria-hidden>ⓘ</span>
          Tryb pokazowy: statystyki zawodników są prawdziwe ({meta.liga}{" "}
          {meta.sezon}), ale kursy są przykładowe, bo trwa przerwa między
          sezonami.
        </p>
      ) : meta.tryb === "ms2026" ? (
        <p className="mb-6 inline-flex items-center gap-2 rounded-lg border border-hairline bg-card px-3 py-2 text-xs text-muted">
          <span aria-hidden>ⓘ</span>
          Dane na żywo · kursy Superbet. Okazji z kursem jest celowo mało:
          bezpieczniki modelu odrzucają typy, gdzie kurs nie daje realnej
          przewagi.
        </p>
      ) : null}

      <div id="okazje" className="scroll-mt-24">
      <ValueBoard
        key={rodzaj ?? "domyslny"}
        bets={bets}
        zawodnicy={zawodnicy}
        initialMatchId={mecz ? Number(mecz) : undefined}
        initialRodzaj={
          rodzaj === "okazje" ||
          rodzaj === "pewniaki" ||
          rodzaj === "sugestie" ||
          rodzaj === "wszystko"
            ? rodzaj
            : undefined
        }
      />
      </div>
    </>
  );
}
