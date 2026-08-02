/** Typy danych FootStats – odpowiadają JSON-om generowanym przez pipeline. */

export type Pewnosc = "wysoka" | "srednia" | "niska";
export type Ryzyko = "niskie" | "srednie" | "wysokie";
/**
 * Strona zakładu. Do 2026-07-30 były dwie i cała strona to zakładała.
 *
 * Rynek „kto więcej" (`wiecej_*`) nie ma linii ani kierunku — jego `strona`
 * mówi, KTÓRA DRUŻYNA ma mieć więcej. Typ nie wiedział o tym przez trzy dni,
 * więc kompilator nie miał jak ostrzec, że `STRONA_LABEL[strona]` zwróci
 * `undefined`, a użytkownik zobaczy je dosłownie. Zdania buduje `opisZakladu`;
 * tu chodzi o to, żeby TypeScript znów mówił prawdę o danych.
 */
export type Strona = "powyzej" | "ponizej" | "gospodarz" | "gosc";

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
  kurs: number | null;          // null dla sugestii (rynek STS – sprawdź ręcznie)
  bukmacher: string;
  /** mediana kursów bukmacherów UK (Bet365, WH...) dla tej linii – konsensus rynku */
  kurs_ref?: number | null;
  /** uczciwy kurs UK po zdjęciu marży (no-vig) – benchmark „prawdziwej" ceny */
  kurs_novig?: number | null;
  /** wartość kursu Superbetu względem no-vig UK, w % (dodatnia = miękka linia) */
  ev_uk?: number | null;
  /**
   * Szansa POKAZYWANA – po urealnieniu na rozliczeniach, gdy jest z czego
   * (patrz `p_urealnione`). Liczby pochodne niżej są przeliczone z tej samej
   * wartości, więc karta nie może sama sobie zaprzeczyć. W księdze typów
   * pipeline trzyma wersję surową; ta jest wyłącznie do czytania.
   */
  p_model: number;
  /** true = powyższa szansa jest już ściągnięta o to, o ile taki strumień
   *  typów rozmijał się z rzeczywistością w ostatnich rozliczeniach */
  p_urealnione?: boolean;
  p_rynku: number | null;
  fair_kurs: number;
  edge_pp: number | null;
  /** BRUTTO – tą liczbą decydują bramy publikacji (patrz betting.ev_brutto_pct) */
  ev_pct: number | null;
  /** PO PODATKU od stawki – TO pokazujemy użytkownikowi (betting.ev_pct).
   *  Brak pola = rekord sprzed 2026-07-31; wtedy front liczy netto sam. */
  ev_netto?: number | null;
  /** „standard" (12% od stawki) | „bez_podatku" | „zwrot" – zapisany przy
   *  typie, żeby zmiana domyślnego trybu nie unieważniła historii */
  tryb_podatku?: string;
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
  /** true = wraca do XI po dłuższej przerwie – linie rynku bywają niedograne */
  rotacja?: boolean;
  /** true = składy potwierdzono <45 min temu – kurs mógł nie zdążyć zareagować */
  swieze_sklady?: boolean;
  /** true = linia płaci >=12% ponad kurs wynikający z RESZTY siatki Superbetu */
  miekka_linia?: boolean;
  /** true = typ z WCZEŚNIEJSZEGO cyklu, wznowiony z rejestru publikacji:
   *  bieżące przeliczenie go nie odtworzyło (zwykle feed zamilkł albo kurs
   *  wyszedł z widełek), ale został opublikowany i normalnie się rozliczy.
   *  Kurs jest ZAMROŻONY z chwili publikacji. */
  wznowiony?: boolean;
  /** true = typ odtworzony z KSIĘGI ROZLICZEŃ (drugie źródło siatki), a nie
   *  z rejestru publikacji: księga zna sam typ, kurs i szansę z chwili
   *  publikacji, więc karta jedzie bez rentgenu (czynniki, przedział,
   *  rozkład, historia). Zawsze razem z `wznowiony`. */
  uproszczony?: boolean;
  /** znacznik pierwszej publikacji typu (z rejestru, nie z bieżącego cyklu) */
  opublikowano_ts?: number;
  /** kurs, jaki wynika z pozostałych linii buka (gdy miekka_linia) */
  kurs_oczekiwany?: number | null;
}

