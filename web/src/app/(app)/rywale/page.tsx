import { PageHeader } from "@/components/PageHeader";
import { Reveal } from "@/components/Reveal";
import { RywaleTablica } from "@/components/RywaleTablica";
import { getRywale, getValueBets } from "@/lib/data";

export const metadata = { title: "Rywale – FootStats" };

/**
 * RYWALE – szukanie od rywala do zawodnika (2026-09-14). Eksperci zaczynają
 * od „kto dopuszcza najwięcej", my do tej pory tylko od zawodnika. Ekran
 * pokazuje koncesje rywali w meczach z najbliższych trzech dni, per formacja,
 * i ile naszych typów już przeciwko nim stoi. Liczby są te same, które
 * model ma w rachunku (cecha `rywal`), więc ekran i karta mówią jedno.
 */
export default async function RywalePage() {
  const [rywale, bets] = await Promise.all([getRywale(), getValueBets()]);
  return (
    <div>
      <PageHeader
        eyebrow="profil rywala"
        title="Kto dopuszcza najwięcej"
        lead={
          <>
            Zanim spojrzysz na zawodnika, spójrz na jego <strong>rywala</strong>:
            ile fauli, strzałów czy odbiorów dopuszczał zawodnikom danej
            formacji w 10 ostatnich meczach względem przeciętnej drużyny.
            Mecze z najbliższych trzech dni. To ta sama liczba, którą model
            wlicza w szansę każdego typu zawodniczego.
          </>
        }
      />
      <Reveal>
        <RywaleTablica rywale={rywale} typy={bets} />
      </Reveal>
    </div>
  );
}
