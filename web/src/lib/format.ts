/** Formatowanie liczb i dat po polsku. */

export function fmtProc(p: number, digits = 0): string {
  return `${(p * 100).toFixed(digits).replace(".", ",")}%`;
}

export function fmtKurs(k: number): string {
  return k.toFixed(2).replace(".", ",");
}

export function fmtLinia(l: number): string {
  return l.toFixed(1).replace(".", ",");
}

export function fmtEV(ev: number): string {
  const sign = ev > 0 ? "+" : "";
  return `${sign}${ev.toFixed(1).replace(".", ",")}%`;
}

export function fmtMnoznik(m: number): string {
  return `×${m.toFixed(2).replace(".", ",")}`;
}

/** Bilans w jednostkach (stawka 1 j. na typ): "+8,2u", "−3u", "0u". */
export function fmtU(v: number): string {
  const s = v.toFixed(2).replace(".", ",").replace(/,?0+$/, "");
  return `${v > 0 ? "+" : ""}${s === "" || s === "-" ? "0" : s}u`;
}

/**
 * Odmiana rzeczownika przez liczbę – po polsku formy są TRZY, nie dwie:
 * 1 zakład, 2–4 zakłady, 5+ zakładów. Warunek „nie 12–14" jest konieczny,
 * bo 22 idzie jak 2, ale 12 jak 5.
 *
 *     odmien(26, "zakład", "zakłady", "zakładów")  ->  "zakładów"
 */
export function odmien(
  n: number,
  jeden: string,
  dwaCztery: string,
  wiele: string,
): string {
  const a = Math.abs(Math.round(n));
  if (a === 1) return jeden;
  const r10 = a % 10;
  const r100 = a % 100;
  if (r10 >= 2 && r10 <= 4 && !(r100 >= 12 && r100 <= 14)) return dwaCztery;
  return wiele;
}

/**
 * Teksty z pipeline miewają kropkę dziesiętną ("Średnio 2.80") – na widoku
 * zamieniamy ją na przecinek. Tylko między cyframi, reszta tekstu nietknięta.
 */
export function fmtOpisLiczby(s: string): string {
  return s.replace(/(\d)\.(\d)/g, "$1,$2");
}

export function fmtDataCzas(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString("pl-PL", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  });
}

/** "2026-07-10" -> "czw, 10 lip" (dłużej: "czwartek, 10 lipca").
 *  Doba brana z południa lokalnego – inaczej strefa przesuwa etykietę o dzień. */
export function fmtDzien(dzien: string, dlugo = false): string {
  return new Intl.DateTimeFormat("pl-PL", {
    weekday: dlugo ? "long" : "short",
    day: "numeric",
    month: dlugo ? "long" : "short",
  }).format(new Date(`${dzien}T12:00:00`));
}

/** Sama godzina kickoffu ("20:15") w czasie polskim. */
export function fmtGodzina(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("pl-PL", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  });
}

export const STRONA_LABEL: Record<string, string> = {
  powyzej: "powyżej",
  ponizej: "poniżej",
  // „kto więcej" (rynek dodany 2026-07-30) — strona mówi, KTÓRA drużyna,
  // nie w którą stronę linii. Etykiety same z siebie nie trafiają do zdania
  // (buduje je `opisZakladu`), ale muszą tu być: bez nich `STRONA_LABEL[...]`
  // zwracało `undefined` i tyle dosłownie wyświetlało się użytkownikowi.
  gospodarz: "gospodarz",
  gosc: "gość",
};

/* ------------------------------------------------------------------ *
 * OPIS ZAKŁADU — jedno miejsce, w którym rekord staje się zdaniem
 * ------------------------------------------------------------------ */

/**
 * Sklejanie `rynek + strona + linia` było przepisane w OŚMIU komponentach
 * (wiersz, karta, drabinka, tabela Skuteczności, bilet kuponu, historia
 * kuponów, rentgen, tracker). Każda kopia zakładała, że strona to zawsze
 * „powyżej/poniżej", a linia zawsze coś znaczy. Rynek „kto więcej" łamie
 * oba założenia naraz i dlatego pokazywał:
 *
 *     Newell's Old Boys · 22:00 z Newell's Old Boys
 *     więcej: strzały undefined 0,0
 *
 * Trzy błędy w jednej linijce: `undefined` z brakującej etykiety, „0,0"
 * z linii, której ten rynek nie ma, i nazwa GOSPODARZA przy zakładzie na
 * gościa — bo `podmiot` w tym rynku to zawsze gospodarz (tak wymaga
 * rozliczanie), a typowana drużyna siedzi w polu `druzyna`.
 */
export interface ZakladDoOpisu {
  rynek: string;
  rynek_kod?: string;
  strona: string;
  linia: number;
  podmiot: string;
  /** „Gospodarz – Gość"; jedyne źródło nazw, gdy rekord nie niesie `druzyna` */
  mecz?: string;
  druzyna?: string | null;
  przeciwnik?: string | null;
}