/**
 * Value bet STS: selekcja „powyżej", gdzie STS przepłaca vs Superbet, a model
 * potwierdza. Generowane on-demand (jobs/sts_value.py) z domowego IP i wpychane
 * do Supabase (klucz sts_value). Osobny kształt niż ValueBet – STS to porównanie
 * dwóch kursów + strona modelu, nie pełny rentgen predykcji.
 */
export interface StsAlert {
  mecz: string;
  mecz_ts: number | null;
  /** znormalizowany klucz zawodnika (parowanie STS↔Superbet↔model) */
  zawodnik: string;
  /** ładna nazwa z modelu (legi_pool.podmiot); brak = pokaż klucz */
  zawodnik_nazwa?: string | null;
  rynek_kod: string;
  rynek: string;
  linia: number;
  /** „przynajmniej N" (STS: „N lub więcej") */
  linia_opis: string;
  /** rynek rozliczany z dogrywką (STS wystawia część rynków tylko tak) */
  z_dogrywka: boolean;
  /** SuperZmiana: przy zejściu zawodnika zakład przechodzi na zmiennika */
  superzmiana: boolean;
  kurs_sts: number;
  kurs_superbet: number;
  /** kurs_sts / kurs_superbet */
  ratio: number;
  /** iloraz ponad medianę różnicy STS/Superbet tego meczu (odjęte tło luźności) */
  nadwyzka_vs_baseline: number;
  /** szansa „fair" z devigu kursu Superbetu (dolne, ostrożne oszacowanie) */
  p_fair_superbet: number;
  /** EV wzięcia kursu STS liczone z fair Superbetu, w % */
  ev_pct: number;
  /** kurs „fair" z samospójności siatki Superbetu (kontrolna referencja) */
  fair_kurs_siatka: number | null;
  /** 0–3 niezależne potwierdzenia cross-book (siatka, baseline, drabinka) */
  sygnaly: number;
  pewnosc: Pewnosc;
  /** szansa modelu FootStats na tę selekcję (z legi_pool); null = poza modelem */
  p_model?: number | null;
  /** EV wg NIEZALEŻNEJ wyceny modelu: p_model * kurs_STS - 1, w % */
  ev_model_pct?: number | null;
  /** true = model ma zdanie o tej selekcji */
  ma_model?: boolean;
  /** true = pełny value bet STS: model + cross-book (EV modelu > 0, bez weta) */
  value_potwierdzony?: boolean;
  /** true = model odrzucił tę parę (zawodnik, rynek) – weto „potwierdzenia" */
  model_odrzucil?: boolean;
  /** powód odrzucenia po ludzku (gdy model_odrzucil) */
  odrzucenie_powod?: string | null;
  oczekiwane_minuty?: number | null;
  druzyna?: string | null;
}

/** Payload klucza `sts_value` w Supabase (snapshot z ostatniego klika użytkownika). */
export interface StsValue {
  generated_ts: number;
  n_meczow: number;
  n_alertow: number;
  n_potwierdzonych: number;
  alerty: StsAlert[];
}

/** Jeden szczebel drabinki kursów Superbetu na karcie radaru. */
export interface RadarSzczebel {
  linia: number;
  kurs: number;
  /** szansa modelu na „powyżej" tej linii; null = model nie liczył */
  p_model: number | null;
  /** ile z ostatnich występów przebiło tę linię ("trafione 8/10") */
  pokrycie?: { traf: number; z: number } | null;
  /** pokrycie po korekcie na krótką próbę (dolna granica Wilsona) */
  p_bazowe?: number | null;
  /** ile kontekst tego meczu zmienia szansę (1.0 = nic nie zmienia) */
  korekta?: number | null;
  /** szansa po kontekście – TA liczba decyduje o wyborze i kolejności kart */
  p_final?: number | null;
  /** p_final ścięte, bo model widział tę linię ciemniej niż pokrycie */
  strzyzenie_modelu?: boolean;
  /** cena tej samej linii u drugiego bukmachera (Betclic), gdy ją mamy */
  kurs_betclic?: number | null;
  rozjazd?: RadarRozjazd | null;
}

