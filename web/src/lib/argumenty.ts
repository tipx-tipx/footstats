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
    /** sumy meczowe: średnie miejsce obu drużyn (notują + oddają), 1 = najwięcej */
    mecz_miejsce?: number;
  };
};

export type ArgumentTekst = { tekst: string; kier: "za" | "przeciw" };

/** Kto jest kim w zdaniu – nazwy jak w danych, bez odmiany (stąd „drużyna X”). */
export type KontekstArgumentu = { kto?: string; druzyna?: string; rywal?: string; rynekKod?: string };

/** 1 strzał, 2–4 strzały, 5+ strzałów (12–14 też „strzałów”) */
const strzaly = (n: number) => (n === 1 ? "strzał" : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? "strzały" : "strzałów");

/**
 * Statystyka rynku w dopełniaczu liczby mnogiej („dużo strzałów”) – po kodzie
 * rynku bez przedrostka drużyny/meczu („team_sot” → „sot”).
 */
const STAT_MN: Record<string, string> = {
  shots: "strzałów", sot: "celnych strzałów", shots_outside_box: "strzałów zza pola karnego",
  sot_outside_box: "celnych strzałów zza pola karnego", headed_shots: "strzałów głową",
  headed_sot: "celnych strzałów głową", fouls_committed: "fauli", fouls_won: "wywalczonych fauli",
  offsides: "spalonych", tackles: "odbiorów", corners: "rzutów rożnych", cards: "kartek",
  fouls: "fauli", goals: "goli",
};
export const statystykaMn = (rynekKod?: string) =>
  STAT_MN[(rynekKod ?? "").replace(/^(team_|match_|wiecej_)/, "")] ?? "tej statystyki";

/**
 * ⚑ NA KARCIE TYLKO TO, CO STOI ZA TYPEM (właściciel 26.10: „nic, co stoi przeciw
 * typowi, tylko i wyłącznie informacje, co stoi za… logicznie napisane, zgodnie
 * z prawdą, bez skrótów myślowych”). Argumenty przeciw dalej działają w wyborze
 * (weto w pipeline), ale karta ich nie pokazuje.
 *
 * Miejsce w lidze liczy pipeline zawsze od NAJWIĘKSZEJ wartości (1 = najwięcej),
 * a zdanie mówi „dużo/mało” – kierunek wynika ze strony typu.
 * Forma i pokrycie NIE mają tu zdania: karta pokazuje je w kratkach (podgląd 18.10:
 * model liczy pokrycie z innego okna niż historia na karcie – „10 z 10” obok „9/10”).
 */
function tekst(kod: string, d: NonNullable<ArgumentyTypu["dane"]>, ponizej: boolean, k: KontekstArgumentu): string | null {
  const miejsce = (x?: [number, number]) => (x ? ` – ${x[0]}. miejsce na ${x[1]} drużyn w lidze` : "");
  const ile = ponizej ? "mało" : "dużo";
  const stat = statystykaMn(k.rynekKod);
  const rywal = k.rywal ? `drużyną ${k.rywal}` : "tym rywalem";
  const kodRynku = (k.rynekKod ?? "").replace(/^(team_|match_|wiecej_)/, "");
  switch (kod) {
    case "rywal_top": {
      const kto = k.rywal ?? "Rywal";
      // faule wywalczone: liczy się, ile rywal SAM fauluje
      if (kodRynku === "fouls_won") return `${kto} fauluje ${ile}${miejsce(d.rywal_miejsce)}`;
      return `W meczach z ${rywal} przeciwnicy notują ${ile} ${stat}${miejsce(d.rywal_miejsce)}`;
    }
    case "h2h_wszystkie":
    case "h2h_wiekszosc":
      return d.h2h ? `Ta linia weszła w ${d.h2h[0]} z ${d.h2h[1]} ostatnich meczów z ${rywal}` : null;
    // „na 90” bez zdania: model ma na karcie własne „średnio X na 90 minut” z innego
    // okna (podgląd 18.10: 1,5 obok 1,9) – zostaje tylko w pomiarze
    case "druzyna_top":
      return `${k.druzyna ?? "Drużyna"} notuje ${ile} ${stat}${miejsce(d.druzyna_miejsce)}`;
    case "slabsza_ponizej":
      return k.rywal && k.druzyna
        ? `W ostatnich 10 meczach ${k.rywal} miał wyraźnie lepszy bilans bramek niż ${k.druzyna}`
        : "W ostatnich 10 meczach rywal miał wyraźnie lepszy bilans bramek";
    case "mecz_sprzyja":
      return `Obie drużyny w swoich meczach notują i pozwalają rywalom na ${ile} ${stat}`;
    case "wykonawca_karnych":
      return `${k.kto ?? "Zawodnik"} wykonuje rzuty karne` + (d.karne ? ` – ${d.karne} w ostatnich meczach` : "");
    case "wykonawca_wolnych":
      return `${k.kto ?? "Zawodnik"} uderza z rzutów wolnych` + (d.wolne ? ` – ${d.wolne} ${strzaly(d.wolne)} w ostatnich meczach` : "");
    default:
      return null;
  }
}

/** Zdania na kartę – wyłącznie argumenty za; kody bez zdania pomijamy */
export function argumentyPoLudzku(a?: ArgumentyTypu | null, strona?: string, k: KontekstArgumentu = {}): ArgumentTekst[] {
  if (!a) return [];
  const d = a.dane ?? {};
  const ponizej = strona === "ponizej";
  const out: ArgumentTekst[] = [];
  for (const kod of a.za ?? []) {
    const t = tekst(kod, d, ponizej, k);
    if (t) out.push({ tekst: t, kier: "za" });
  }
  return out;
}
