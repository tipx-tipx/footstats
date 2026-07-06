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
  const naj = okazje.find((b) => b.ev_pct != null);
  const wysokaPewnosc = okazje.filter((b) => b.pewnosc === "wysoka").length;
  const topBet = naj ?? sugestie[0] ?? null;
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
        okazje={okazje.length}
        wysokaPewnosc={wysokaPewnosc}
        najlepszaEv={naj?.ev_pct ?? null}
        mecze={meta.meczow_demo}
        topBet={topBet}
        liczbaSugestii={sugestie.length}
      />

      {meta.tryb === "demo" && (
        <p className="mb-6 inline-flex items-center gap-2 rounded-lg border border-data-amber/40 bg-data-amber-wash px-3 py-2 text-xs text-[#8a5613]">
          <span aria-hidden>ⓘ</span>
          Tryb pokazowy: statystyki zawodników są prawdziwe ({meta.liga}{" "}
          {meta.sezon}), ale kursy są przykładowe — trwa przerwa między
          sezonami.
        </p>
      )}

      <ValueBoard
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
    </>
  );
}