/** Rozjazd dwóch cenników na jednej linii (backend: betclic.rozjazd). */
export interface RadarRozjazd {
  superbet: number;
  betclic: number;
  /** wyższa z dwóch cen – tam się gra */
  lepszy: number;
  gdzie: "superbet" | "betclic";
  /** o ile procent lepsza cena bije gorszą */
  przewaga_pct: number;
  /** szansa wynikająca z TAŃSZEJ ceny (ostrożniejsza ocena rynku) */
  p_rynku: number;
  /** „pewniak_taniej" = jeden mówi „to niemal pewne", drugi płaci sensownie */
  typ: "pewniak_taniej" | "zwykly";
}

/** Jeden czynnik wodospadu kontekstu (rywal, sędzia, scenariusz, ...). */
export interface RadarCzynnik {
  zrodlo?: string;
  mnoznik?: number;
  /** ile rywal średnio dopuszcza na tym rynku / profil sędziego */
  srednia?: number;
  norma?: number;
  rank?: number | null;
  z?: number | null;
  mecze?: number;
  sedzia?: string;
  dom?: boolean;
  faworyt?: boolean;
  spread?: number;
  total?: number | null;
  sezon90?: number;
  okno90?: number;
  rynek_zrodlowy?: string;
}

/** Wodospad kontekstu meczu dla jednego rynku (jobs/radar.py). */
export interface RadarKontekst {
  rywal?: RadarCzynnik;
  sedzia?: RadarCzynnik;
  scenariusz?: RadarCzynnik;
  dom?: RadarCzynnik;
  sezony?: RadarCzynnik;
  /** iloczyn czynników po capie – tyle łącznie robi kontekst z lambdą */
  lacznie?: number;
}

/** Rynek na karcie radaru: drabinka + ostatnie występy (gdy mamy historię). */
export interface RadarRynek {
  rynek_kod: string;
  rynek: string;
  drabinka: RadarSzczebel[];
  /** liczniki z ostatnich rozegranych meczów (najnowszy pierwszy) */
  ostatnie?: number[];
  minuty?: number[];
  rywale?: string[];
  srednia90?: number;
  /** forma okno-vs-baza: śr./90 z 6 ostatnich vs wcześniejszych meczów */
  forma?: { okno90: number; baza90: number } | null;
  /** kontekst rywala: ile śr. oddaje na tym rynku i miejsce na tle ligi */
  rywal?: {
    srednia?: number | null;
    rank?: number | null;
    z?: number | null;
    liga?: number | null;
  } | null;
  /** pełny wodospad kontekstu meczu użyty do policzenia p_final */
  kontekst?: RadarKontekst | null;
}

/** Średnie CAŁEGO sezonu gracza (cache workera Sofascore, per liga+rok). */
export interface RadarSezon {
  turniej: string;
  rok: string;
  mecze: number;
  minuty: number;
  /** rynek_kod -> średnia na mecz (np. shots: 2.0) */
  na_mecz: Record<string, number>;
  /** rynek_kod -> średnia na 90 minut */
  na90: Record<string, number>;
}

/**
 * Wpis radaru okazji kontekstowych (jobs/radar.py) – sygnały, których model
 * celowo nie gra: nowy w drużynie, seria formy, debiutant bez historii.
 * To warstwa informacyjna POZA bramami publikacji modelu, nie typ modelu.
 */
