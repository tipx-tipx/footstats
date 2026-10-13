import { powodPoLudzku, type Powod } from "../_dane/elementy";
import { OpisyTypow, type PorownanieOpisu } from "../_ui/OpisyTypow";
import { opisZakladu } from "@/lib/format";
import { pobierzSurowe } from "@/lib/nowe/surowe";

/*
 * Warsztat 11.10 – opisy pod typami: stary silnik obok modelu uczonego
 * (właściciel: „opisy przepisać dokładnie”). Typy z produkcji (Supabase),
 * oba opisy przez ten sam `powodPoLudzku`, który rysuje kartę typu.
 */
type Czynnik = { nazwa: string; opis: string; mnoznik: number | null };
type TypZOpisem = {
  id?: number;
  podmiot: string;
  podmiot_typ?: string;
  przeciwnik?: string;
  mecz?: string;
  rynek: string;
  rynek_kod?: string;
  strona: string;
  linia: number;
  kurs: number;
  p_model: number;
  zrodlo_p?: string;
  uzasadnienie?: { czynniki?: Czynnik[] };
  uzasadnienie_uczony?: { czynniki?: Czynnik[] };
};

const powody = (cz: Czynnik[] | undefined, rynek: string): Powod[] =>
  (cz ?? []).map((c) => powodPoLudzku(c, rynek)).filter((x): x is Powod => x !== null);

export default async function OpisyTypowPage() {
  const surowe = await pobierzSurowe();
  const typy = (surowe.typy ?? []) as unknown as TypZOpisem[];
  const lista: PorownanieOpisu[] = typy
    .filter((t) => t.zrodlo_p === "uczony")
    .map((t, i) => ({
      klucz: `${t.id ?? i}-${t.podmiot}-${t.rynek_kod}-${t.linia}-${t.strona}`,
      kto: t.podmiot,
      druzynowy: t.podmiot_typ === "druzyna",
      zaklad: opisZakladu(t as unknown as Parameters<typeof opisZakladu>[0]),
      kurs: t.kurs,
      szansa: t.p_model,
      stary: powody(t.uzasadnienie?.czynniki, t.rynek),
      nowy: powody(t.uzasadnienie_uczony?.czynniki, t.rynek),
      maNowy: Boolean(t.uzasadnienie_uczony?.czynniki?.length),
    }));
  return <OpisyTypow lista={lista} />;
}
