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
  /** true = top typ meczu z pełnego skanu (wysoka szansa, bez wymogu value) */
  pewniak?: boolean;
  /** true = perełka na wyższej linii (>= 1,5) przy wciąż solidnej szansie */
  wyzsza_linia?: boolean;
  /** true = profil rywala wyraźnie sprzyja (koncesje per rynek × pozycja) */
  matchup?: boolean;
  /** true = pierwszy występ w XI na turnieju — linie rynku bywają niedograne */
  rotacja?: boolean;
  /** true = składy potwierdzono <45 min temu — kurs mógł nie zdążyć zareagować */
  swieze_sklady?: boolean;
  /** true = linia płaci >=12% ponad kurs wynikający z RESZTY siatki Superbetu */
  miekka_linia?: boolean;
  /** kurs, jaki wynika z pozostałych linii buka (gdy miekka_linia) */
  kurs_oczekiwany?: number | null;
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
  /** rywal w każdym meczu (równolegle z ostatnie) */
  rywale?: string[];
  /** true = mecz reprezentacji (false/brak = klub) */
  kadra?: boolean[];
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

/** Jeden typ (leg) na kuponie. */
export interface KuponLeg {
  value_bet_id: number;
  podmiot: string;
  rynek: string;
  linia: number;
  strona: Strona;
  kurs: number;
  bukmacher: string;
  p_model: number;
  pewnosc: Pewnosc;
  mecz: string;
  mecz_id: number;
  kickoff_ts: number;
  /** wynik lega z logu rozliczeń (null/brak = jeszcze w grze) */
  wynik?: "wygrany" | "przegrany" | "zwrot" | null;
  /** kontekst lega: profil rywala / debiut w XI / niespójna siatka buka */
  matchup?: boolean;
  rotacja?: boolean;
  miekka_linia?: boolean;
}

/** Propozycja wymiany najsłabszego lega (rentgen kuponu — doradcza). */
export interface KuponAlternatywa extends KuponLeg {
  zamiast_idx: number;
  kurs_po: number;
  p_po: number;
}

/** Propozycja DOŁOŻENIA pewnego lega, gdy kurs wisi nisko w przedziale. */
export interface KuponDolozenie extends KuponLeg {
  kurs_po: number;
  p_po: number;
}

/** Kupon (AKO) budowany przez model pod docelowy kurs (x5/x10/x15/x20/x25). */
export interface Kupon {
  cel: number;
  /** np. "10–15" — przedział kursowy kuponu */
  cel_label?: string;
  /** dzienny = mecze z dziś/jutra; dlugoterminowy = najbliższe 4 dni */
  horyzont?: "dzienny" | "dlugoterminowy" | "value";
  /** pewniaki = maks. szansa przy zadanym kursie; value = tylko typy z przewagą */
  styl?: "pewniaki" | "value";
  kurs_laczny: number;
  p_model: number;
  fair_kurs: number;
  ev_pct: number;
  legi: KuponLeg[];
  /** indeks lega o najniższej szansie (najsłabsze ogniwo) */
  najslabszy_idx?: number;
  alternatywa?: KuponAlternatywa;
  dolozenie?: KuponDolozenie;
  /** ile meczów kuponu miało POTWIERDZONE składy w chwili budowy */
  mecze_ze_skladami?: number;
  mecze_lacznie?: number;
  /** alternatywny, wyraźnie inny zestaw z tej samej puli (podglądowy) */
  wariant_b?: Kupon;
  /** true = kupon powstał z wymiany lega (zastosowana alternatywa rentgena) */
  z_wymiany?: boolean;
  /** klucz rekordu w logu kuponów — identyfikator do pomijania */
  klucz?: string;
}

/** Rozliczony (lub czekający) typ z automatycznego logu. */
export interface TypRozliczony {
  mecz: string;
  kickoff_ts: number;
  podmiot: string;
  rynek_kod: string;
  rynek: string;
  linia: number;
  strona: Strona;
  kurs: number | null;
  p_model: number;
  sugestia: boolean;
  wynik: "wygrany" | "przegrany" | "zwrot" | null;
  faktyczna: number | null;
  /** ostatni kurs przed startem meczu (linia zamknięcia rynku) */
  kurs_zamkniecia?: number | null;
  /** CLV: o ile % kurs wzięty był lepszy od zamknięcia (dodatnie = bijemy rynek) */
  clv_pct?: number | null;
}

/** Kupon w historii: zamrożony przy publikacji, rozliczany z legów. */
export interface KuponHistoria extends Kupon {
  dzien: string;
  opublikowano_ts: number;
  /** "anulowany" = unieważniony przez zmianę ogłoszonych składów;
   *  "zwrot" = wszystkie legi zwrócone (stawka wraca, kurs 1.0) */
  wynik: "wygrany" | "przegrany" | "anulowany" | "zwrot" | null;
  powod?: string;
  slot?: string;
  klucz?: string;
  kurs_rozliczony?: number;
  legi_trafione?: number;
  legi_rozliczone?: number;
  /** true = user pominął kupon (nie zagrał) — rozliczony tylko do nauki */
  pominiety?: boolean;
  /** powód pominięcia (user) albo techniczny: wymiana lega / przebudowa */
  pomin_powod?: string | null;
}

/** Skuteczność jednego rynku (trafienia vs. średnia szansa modelu). */
export interface RynekSkutecznosc {
  rynek_kod: string;
  rynek: string;
  n: number;
  trafione: number;
  sr_p_model: number;
  czestosc: number;
  bias: number;
}

/** Skuteczność realnych typów jednego dnia (grupowane po dniu meczu). */
export interface SkutecznoscDnia {
  /** "YYYY-MM-DD" — dzień meczu */
  dzien: string;
  rozliczone: number;
  trafione: number;
  /** typy z realnym kursem (bez sugestii) — podstawa ROI */
  okazje: number;
  /** ROI flat: stawka 1 j. na okazję (zwrot − postawione) */
  roi_flat: number;
  /** realne typy tego dnia (co siadło / nie siadło) — trafione na górze */
  typy?: TypRozliczony[];
}

/** Skuteczność realnych typów (log rozliczany automatycznie po meczach). */
export interface TypyWyniki {
  podsumowanie: {
    opublikowane: number;
    rozliczone: number;
    trafione: number;
    roi_flat: number;
    okazje_rozliczone: number;
    /** średnie CLV rozliczonych typów (dodatnie = bierzemy kursy lepsze niż zamknięcie) */
    clv_sr_pct?: number | null;
    clv_n?: number;
  } | null;
  po_rynku: RynekSkutecznosc[];
  ostatnie: TypRozliczony[];
  /** skuteczność dzień po dniu (do przełącznika); najnowszy dzień pierwszy */
  skutecznosc_dzienna?: SkutecznoscDnia[];
  kupony?: KuponHistoria[];
  /** ROI kuponów per horyzont (stawka 1 j./kupon; bez pominiętych) */
  kupony_roi?: Record<
    string,
    { n: number; wygrane: number; zwrot_j: number; roi_j: number }
  >;
  /** WSZYSTKIE wygrane kupony (trwały log — nigdy nie znikają) */
  kupony_wygrane?: KuponHistoria[];
}

/**
 * Siatka kursów Superbet (strona „powyżej") do widoku TOP POKRYCIA:
 * mecz_id → player_id → rynek_kod → "linia" (np. "0.5") → kurs.
 * Klucze to stringi (JSON), bo mecz_id/player_id/linia serializują się jako tekst.
 */
export type OddsSuperbet = Record<
  string,
  Record<string, Record<string, Record<string, number>>>
>;

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