const CZY_WIECEJ = (b: ZakladDoOpisu) => (b.rynek_kod ?? "").startsWith("wiecej_");
const CZY_SUMA = (b: ZakladDoOpisu) => (b.rynek_kod ?? "").startsWith("match_");

/**
 * Dopełniacz nazwy rynku — „więcej STRZAŁÓW niż Radomiak", nie „więcej
 * strzały". Odmiana idzie po KODZIE rynku, nie po napisie: kod jest stały,
 * a nazwa bywa przerabiana po drodze (pipeline ucina z niej „drużyny").
 * Nieznany kod spada na mianownik — brzydko, ale zrozumiale.
 */
const DOPELNIACZ_RYNKU: Record<string, string> = {
  wiecej_shots: "strzałów",
  wiecej_sot: "celnych strzałów",
  wiecej_fouls: "fauli",
  wiecej_cards: "kartek",
  wiecej_corners: "rzutów rożnych",
};

/**
 * Strona W SENSIE LINII, albo `undefined`, gdy rynek linii nie ma.
 *
 * Wszystko, co rysuje poprzeczkę (pasek szansy, rozkład wyników, światło
 * formy), ma sens wyłącznie przy „powyżej/poniżej". Przy „kto więcej" linia
 * wynosi 0 i taki wykres opisywałby zakład, którego nie ma.
 */
export function stronaLinii(s: string): "powyzej" | "ponizej" | undefined {
  return s === "powyzej" || s === "ponizej" ? s : undefined;
}

/** „Gospodarz – Gość" -> [gospodarz, gość]; półpauza albo myślnik. */
function stronyMeczu(mecz?: string): [string, string] {
  const czesci = (mecz ?? "").split(/\s+[–—-]\s+/);
  return czesci.length === 2 ? [czesci[0], czesci[1]] : ["", ""];
}

/**
 * Kogo NAPRAWDĘ typujemy. Dla „kto więcej" to nie jest `podmiot`:
 * rozliczanie wymaga, żeby `podmiot` trzymał zawsze gospodarza, więc przy
 * zakładzie na gościa wiersz nazwałby zupełnie inną drużynę.
 */
export function nazwaPodmiotu(b: ZakladDoOpisu): string {
  if (!CZY_WIECEJ(b)) return b.podmiot;
  if (b.druzyna) return b.druzyna;
  const [gosp, gosc] = stronyMeczu(b.mecz);
  return (b.strona === "gosc" ? gosc : gosp) || b.podmiot;
}

/** Druga drużyna zakładu — do cichej linijki „19:00 z …" obok nazwy. */
export function rywalWZakladzie(b: ZakladDoOpisu): string {
  const [gosp, gosc] = stronyMeczu(b.mecz);
  if (CZY_WIECEJ(b)) {
    if (b.przeciwnik) return b.przeciwnik;
    return b.strona === "gosc" ? gosp : gosc;
  }
  // suma meczowa: `przeciwnik` przychodzi z pipeline'u PUSTY, bo zakład jest
  // o cały mecz — ale wiersz i tak ma prawo pokazać, z kim ten mecz jest
  if (CZY_SUMA(b)) return b.podmiot === gosp ? gosc : gosp;
  return b.przeciwnik || "";
}

/**
 * Zakład jednym zdaniem.
 *
 * `krotko` = wersja do gęstej ceduły: „Gole drużyny" -> „gole", bo w wierszu
 * liczy się rytm skanowania, a słowo „drużyny" stoi tam w każdej linii.
 */
export function opisZakladu(b: ZakladDoOpisu, krotko = false): string {
  if (CZY_WIECEJ(b)) {
    // „Więcej: strzały" -> „strzałów"; zdanie ma nieść kierunek zakładu,
    // a nie dwukropek z nazwy rynku
    const co =
      DOPELNIACZ_RYNKU[b.rynek_kod ?? ""] ??
      b.rynek.replace(/^więcej:\s*/i, "").toLowerCase();
    const rywal = rywalWZakladzie(b);
    return rywal ? `więcej ${co} niż ${rywal}` : `więcej ${co} niż rywal`;
  }
  const nazwa = krotko
    ? b.rynek.toLowerCase().replace(/\s*drużyny\s*/g, " ").trim()
    : b.rynek.toLowerCase();
  // `?? b.strona` zamiast pustki: nowy rynek ma pokazać brzydką, ale PRAWDZIWĄ
  // etykietę, nigdy „undefined" (patrz komentarz przy STRONA_LABEL)
  const strona = STRONA_LABEL[b.strona] ?? b.strona;
  return `${nazwa} ${strona} ${fmtLinia(b.linia)}`;
}

export const PEWNOSC_LABEL: Record<string, string> = {
  wysoka: "wysoka",
  srednia: "średnia",
  niska: "niska",
};

export const RYZYKO_LABEL: Record<string, string> = {
  niskie: "niskie",
  srednie: "średnie",
  wysokie: "wysokie",
};
