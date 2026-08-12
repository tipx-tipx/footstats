import { NextResponse } from "next/server";

import { mergeAppData, readAppData, writeAppData } from "@/lib/appDataWrite";
import { czytajRole } from "@/lib/rola";

/**
 * Akcje na kuponach (za bramką logowania – proxy.ts):
 *  - {klucz, powod?}                – pomiń kupon (opcjonalny powód),
 *  - {klucz, akcja: "przywroc"}     – cofnij pominięcie (usuń klucz),
 *  - {klucz, akcja: "wymien"}       – zastosuj alternatywę rentgena,
 *  - {klucz, akcja: "przebuduj"}    – przebuduj po potwierdzeniu składów,
 *  - {akcja: "profil", profil}      – charakter buildera kuponów.
 * Pipeline czyta te klucze w każdym cyklu (kupony_pominiete / kupony_wymiana
 * / kupony_przebudowa / kupony_profil). Wymaga SUPABASE_SERVICE_KEY.
 *
 * ⚑ DWA ZABEZPIECZENIA DOŁOŻONE 2026-08-12 (P0 z audytu zewnętrznego).
 *
 * 1. KONTROLA ROLI. Bramka w `proxy.ts` sprawdza tylko, czy ktoś JEST
 *    zalogowany — a `KLIENT_PASSWORD` daje sesję tak samo jak `APP_PASSWORD`.
 *    Klient mógł więc przez ten endpoint zmienić GLOBALNY profil buildera,
 *    pominąć cudzy kupon i wywołać cykl pipeline'u. To są operacje na wspólnym
 *    stanie produktu, nie na jego własnym koncie, więc wymagają administratora.
 *    Kupony per użytkownik to osobna, większa zmiana (jest w kolejce) — do
 *    tego czasu obowiązuje ta prostsza i bezpieczniejsza reguła.
 *
 * 2. PARAMETRY MODELOWE NIE POCHODZĄ JUŻ Z PRZEGLĄDARKI. Ścieżka
 *    `wlasny_nauka` przyjmowała `p_model`, kursy, EV i flagi diagnostyczne
 *    wprost z żądania i zapisywała je do `kupony_wlasne` — a stamtąd trafiają
 *    do księgi i do WARSTW UCZENIA. Dowolna liczba wysłana z konsoli
 *    przeglądarki uczyła model. Teraz z żądania bierzemy WYŁĄCZNIE
 *    identyfikatory (mecz, zawodnik/drużyna, rynek, linia, strona), a resztę
 *    odtwarzamy po stronie serwera z `legi_pool` — czyli z tego, co sami
 *    policzyliśmy w ostatnim cyklu. Leg bez pokrycia w puli jest odrzucany.
 */

const POWODY = new Set(["nie zagrałem", "słaby zestaw", "za niski kurs"]);
const PROFILE = new Set(["bezpieczny", "zbalansowany", "agresywny"]);

// Odpalenie pipeline'u od razu po akcji usera. Bez tego nowy kupon w
// zwolnionym slocie czeka na kolejny cron GitHub Actions, który na prywatnym
// repo bywa dławiony do kilku godzin. GH_DISPATCH_TOKEN = fine-grained PAT z
// uprawnieniem Actions: write na tym repo (jeśli brak – zostajemy przy cronie).
const GH_REPO = process.env.GH_REPO ?? "tipx-tipx/footstats";
const GH_TOKEN = process.env.GH_DISPATCH_TOKEN;
const GH_WORKFLOW = "cycle.yml";
const GH_REF = process.env.GH_REF ?? "master";
const DISPATCH_THROTTLE_S = 90; // jeden cykl i tak przelicza wszystkie zmiany

