import { BetCard } from "@/components/BetCard";
import { PageHeader } from "@/components/PageHeader";
import { Reveal } from "@/components/Reveal";
import { getMeta, getValueBets } from "@/lib/data";

export const metadata = { title: "Drużyny – FootStats" };

/**
 * STATYSTYKI DRUŻYNOWE — osobna funkcja produktu (nie ta sama lista co
 * propsy zawodników): typy na gole, rzuty rożne i kartki CAŁYCH drużyn.
 * Zakres celowo wąski: top 5 lig, Ekstraklasa i puchary europejskie
 * z kwalifikacjami — tylko rozgrywki, dla których model ma głębokie dane.
 */
export default async function DruzynyPage() {
  const [bets, meta] = await Promise.all([getValueBets(), getMeta()]);
  const typy = bets.filter((b) => b.podmiot_typ === "druzyna" && !b.sugestia);

  return (
    <div>
      <PageHeader
        eyebrow="statystyki drużynowe"
        title="Typy na całe drużyny"
        lead={
          <>
            Gole, rzuty rożne i kartki całych drużyn, nie pojedynczych
            zawodników. Model liczy je tylko dla rozgrywek, które zna od
            podszewki: pięć czołowych lig Europy, Ekstraklasa i puchary
            europejskie razem z kwalifikacjami.
          </>
        }
      />

      {typy.length === 0 ? (
        <Reveal className="mt-8">
          <div className="rounded-(--radius-card) border border-hairline bg-card px-8 py-14 text-center shadow-(--shadow-card)">
            <p className="font-semibold">Na razie brak typów drużynowych</p>
            <p className="mx-auto mt-1.5 max-w-md text-sm leading-relaxed text-muted">
              Typy pojawiają się, gdy zbliżają się mecze czołowych lig i
              pucharów, a kursy dają się sensownie ograć ({meta.liga}{" "}
              {meta.sezon}). Statystyki pojedynczych zawodników znajdziesz w
              zakładce Zawodnicy.
            </p>
          </div>
        </Reveal>
      ) : (
        <div className="mt-7 space-y-4">
          {typy.map((bet, i) => (
            <Reveal key={bet.id} delay={Math.min(i * 0.04, 0.4)}>
              <BetCard bet={bet} rank={i + 1} />
            </Reveal>
          ))}
        </div>
      )}
    </div>
  );
}
