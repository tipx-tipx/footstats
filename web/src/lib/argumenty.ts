/**
 * Argumenty typu „jak u typera" (pipeline `model/argumenty.py`, 18.10) – kody
 * i liczby sprzed meczu zamienione na krótkie zdania karty. Moduł bez danych:
 * importuje go komponent przeglądarki.
 */
export type ArgumentyTypu = {
  za: string[];
  przeciw: string[];
  dane?: {
    rywal_miejsce?: [number, number];
    druzyna_miejsce?: [number, number];
    h2h?: [number, number];
    forma?: [number, number];
    /** drużyny: udział meczów po stronie typu (0–1); zawodnicy: [weszło, z] */
    pokrycie?: number | [number, number];
    na_90?: number;
    karne?: number;
    wolne?: number;
  };
};

export type ArgumentTekst = { tekst: string; kier: "za" | "przeciw" };

/** 1 strzał, 2–4 strzały, 5+ strzałów (12–14 też „strzałów”) */
const strzaly = (n: number) => (n === 1 ? "strzał" : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? "strzały" : "strzałów");

/**
 * Miejsce w lidze liczy pipeline zawsze od NAJWIĘKSZEJ wartości (1 = najwięcej),
 * a zdanie mówi „dużo/mało” – kierunek wynika z kodu i strony typu.
 * Forma i pokrycie NIE mają tu zdania: karta pokazuje je w kratkach (podgląd 18.10:
 * model liczy pokrycie z innego okna niż historia na karcie – „10 z 10” obok „9/10”).
 */
function tekst(kod: string, d: NonNullable<ArgumentyTypu["dane"]>, ponizej: boolean): string | null {
  const m = (x?: [number, number]) => (x ? `: ${x[0]}. na ${x[1]} w lidze` : "");
  // rywal_top = rywal sprzyja typowi: przy „powyżej” pozwala na dużo, przy „poniżej” na mało
  const rywalDuzo = (kod === "rywal_top") !== ponizej;
  switch (kod) {
    case "rywal_top":
    case "rywal_slaby":
      return `Rywal pozwala na ${rywalDuzo ? "dużo" : "mało"}${m(d.rywal_miejsce)}`;
    case "h2h_wszystkie":
    case "h2h_wiekszosc":
    case "h2h_nie":
      return d.h2h ? `Z tym rywalem weszło ${d.h2h[0]} z ${d.h2h[1]}` : null;
    // „na 90” bez zdania: model ma na karcie własne „średnio X na 90 minut” z innego
    // okna (podgląd 18.10: 1,5 obok 1,9) – zostaje tylko w pomiarze
    case "rzadko_sklad":
      return "Rzadko w pierwszym składzie";
    case "druzyna_top":
      return `Drużyna notuje ${ponizej ? "mało" : "dużo"}${m(d.druzyna_miejsce)}`;
    case "slabsza_ponizej":
      return "Ostatnie 10 meczów: rywal z wyraźnie lepszym bilansem bramek";
    case "wykonawca_karnych":
      return d.karne ? `Wykonuje rzuty karne (${d.karne} w ostatnich meczach)` : "Wykonuje rzuty karne";
    case "wykonawca_wolnych":
      return d.wolne ? `Uderza z rzutów wolnych (${d.wolne} ${strzaly(d.wolne)} w ostatnich meczach)` : "Uderza z rzutów wolnych";
    default:
      return null;
  }
}

/** Zdania na kartę: najpierw za, potem przeciw; kody bez zdania pomijamy */
export function argumentyPoLudzku(a?: ArgumentyTypu | null, strona?: string): ArgumentTekst[] {
  if (!a) return [];
  const d = a.dane ?? {};
  const ponizej = strona === "ponizej";
  const out: ArgumentTekst[] = [];
  for (const [lista, kier] of [[a.za, "za"], [a.przeciw, "przeciw"]] as const) {
    for (const kod of lista ?? []) {
      const t = tekst(kod, d, ponizej);
      if (t) out.push({ tekst: t, kier });
    }
  }
  return out;
}
