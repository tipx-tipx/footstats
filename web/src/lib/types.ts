/** Typy danych FootStats — odpowiadają JSON-om generowanym przez pipeline. */

export type Pewnosc = "wysoka" | "srednia" | "niska";
export type Ryzyko = "niskie" | "srednie" | "wysokie";
export type Strona = "powyzej" | "ponizej";

export interface CzynnikUzasadnienia {
  nazwa: string;
  opis: string;
  mnoznik: number | null;
}

export interface Uzasadnienie {
  czynniki: CzynnikUzasadnienia[];
  oczekiwana_liczba: number;
  rynek_rzadki: boolean;
}

export interface Czynniki {
  rywal: number;
  sedzia: number;
  dom_wyjazd: number;
  scenariusz_meczu: number;
  lacznie: number;
  opisy: Record<string, string>;
}

export interface ValueBet {
  id: number;
  mecz_id: number;
  mecz: string;
  kickoff_ts: number;
  podmiot_typ: "zawodnik" | "druzyna";
  podmiot_id: number;
  podmiot: string;
  druzyna: string;
  przeciwnik: string;
  rynek_kod: string;
  rynek: string;
  linia: number;
  strona: Strona;
  kurs: number | null;          // null dla sugestii (rynek STS — sprawdź ręcznie)
  bukmacher: string;
  /** mediana kursów bukmacherów UK (Bet365, WH...) dla tej linii — konsensus rynku */
  kurs_ref?: number | null;
  p_model: number;
  p_rynku: number | null;
  fair_kurs: number;
  edge_pp: number | null;
  ev_pct: number | null;
  pewnosc: Pewnosc;
  pewnosc_score: number;
  ryzyko: Ryzyko;
  rank_score: number;
  ci: [number, number] | [null, null];
  oczekiwane_minuty: number | null;
  lambda: number;
  rozklad: number[] | null;
  czynniki: Czynniki | Record<string, never>;
  uzasadnienie: Uzasadnienie;
  sugestia?: boolean;           // true = brak kursu, tylko podpowiedź modelu
}

export interface Mecz {
  id: number;
  liga: string;
  sezon: string;
  kolejka: number | null;
  kickoff_ts: number;
  gospodarz: string;
  gosc: string;
  sedzia: string | null;
  sedzia_mnoznik_fauli: number;
  okazje: number[];
  /** true = oficjalne XI ogłoszone (model przeliczony na pewnych składach) */
  sklady_ogloszone?: boolean;
}

export interface FormaRynku {
  ostatnie: number[];
  minuty: number[];
  srednia90: number;
}

export interface Zawodnik {
  id: number;
  nazwa: string;
  pozycja: string;
  druzyna: string;
  minuty_lacznie: number;
  forma: Record<string, FormaRynku>;
}

export interface KubelekKalibracji {
  p_pred: number;
  p_real: number;
  n: number;
}

export interface KalibracjaRynku {
  kod: string;
  nazwa: string;
  n: number;
  brier: number;
  kubelki: KubelekKalibracji[];
}

export interface Kalibracja {
  rynki: KalibracjaRynku[];
  razem: { n: number; brier: number } | null;
}

export interface Meta {
  wygenerowano_ts: number;
  tryb: string;
  liga: string;
  sezon: string;
  zrodlo: string;
  meczow_w_bazie: number;
  meczow_demo: number;
  meczow_kalibracja: number;
  okazji: number;
}

/** Zakład zapisany w trackerze (localStorage). */
export interface MojZaklad {
  id: string;
  value_bet_id: number | null;
  mecz: string;
  podmiot: string;
  rynek: string;
  linia: number;
  strona: Strona;
  kurs: number;
  bukmacher: string;
  stawka: number | null;
  dodano_ts: number;
  kurs_zamkniecia: number | null;
  wynik: "oczekuje" | "wygrany" | "przegrany" | "zwrot";
  p_model: number;
}