export interface RadarWpis {
  id: number;
  /**
   * "drabinka" = kwotowany gracz z historią, bez osobnego sygnału;
   * "bez_feedu" = liga poza feedem statystyk (np. Ekstraklasa) – mamy same
   * kursy + ewentualnie średnie sezonowe, historii meczowej brak
   */
  rodzaj: "transfer" | "forma" | "debiutant" | "drabinka" | "bez_feedu";
  mecz_id: number;
  mecz: string;
  kickoff_ts: number;
  podmiot_id: number | null;
  podmiot: string;
  druzyna: string;
  przeciwnik: string;
  pozycja: string;
  /** w przewidywanym/potwierdzonym XI (null = nie wiemy) */
  xi?: boolean | null;
  /** średnia minut z 6 ostatnich występów (pełne mecze vs ławka) */
  minuty_sr6?: number | null;
  /** true = karta z WCZEŚNIEJSZEGO cyklu, wznowiona z rejestru publikacji.
   *  Bieżące przeliczenie jej nie odtworzyło (zwykle kurs się skrócił i
   *  przewaga spadła pod próg), ale raz pokazana karta zostaje do gwizdka.
   *  `hero` jest ZAMROŻONY z chwili publikacji – kurs sprawdź u bukmachera. */
  wznowiony?: boolean;
  /** znacznik pierwszej publikacji karty */
  opublikowano_ts?: number;
  /**
   * Na czym stoi karta (backend: radar._kategoria_karty) – front dobiera po
   * tym kolor i etykietę:
   *   "analiza"        – sama nasza analiza, drugiej ceny nie mamy
   *   "rynek_zgodny"   – drugi bukmacher wycenia to prawie tak samo
   *   "rozjazd"        – drugi bukmacher płaci zauważalnie więcej
   *   "pewniak_taniej" – jeden mówi „to niemal pewne", drugi płaci sensownie
   */
  kategoria?: "analiza" | "rynek_zgodny" | "rozjazd" | "pewniak_taniej";
  /** najmocniejszy układ „pewniak taniej" na karcie (do wyróżnienia) */
  rozjazd_pewniak?: (RadarRozjazd & { linia: number }) | null;
  /** rozjazd na linii, która wygrała kartę */
  rozjazd_hero?: RadarRozjazd | null;
  /** najlepsza linia karty wg oceny backendu (nagłówek karty) */
  hero?: {
    rynek_kod: string;
    rynek?: string;
    linia: number;
    kurs: number;
    traf: number;
    z: number;
    /** przewaga nad kursem: p_final − 1/kurs */
    edge: number;
    p_final?: number | null;
    p_bazowe?: number | null;
    korekta?: number | null;
  } | null;
  /**
   * Ocena karty – JEDYNE źródło rankingu i oznaczeń (front nie ma własnej
   * definicji „najlepszego typu"). `miejsce` to pozycja w stawce dnia,
   * `klasa` łączy próg przewagi z miejscem w czubie stawki.
   */
  ocena?: {
    miejsce: number;
    klasa: "top" | "mocny" | "solidny";
    /** przewaga nad kursem w punktach prawdopodobieństwa */
    edge: number;
    /**
     * Na czym stoi karta:
     *   "przewaga" – nasza szansa bije cenę bukmachera,
     *   "seria"    – mocne pokrycie przy grywalnej cenie, BEZ przewagi.
     * Karta bez przewagi nie ma prawa wyglądać jak karta z przewagą,
     * dlatego front pisze to wprost (decyzja usera 2026-07-30).
     */
    powod_wejscia?: "przewaga" | "seria";
    p_final?: number | null;
    p_bazowe?: number | null;
    korekta?: number | null;
    kontekst?: RadarKontekst | null;
  } | null;
  /** brak dla rodzaju "drabinka" (nie ma osobnego powodu-sygnału) */
  powod?:
    | "zmiana_ligi"
    | "gral_przeciw"
    | "seria"
    | "brak_historii"
    | "poza_feedem";
  /** średnie sezonowe gracza (bieżący + poprzednie; cache workera) */
  sezony?: RadarSezon[];
  /** etykieta poprzedniej ligi (gdy powod = zmiana_ligi) */
  stara_liga?: string | null;
  stara_liga_utid?: number | null;
  mecze_stara?: number | null;
  mecze_nowa?: number | null;
  /** profil debiutanta (statshub) – gdy rodzaj = debiutant */
  profil?: {
    wzrost?: number | null;
    wiek?: number | null;
    kraj?: string | null;
    noga?: string | null;
  } | null;
  forma_rynek?: string | null;
  forma?: {
    linia: number;
    kurs: number;
    trafienia: number;
    okno: number;
    srednia90_okno: number;
    srednia90_baza: number;
  } | null;
  rynki: RadarRynek[];
}

/** Payload klucza `radar` w Supabase / radar.json. */
export interface Radar {
  wygenerowano_ts: number;
  wpisy: RadarWpis[];
}