export async function POST(req: Request) {
  const url = process.env.SUPABASE_URL?.replace(/\/$/, "");
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) {
    return NextResponse.json(
      { error: "brak konfiguracji Supabase (SUPABASE_SERVICE_KEY)" },
      { status: 503 },
    );
  }

  let body: {
    klucz?: unknown;
    akcja?: unknown;
    powod?: unknown;
    profil?: unknown;
    kupon?: unknown;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "zły JSON" }, { status: 400 });
  }
  const akcja = typeof body.akcja === "string" ? body.akcja : "pomin";

  // ⚑ Akcje ruszające WSPÓLNY stan produktu — tylko administrator.
  // `wlasny_nauka` zostaje dostępne dla klienta: to jego własny kupon
  // z generatora, a parametry modelowe i tak odtwarzamy z serwera niżej.
  const AKCJE_ADMINA = new Set(["profil", "pomin", "przywroc", "wymien", "przebuduj"]);
  if (AKCJE_ADMINA.has(akcja) && (await czytajRole()) !== "admin") {
    return NextResponse.json(
      { error: "ta akcja wymaga konta administratora" },
      { status: 403 },
    );
  }

  const readKey = (name: string) => readAppData(url, key, name);
  const writeKey = (name: string, payload: unknown) => writeAppData(url, key, name, payload);
  const merge = (name: string, patch?: Record<string, unknown>, remove?: string[]) =>
    mergeAppData(url, key, name, patch, remove);

  const now = Math.floor(Date.now() / 1000);

  // odpal cykl pipeline'u, chyba że któryś odpalił się w ostatnich ~90 s;
  // dispatch jest bonusem – akcja usera jest już zapisana, więc błąd tu nie
  // wywraca odpowiedzi (cron i tak w końcu dogoni)
  async function odpalCykl(): Promise<void> {
    if (!GH_TOKEN) return;
    try {
      const stan = await readKey("cykl_dispatch");
      const ostatni = typeof stan.ts === "number" ? stan.ts : 0;
      if (now - ostatni < DISPATCH_THROTTLE_S) return;
      const res = await fetch(
        `https://api.github.com/repos/${GH_REPO}/actions/workflows/${GH_WORKFLOW}/dispatches`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${GH_TOKEN}`,
            Accept: "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "footstats-kupony",
          },
          body: JSON.stringify({ ref: GH_REF }),
        },
      );
      if (res.ok) await writeKey("cykl_dispatch", { ts: now });
    } catch {
      /* dispatch nieudany – zostaje cron */
    }
  }

  if (akcja === "profil") {
    if (typeof body.profil !== "string" || !PROFILE.has(body.profil)) {
      return NextResponse.json({ error: "zły profil" }, { status: 400 });
    }
    if (!(await writeKey("kupony_profil", body.profil))) {
      return NextResponse.json({ error: "zapis nieudany" }, { status: 502 });
    }
    await odpalCykl();
    return NextResponse.json({ ok: true, profil: body.profil });
  }

  // własny kupon z generatora – zapisz do nauki (rozliczy się w tle jak
  // pominięty, zasila korelację/kalibrację i kalibrację legów)
  if (akcja === "wlasny_nauka") {
    const kk = body.kupon as
      | { legi?: unknown; kurs_laczny?: unknown; p_model?: unknown }
      | undefined;
    if (!kk || !Array.isArray(kk.legi) || kk.legi.length < 2 || kk.legi.length > 12) {
      return NextResponse.json({ error: "zły kupon" }, { status: 400 });
    }
    // PULA Z OSTATNIEGO CYKLU — jedyne źródło parametrów modelowych.
    // Żądanie wskazuje TYLKO, o który leg chodzi; wszystko, co wpływa na
    // księgę i uczenie (p_model, EV, flagi, kurs), bierzemy stąd.
    const pool = await readKey("legi_pool");
    const poolLista: Record<string, unknown>[] = Array.isArray(pool)
      ? (pool as Record<string, unknown>[])
      : Array.isArray((pool as { legi?: unknown }).legi)
        ? ((pool as { legi: Record<string, unknown>[] }).legi)
        : [];
    const kluczLega = (x: Record<string, unknown>) =>
      [
        Number(x.mecz_id) || 0,
        Number(x.podmiot_id) || 0,
        String(x.rynek_kod ?? ""),
        Number(x.linia) || 0,
        x.strona === "ponizej" ? "ponizej" : "powyzej",
      ].join(":");
    const wPuli = new Map(poolLista.map((l) => [kluczLega(l), l]));

    const legi = kk.legi
      .map((l) => {
        const x = l as Record<string, unknown>;
        const zrodlo = wPuli.get(kluczLega(x));
        if (!zrodlo) return null;
        // od tego miejsca `zrodlo` (nasza pula), nigdy `x` (przeglądarka)
        const s = zrodlo as Record<string, unknown>;
        const opcjonalnaFlaga = (k: string) => (s[k] ? true : undefined);
        const opcjonalnaLiczba = (k: string) =>
          Number.isFinite(Number(s[k])) && s[k] != null ? Number(s[k]) : undefined;
        return {
          mecz_id: Number(s.mecz_id) || 0,
          mecz: String(s.mecz ?? "").slice(0, 80),
          kickoff_ts: Number(s.kickoff_ts) || 0,
          podmiot_id: Number(s.podmiot_id) || 0,
          podmiot: String(s.podmiot ?? "").slice(0, 60),
          druzyna: String(s.druzyna ?? "").slice(0, 60),
          rynek_kod: String(s.rynek_kod ?? "").slice(0, 30),
          rynek: String(s.rynek ?? "").slice(0, 40),
          linia: Number(s.linia) || 0,
          strona: s.strona === "ponizej" ? "ponizej" : "powyzej",
          kurs: Number(s.kurs) || 0,
          bukmacher: String(s.bukmacher ?? "Superbet").slice(0, 20),
          p_model: Number(s.p_model) || 0,
          pewnosc: s.pewnosc === "wysoka" || s.pewnosc === "srednia" ? s.pewnosc : undefined,
          // te same flagi co kupony.py:_leg_dict – bez nich legi trafiające do
          // nauki WYŁĄCZNIE przez własny kupon są ślepą plamą dla diagnostyki
          // miękkich linii/sygnałów XI/marży UK
          matchup: opcjonalnaFlaga("matchup"),
          matchup_styl: opcjonalnaFlaga("matchup_styl"),
          rotacja: opcjonalnaFlaga("rotacja"),
          wyzsza_linia: opcjonalnaFlaga("wyzsza_linia"),
          miekka_linia: opcjonalnaFlaga("miekka_linia"),
          swieze_sklady: opcjonalnaFlaga("swieze_sklady"),
          xi_sygnal:
            s.xi_sygnal === "official" || s.xi_sygnal === "predicted"
              ? s.xi_sygnal
              : undefined,
          kurs_ref: opcjonalnaLiczba("kurs_ref"),
          ev_uk: opcjonalnaLiczba("ev_uk"),
          ev_pct: opcjonalnaLiczba("ev_pct"),
          // rachunek „skąd wzięła się ta liczba" — jeśli pula go niesie,
          // niech jedzie razem z legiem (patrz betting.stempel_rachunku)
          rachunek:
            s.rachunek && typeof s.rachunek === "object" ? s.rachunek : undefined,
        };
      })
      .filter((l): l is NonNullable<typeof l> => !!l)
      .filter((l) => l.mecz_id && l.podmiot && l.kurs > 1);
    if (legi.length < 2) {
      return NextResponse.json(
        {
          error:
            "za mało typów z bieżącej puli – kupon mógł się zdezaktualizować, " +
            "odśwież stronę",
        },
        { status: 400 },
      );
    }
    const sygn = legi
      .map((l) => `${l.mecz_id}:${l.podmiot_id}:${l.rynek_kod}:${l.linia}`)
      .sort()
      .join("|")
      .slice(0, 130);
    // bufor ograniczony (~40 ostatnich) – nie puchnie w nieskończoność. Lista
    // do przycięcia to best-effort odczyt (rzadka operacja porządkowa); zapis
    // nowego wpisu + przycięcie lecą razem w JEDNYM atomowym merge, więc nowy
    // wpis nigdy nie ginie nawet gdy przycięcie akurat "spóźni się" o jeden.
    const wlasne = await readKey("kupony_wlasne");
    const klucze = Object.keys(wlasne);
    const doUsuniecia = klucze.slice(0, Math.max(0, klucze.length - 40));
    // ...a liczby całego kuponu z LEGÓW, nie z żądania — tą samą zasadą co
    // wyżej. Iloczyn szans zakłada niezależność zdarzeń; pipeline i tak liczy
    // kupon własnym rachunkiem (z korelacją), więc to jest wartość zapasowa,
    // która ma być spójna z legami, a nie przyjęta na słowo.
    const kursLaczny = legi.reduce((acc, l) => acc * l.kurs, 1);
    const pKuponu = legi.reduce((acc, l) => acc * (l.p_model || 0), 1);
    const ok = await merge("kupony_wlasne", {
      [sygn]: {
        legi,
        kurs_laczny: Math.round(kursLaczny * 100) / 100,
        p_model: Math.round(pKuponu * 10000) / 10000,
        zapisano_ts: now,
      },
    }, doUsuniecia);
    if (!ok) {
      return NextResponse.json({ error: "zapis nieudany" }, { status: 502 });
    }
    await odpalCykl();
    return NextResponse.json({ ok: true });
  }

  const klucz = body.klucz;
  if (typeof klucz !== "string" || klucz.length < 3 || klucz.length > 160) {
    return NextResponse.json({ error: "zły klucz" }, { status: 400 });
  }

  if (akcja === "pomin") {
    const powod =
      typeof body.powod === "string" && POWODY.has(body.powod)
        ? body.powod
        : null;
    if (!(await merge("kupony_pominiete", { [klucz]: powod ? { ts: now, powod } : now }))) {
      return NextResponse.json({ error: "zapis nieudany" }, { status: 502 });
    }
    await odpalCykl();
    return NextResponse.json({ ok: true });
  }

  if (akcja === "przywroc") {
    if (!(await merge("kupony_pominiete", {}, [klucz]))) {
      return NextResponse.json({ error: "zapis nieudany" }, { status: 502 });
    }
    await odpalCykl();
    return NextResponse.json({ ok: true });
  }

  if (akcja === "wymien" || akcja === "przebuduj") {
    const name = akcja === "wymien" ? "kupony_wymiana" : "kupony_przebudowa";
    if (!(await merge(name, { [klucz]: now }))) {
      return NextResponse.json({ error: "zapis nieudany" }, { status: 502 });
    }
    await odpalCykl();
    return NextResponse.json({ ok: true });
  }

  return NextResponse.json({ error: "nieznana akcja" }, { status: 400 });
}
