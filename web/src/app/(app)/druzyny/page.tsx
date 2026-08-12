import { CzegoNieTypujemy } from "@/components/CzegoNieTypujemy";
import { DruzynyTablica } from "@/components/DruzynyTablica";
import { PageHeader } from "@/components/PageHeader";
import { Reveal } from "@/components/Reveal";
import {
  getDruzynyForma,
  getMecze,
  getMeta,
  getOdrzucenia,
  getValueBets,
  terazTs,
} from "@/lib/data";

export const metadata = { title: "Drużyny – FootStats" };

/**
 * STATYSTYKI DRUŻYNOWE – osobna funkcja produktu (nie ta sama lista co
 * propsy zawodników): typy na gole, rzuty rożne i kartki CAŁYCH drużyn.
 * Zakres celowo wąski: top 5 lig, Ekstraklasa i puchary europejskie
 * z kwalifikacjami – tylko rozgrywki, dla których model ma głębokie dane.
 * Tablica jest projektowana pod pełny sezon (dziesiątki meczów dziennie):
 * najmocniejsze typy doby na górze, reszta dniami, filtry rynku i rozgrywek.
 */
export default async function DruzynyPage() {
  const [bets, forma, mecze, meta, odrzucenia] = await Promise.all([
    getValueBets(),
    getDruzynyForma(),
    getMecze(),
    getMeta(),
    getOdrzucenia(),
  ]);
  const typy = bets.filter((b) => b.podmiot_typ === "druzyna" && !b.sugestia);
  const ligaByMecz = Object.fromEntries(mecze.map((m) => [m.id, m.liga]));
  // TYLKO odrzucenia DRUŻYNOWE i tylko z meczów, które się jeszcze nie zaczęły
  // — sekcja ma tłumaczyć DZISIEJSZĄ listę, a nie archiwum. Rejestr trzyma
  // tysiące wpisów ze wszystkich meczów w bazie.
  const teraz = terazTs();
  const kickoffById = new Map(mecze.map((m) => [m.id, m.kickoff_ts]));
  const odrzuceniaDruzyn = odrzucenia.filter(
    (o) => o.podmiot_typ === "druzyna" && (kickoffById.get(o.mecz_id) ?? 0) > teraz,
  );

  return (
    <div>
      <PageHeader
        eyebrow="statystyki drużynowe"
        title="Typy na całe drużyny"
        // ZAKRES LIG ROZSZERZYLIŚMY 27.07, TEKST ZOSTAŁ ZE STAREJ EPOKI:
        // obiecywał top 5 Europy i puchary, a na liście stały Allsvenskan,
        // Liga Profesional i Superliga. To jedyny błąd tej strony, który
        // czytelnik wykrywa sam w trzy sekundy — i pierwszy dowód, że opis
        // nie zgadza się z produktem. Liczba rozgrywek zamiast wyliczanki:
        // nie zestarzeje się przy następnym rozszerzeniu, a chipy niżej i tak
        // pokazują konkretne ligi.
        lead={
          <>
            {/* „komplet historii" to nasz żargon — użytkownika interesuje, że
                liczymy tylko tam, gdzie mamy dość danych (2026-08-04) */}
            Gole, rożne i kartki <strong>drużyny</strong> – nie pojedynczych
            zawodników. Bierzemy 17 rozgrywek, w których mamy dość historii,
            żeby cokolwiek policzyć.
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
          teraz={teraz}
          meczeTs={mecze.map((m) => m.kickoff_ts)}
          listaDnia={meta.lista_dnia}
        />
      )}

      {/* CO MODEL ŚWIADOMIE ODRZUCIŁ — ta sama zasada co na stronie meczu
          (przegląd sprzedażowy 05.08). Lista mówiła tylko, co wystawiliśmy;
          bez tego „mało typów" czyta się jak słaby dzień, a nie jak działający
          próg. Sekcja jest zwinięta: to dowód na żądanie, nie treść główna. */}
      {odrzuceniaDruzyn.length > 0 && (
        <Reveal className="mt-10">
          <CzegoNieTypujemy odrzucenia={odrzuceniaDruzyn} />
        </Reveal>
      )}
    </div>
  );
}