/** Wpis rejestru odrzuceń: czemu para (zawodnik, rynek) NIE dostała typu. */
export interface Odrzucenie {
  mecz_id: number;
  podmiot: string;
  druzyna: string;
  rynek_kod: string;
  rynek: string;
  powod:
    | "za_malo_historii"
    | "za_malo_zdarzen"
    | "brak_kursu"
    // rynki drużynowe: dawne "kurs_lub_szansa_poza_widelkami" rozbite na trzy
    // powody (2026-07-27) – jeden licznik na trzy warunki nie mówił, co tnie.
    // Stary kod zostaje: log i dumpy sprzed zmiany nadal go niosą.
    | "kurs_lub_szansa_poza_widelkami"
    | "kurs_poza_widelkami"
    | "szansa_za_niska"
    | "wartosc_ujemna"
    | "krotka_historia"
    | "chwiejna_predykcja"
    | "rozjazd_z_rynkiem"
    | "tylko_w_puli"
    | "kwarantanna_rynku"
    | "kwarantanna_kategorii"
    | "za_stara_historia"
    | "stare_dane"
    | "poza_skladem"
    | "za_malo_minut"
    | "za_pozno"
    | string;
  szczegol: string;
  /** "druzyna" = odrzucony rynek drużynowy; brak = kandydat zawodniczy */
  podmiot_typ?: "druzyna";
}

/** Jeden leg z przeanalizowanej puli – fundament generatora kuponów na żądanie. */
export interface LegPool {
  id: number;
  mecz_id: number;
  mecz: string;
  kickoff_ts: number;
  podmiot_id: number;
  podmiot: string;
  /** "zawodnik" (domyślnie) albo "druzyna" – leg na statystykę całej drużyny */
  podmiot_typ?: string;
  druzyna: string;
  przeciwnik: string;
  rynek_kod: string;
  rynek: string;
  linia: number;
  strona: Strona;
  kurs: number;
  bukmacher: string;
  p_model: number;
  matchup?: boolean;
  /** pełny matchup STYLU (silnik matchup.py) realnie ruszył predykcję */
  matchup_styl?: boolean;
  rotacja?: boolean;
  miekka_linia?: boolean;
  swieze_sklady?: boolean;
  /** BRUTTO – tą liczbą decydują bramy publikacji (patrz betting.ev_brutto_pct) */
  ev_pct?: number | null;
  /** PO PODATKU od stawki – TO pokazujemy użytkownikowi (betting.ev_pct).
   *  Brak pola = rekord sprzed 2026-07-31; wtedy front liczy netto sam. */
  ev_netto?: number | null;
  /** „standard" (12% od stawki) | „bez_podatku" | „zwrot" – zapisany przy
   *  typie, żeby zmiana domyślnego trybu nie unieważniła historii */
  tryb_podatku?: string;
  ev_uk?: number | null;
  kurs_oczekiwany?: number | null;
  ryzyko?: Ryzyko;
  oczekiwane_minuty?: number | null;
  wyzsza_linia?: boolean;
  xi_sygnal?: string | null;
  kurs_ref?: number | null;
  pewnosc?: "wysoka" | "srednia";
  /** przedział wiarygodności szansy [dół, góra] – szerokość steruje
   * zaufaniem do p_model przy składaniu kuponu (kuponBuilder.wagaModelu) */
  ci?: number[];
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
  /** true = mecz u siebie (forma drużynowa) */
  dom?: boolean[];
  /** timestamp (s) każdego meczu – do daty ostatniego meczu (świeżość) */
  ts?: number[];
  srednia90: number;
}

/** Forma DRUŻYNY per rynek drużynowy – karta typu na /druzyny. */
export interface DruzynaForma {
  id: number;
  nazwa: string;
  druzyna: string;
  podmiot_typ: "druzyna";
  forma: Record<string, FormaRynku>;
}

