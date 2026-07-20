import { DruzynyTablica } from "@/components/DruzynyTablica";
import { PageHeader } from "@/components/PageHeader";
import { Reveal } from "@/components/Reveal";
import { getDruzynyForma, getMecze, getMeta, getValueBets, terazTs } from "@/lib/data";

export const metadata = { title: "Drużyny – FootStats" };

/**
 * STATYSTYKI DRUŻYNOWE — osobna funkcja produktu (nie ta sama lista co
 * propsy zawodników): typy na gole, rzuty rożne i kartki CAŁYCH drużyn.
 * Zakres celowo wąski: top 5 lig, Ekstraklasa i puchary europejskie
 * z kwalifikacjami — tylko rozgrywki, dla których model ma głębokie dane.
 * Tablica jest projektowana pod pełny sezon (dziesiątki meczów dziennie):
 * najmocniejsze typy doby na górze, reszta dniami, filtry rynku i rozgrywek.
 */
export default async function DruzynyPage() {
  const [bets, forma, mecze, meta] = await Promise.all([
    getValueBets(),
    getDruzynyForma(),
    getMecze(),
    getMeta(),
  ]);
  const typy = bets.filter((b) => b.podmiot_typ === "druzyna" && !b.sugestia);
  const ligaByMecz = Object.fromEntries(mecze.map((m) => [m.id, m.liga]));

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
            europejskie razem z kwalifikacjami. Każdy typ ma na klik formę
            drużyny w tym rynku i czynniki, z których wzięła się liczba.
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
        <DruzynyTablica
          bets={typy}
          forma={forma}
          ligaByMecz={ligaByMecz}
          teraz={terazTs()}
        />
      )}
    </div>
  );
}