export interface Zawodnik {
  id: number;
  nazwa: string;
  pozycja: string;
  druzyna: string;
  minuty_lacznie: number;
  forma: Record<string, FormaRynku>;
  /** true = w przewidywanym/potwierdzonym pierwszym składzie (na górę TOP POKRYCIA) */
  xi?: boolean;
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
  /** zmierzone kary korelacji legów – generator na żądanie używa tych samych co backend */
  kary_korelacji?: { ta_sama: number; przeciwne: number; nieznane: number };
  /** zmierzone delty wag zaufania per kubełek pewności (kalibracja z rozliczeń) */
  wagi_zaufania?: Record<string, number>;
  /**
   * Rynki chwilowo wstrzymane (traciły pieniądze w oknie ostatnich rozliczeń)
   * – ich typy nie są publikowane, dopóki ROI się nie odbuduje.
   * `roi` to zwrot na jednostkę stawki, ujemny (np. −0.18 = −18%).
   */
  kwarantanna?: Record<
    string,
    // roi opcjonalne: dane sprzed wprowadzenia bramy ROI go nie mają
    { roi?: number; hit: number; sr_p: number; n: number; nazwa: string }
  >;
  /**
   * To samo, ale po POWODZIE, dla którego typ wchodził na listę
   * („ambitniejsza linia", „słaby rywal na tym rynku"...). Rozliczenia
   * pokazały, że model zarabia, gdy typuje nudno, i traci na każdej ścieżce
   * „znaleźliśmy coś więcej niż rynek" – te powody są chwilowo wstrzymane.
   */
  kwarantanna_powodow?: Record<
    string,
    { roi: number; hit: number; sr_p: number; n: number; nazwa: string }
  >;
  /** zapas na obstawienie w minutach – nic nowego nie wchodzi później */
  margines_startu_min?: number;
  /**
   * Zmierzone urealnienie szansy kuponu per horyzont (dzienny /
   * dlugoterminowy / value). Szansa kuponu to iloczyn szans typów, więc błąd
   * pojedynczego typu podnosi się do potęgi – bez tej korekty kupon obiecywał
   * 17%, a wchodził w 10%. Wartość < 1 = tyle z deklaracji naprawdę wchodzi.
   */
  kalibracja_kuponow?: Record<string, number>;
  /**
   * Etykiety przedziałów kursowych per horyzont („dzienny", „dlugoterminowy",
   * „value") – JEDNO ŹRÓDŁO PRAWDY po stronie `kupony.py`. Widok kuponów miał
   * je wpisane na sztywno i po przebudowie progów z 30.07 nie zgadzała się
   * ani jedna, więc zakładka świeciła pustką mimo istniejących kuponów.
   */
  przedzialy_kuponow?: Record<string, string[]>;
}

/** Jeden typ (leg) na kuponie. */
export interface KuponLeg {
  value_bet_id: number;
  podmiot: string;
  rynek: string;
  /** kod rynku – bilet potrzebuje go, żeby nazwać zakład (`opisZakladu`);
   *  opcjonalny, bo kupony sprzed 2026-07-30 go nie niosą */
  rynek_kod?: string;
  /** drużyna, NA KTÓRĄ typujemy – przy „kto więcej" różna od `podmiot` */
  druzyna?: string;
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
  matchup_styl?: boolean;
  rotacja?: boolean;
  miekka_linia?: boolean;
}

/** Propozycja wymiany najsłabszego lega (rentgen kuponu – doradcza). */
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
  /** np. "10–15" – przedział kursowy kuponu */
  cel_label?: string;
  /** dzienny = mecze z dziś/jutra; dlugoterminowy = najbliższe 4 dni */
  horyzont?: "dzienny" | "dlugoterminowy" | "value";
  /** pewniaki = maks. szansa przy zadanym kursie; value = tylko typy z przewagą */
  styl?: "pewniaki" | "value";
  kurs_laczny: number;
  p_model: number;
  fair_kurs: number;
  /** BRUTTO – tą liczbą decydują bramy publikacji (patrz betting.ev_brutto_pct) */
  ev_pct: number;
  /** PO PODATKU od stawki – TO pokazujemy użytkownikowi (betting.ev_pct).
   *  Brak pola = rekord sprzed 2026-07-31; wtedy front liczy netto sam. */
  ev_netto?: number | null;
  /** „standard" (12% od stawki) | „bez_podatku" | „zwrot" – zapisany przy
   *  typie, żeby zmiana domyślnego trybu nie unieważniła historii */
  tryb_podatku?: string;
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
  /** klucz rekordu w logu kuponów – identyfikator do pomijania */
  klucz?: string;
}

/** Rozliczony (lub czekający) typ z automatycznego logu. */
export interface TypRozliczony {
  mecz: string;
  kickoff_ts: number;
  /** przy „kto więcej" to ZAWSZE gospodarz (tak wymaga rozliczanie) – nazwę
   *  typowanej drużyny wylicza `nazwaPodmiotu` z `mecz` i `strona` */
  podmiot: string;
  rynek_kod: string;
  rynek: string;
  linia: number;
  strona: Strona;
  kurs: number | null;
  /** tryb podatkowy zamrożony przy typie; brak = rekord sprzed 2026-07-31,
   *  liczony jak „standard" (12% od stawki) */
  tryb_podatku?: string;
  p_model: number;
  sugestia: boolean;
  wynik: "wygrany" | "przegrany" | "zwrot" | null;
  faktyczna: number | null;
  /** ostatni kurs przed startem meczu (linia zamknięcia rynku) */
  kurs_zamkniecia?: number | null;
  /** CLV: o ile % kurs wzięty był lepszy od zamknięcia (dodatnie = bijemy rynek) */
  clv_pct?: number | null;
  /** typ rozliczony poza publikacją: "kwarantanna_rynku" | "limit_meczu";
   *  widoczny w Skuteczności z oznaczeniem, poza licznikami trafień/ROI */
  poza_publikacja?: string | null;
  /** tylko karty drabinek: klasa zamrożona przy publikacji (top/mocny/solidny) */
  klasa?: string | null;
  /**
   * NA KTÓRYM EKRANIE typ stał – stempel z chwili publikacji, nie zgadywanie
   * po kodzie rynku (patrz `betting.ekran_typu` w pipelinie). `poza_lista`
   * = typ zawodniczy bez znacznika „wysoka szansa": policzony i rozliczany,
   * ale od 2026-08-01 żadna zakładka go nie listuje.
   */
  ekran?: Ekran | null;
  /** stempel ODTWORZONY wstecz dla rekordu sprzed wdrożenia – dzień z takimi
   *  typami ma się do rekonstrukcji przyznać, a nie udawać pewność */
  ekran_odtworzony?: boolean | null;
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
  /** true = user pominął kupon (nie zagrał) – rozliczony tylko do nauki */
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
  /** "YYYY-MM-DD" – dzień meczu */
  dzien: string;
  rozliczone: number;
  trafione: number;
  /** typy z realnym kursem (bez sugestii) – podstawa ROI */
  okazje: number;
  /** ROI flat: stawka 1 j. na okazję (zwrot − postawione) */
  roi_flat: number;
  /** typy rozliczone poza publikacją tego dnia (kwarantanna/limit meczu) */
  poza_n?: number;
  poza_trafione?: number;
  /** realne typy tego dnia (co siadło / nie siadło) – trafione na górze,
   *  typy poza publikacją na końcu z oznaczeniem */
  typy?: TypRozliczony[];
}

/** Strumień skuteczności – patrz rozliczanie._strumien. */
export type Strumien = "pewniaki" | "druzyny" | "drabinki";

/**
 * Ekran, na którym typ się pokazał. Trzy pierwsze to zakładki, które user
 * ogląda; `poza_lista` to typ opublikowany, którego żadna z nich nie listuje.
 * Strumień (wyżej) dzieli PRODUKTY do uczenia, ekran dzieli WIDOKI – dlatego
 * `wysokie_szanse` i `poza_lista` to jeden strumień, a dwa różne ekrany.
 */
export type Ekran =
  | "wysokie_szanse"
  | "druzyny"
  | "drabinki"
  | "poza_lista";

/** Skuteczność jednego strumienia: dni + własne podsumowanie. */
export interface SkutecznoscStrumienia {
  dni: SkutecznoscDnia[];
  podsumowanie: {
    rozliczone: number;
    trafione: number;
    /** udział trafień; null przy zerowej próbie */
    skutecznosc: number | null;
    okazje_rozliczone: number;
    roi_flat: number;
    /** rozliczone poza publikacją (kwarantanna rynku / limit meczu) –
     *  poza trafieniami i ROI powyżej, ale liczone i pokazywane osobno */
    poza_n?: number;
    poza_trafione?: number;
  };
  /** tylko drabinki: rozbicie po klasie karty (czy „top" trafia lepiej) */
  klasy?: Record<string, { n: number; trafione: number; skutecznosc: number }>;
}

/** Wynik jednego rynku w jednej epoce (mundial / sezon ligowy). */
export interface EpokaBlok {
  n: number;
  trafione: number;
  /** udział trafień, 0–1 */
  skutecznosc: number;
  /** zwrot z jednostkowej stawki, np. −0.107 = tracimy 10,7 gr na złotówce */
  roi: number;
}

/** Ten sam rynek w dwóch epokach – do porównania „czy w ligach jest lepiej". */
export interface EpokiRynku {
  nazwa: string;
  mundial: EpokaBlok | null;
  ligi: EpokaBlok | null;
}

/**
 * Jeden wiersz raportu uczenia: paczka kolejnych rozliczeń stałej wielkości.
 *
 * Paczka, a nie tydzień, bo tydzień to raz 3, raz 90 typów – porównanie
 * wiersz do wiersza mówiłoby wtedy głównie o kalendarzu rozgrywek.
 */
export interface PaczkaUczenia {
  /** data pierwszego i ostatniego meczu w paczce (YYYY-MM-DD) */
  od: string;
  do: string;
  n: number;
  trafione: number;
  /** udział trafień, 0–1 */
  hit: number;
  /** średnia szansa, jaką model DEKLAROWAŁ przy publikacji */
  deklaracja: number;
  /** hit − deklaracja; ujemne = model był zbyt pewny siebie */
  luka: number;
  /** zwrot z jednostkowej stawki; null gdy żaden typ nie miał kursu */
  roi: number | null;
  /** false = wiersz jeszcze rośnie (ostatnia, niedokończona paczka) */
  pelna: boolean;
}

/** Postęp jednego strumienia: wiersze + kierunek liczony z pełnych paczek. */
export interface UczenieStrumienia {
  paczki: PaczkaUczenia[];
  trend?: {
    luka_start: number;
    luka_teraz: number;
    /** ujemne = luka się POWIĘKSZA, czyli model NIE robi postępów */
    zmiana: number;
    paczek: number;
  };
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
  /**
   * Ta sama skuteczność rozbita na strumienie. Trzy różne produkty o różnym
   * ryzyku i różnym pochodzeniu prawdopodobieństwa nie mogą dzielić jednego
   * licznika: `pewniaki` = typy zawodnicze z silnika, `druzyny` = rynki
   * drużynowe, `drabinki` = karty z zakładki Drabinki (pokrycie + kontekst).
   */
  skutecznosc_strumienie?: Partial<Record<Strumien, SkutecznoscStrumienia>>;
  /**
   * Czy model robi postępy: paczki po 40 rozliczeń, per strumień.
   * KUCHNIA – `okrojDlaKlienta` to wycina (mówi wprost, o ile model
   * przeszacowuje, tak samo jak `po_rynku`).
   */
  raport_uczenia?: Partial<Record<Strumien, UczenieStrumienia>>;
  /**
   * Mundial vs sezon ligowy, per rynek. NIE JEST JUŻ POKAZYWANE (decyzja usera
   * 2026-07-27: „nie interesuje nas ten mundial"). Pipeline liczy to dalej, bo
   * kwarantanna rynków patrzy na okno 40 ostatnich rozliczeń, a nie na
   * kalendarz – gdyby pytanie wróciło, dane są. Front tego nie czyta.
   */
  epoki_per_rynek?: Record<string, EpokiRynku>;
  kupony?: KuponHistoria[];
  /** ROI kuponów per horyzont (stawka 1 j./kupon; bez pominiętych) */
  kupony_roi?: Record<
    string,
    { n: number; wygrane: number; zwrot_j: number; roi_j: number }
  >;
  /** WSZYSTKIE wygrane kupony (trwały log – nigdy nie znikają) */
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

/**
 * POKRYCIE SKANU – czego umiemy policzyć, a czego nie (zakładka Mecze).
 *
 * Liczone przez pipeline co cykl (`_dump_pokrycie`), do 2026-07-27 lądowało
 * wyłącznie w pliku i nigdy nie docierało na stronę. `rynki` to tabela
 * „naszych statystyk": w ilu meczach zakresu drużynowego widzimy dany rynek
 * i ile par (zawodnik, rynek) ma kwotowanie.
 */
export interface PokrycieRozgrywek {
  kraj: string;
  mecze: number;
  sparowane: number;
  druzynowe: boolean;
}

export interface PokrycieRynkow {
  meczow_druzynowych: number;
  druzynowe: Record<string, number>;
  zawodnicze: Record<string, number>;
}

export interface PokrycieLiga {
  mecze_statshub?: number;
  mecze_superbet?: number;
  sparowane?: number;
  per_rozgrywki?: Record<string, PokrycieRozgrywek>;
  rynki?: PokrycieRynkow;
  typy?: number;
  mecze_z_typami?: number;
  odrzucenia_per_powod?: Record<string, number>;
  wygenerowano_ts?: number;
}
