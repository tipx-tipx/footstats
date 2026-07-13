import { NextResponse } from "next/server";

import { mergeAppData, readAppData, writeAppData } from "@/lib/appDataWrite";

/**
 * Akcje na kuponach (za bramką logowania — proxy.ts):
 *  - {klucz, powod?}                — pomiń kupon (opcjonalny powód),
 *  - {klucz, akcja: "przywroc"}     — cofnij pominięcie (usuń klucz),
 *  - {klucz, akcja: "wymien"}       — zastosuj alternatywę rentgena,
 *  - {klucz, akcja: "przebuduj"}    — przebuduj po potwierdzeniu składów,
 *  - {akcja: "profil", profil}      — charakter buildera kuponów.
 * Pipeline czyta te klucze w każdym cyklu (kupony_pominiete / kupony_wymiana
 * / kupony_przebudowa / kupony_profil). Wymaga SUPABASE_SERVICE_KEY.
 */

const POWODY = new Set(["nie zagrałem", "słaby zestaw", "za niski kurs"]);
const PROFILE = new Set(["bezpieczny", "zbalansowany", "agresywny"]);

// Odpalenie pipeline'u od razu po akcji usera. Bez tego nowy kupon w
// zwolnionym slocie czeka na kolejny cron GitHub Actions, który na prywatnym
// repo bywa dławiony do kilku godzin. GH_DISPATCH_TOKEN = fine-grained PAT z
// uprawnieniem Actions: write na tym repo (jeśli brak — zostajemy przy cronie).
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

  const readKey = (name: string) => readAppData(url, key, name);
  const writeKey = (name: string, payload: unknown) => writeAppData(url, key, name, payload);
  const merge = (name: string, patch?: Record<string, unknown>, remove?: string[]) =>
    mergeAppData(url, key, name, patch, remove);

  const now = Math.floor(Date.now() / 1000);

  // odpal cykl pipeline'u, chyba że któryś odpalił się w ostatnich ~90 s;
  // dispatch jest bonusem — akcja usera jest już zapisana, więc błąd tu nie
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
      /* dispatch nieudany — zostaje cron */
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

  // własny kupon z generatora — zapisz do nauki (rozliczy się w tle jak
  // pominięty, zasila korelację/kalibrację i kalibrację legów)
  if (akcja === "wlasny_nauka") {
    const kk = body.kupon as
      | { legi?: unknown; kurs_laczny?: unknown; p_model?: unknown }
      | undefined;
    if (!kk || !Array.isArray(kk.legi) || kk.legi.length < 2 || kk.legi.length > 12) {
      return NextResponse.json({ error: "zły kupon" }, { status: 400 });
    }
    const legi = kk.legi
      .map((l) => {
        const x = l as Record<string, unknown>;
        return {
          mecz_id: Number(x.mecz_id) || 0,
          mecz: String(x.mecz ?? "").slice(0, 80),
          kickoff_ts: Number(x.kickoff_ts) || 0,
          podmiot_id: Number(x.podmiot_id) || 0,
          podmiot: String(x.podmiot ?? "").slice(0, 60),
          druzyna: String(x.druzyna ?? "").slice(0, 60),
          rynek_kod: String(x.rynek_kod ?? "").slice(0, 30),
          rynek: String(x.rynek ?? "").slice(0, 40),
          linia: Number(x.linia) || 0,
          strona: x.strona === "ponizej" ? "ponizej" : "powyzej",
          kurs: Number(x.kurs) || 0,
          bukmacher: String(x.bukmacher ?? "Superbet").slice(0, 20),
          p_model: Number(x.p_model) || 0,
          pewnosc: x.pewnosc === "wysoka" || x.pewnosc === "srednia" ? x.pewnosc : undefined,
          // te same flagi co kupony.py:_leg_dict — bez nich legi trafiające do
          // nauki WYŁĄCZNIE przez własny kupon są ślepą plamą dla diagnostyki
          // miękkich linii/sygnałów XI/marży UK (dokładnie ten sam P0 fix z tej
          // sesji, ale dla ścieżki "wlasny_nauka", którą wtedy pominięto)
          matchup: Boolean(x.matchup) || undefined,
          rotacja: Boolean(x.rotacja) || undefined,
          wyzsza_linia: Boolean(x.wyzsza_linia) || undefined,
          miekka_linia: Boolean(x.miekka_linia) || undefined,
          swieze_sklady: Boolean(x.swieze_sklady) || undefined,
          xi_sygnal: x.xi_sygnal === "official" || x.xi_sygnal === "predicted" ? x.xi_sygnal : undefined,
          kurs_ref: Number.isFinite(Number(x.kurs_ref)) && x.kurs_ref != null ? Number(x.kurs_ref) : undefined,
          ev_uk: Number.isFinite(Number(x.ev_uk)) && x.ev_uk != null ? Number(x.ev_uk) : undefined,
          ev_pct: Number.isFinite(Number(x.ev_pct)) && x.ev_pct != null ? Number(x.ev_pct) : undefined,
        };
      })
      .filter((l) => l.mecz_id && l.podmiot && l.kurs > 1);
    if (legi.length < 2) {
      return NextResponse.json({ error: "za mało poprawnych legów" }, { status: 400 });
    }
    const sygn = legi
      .map((l) => `${l.mecz_id}:${l.podmiot_id}:${l.rynek_kod}:${l.linia}`)
      .sort()
      .join("|")
      .slice(0, 130);
    // bufor ograniczony (~40 ostatnich) — nie puchnie w nieskończoność. Lista
    // do przycięcia to best-effort odczyt (rzadka operacja porządkowa); zapis
    // nowego wpisu + przycięcie lecą razem w JEDNYM atomowym merge, więc nowy
    // wpis nigdy nie ginie nawet gdy przycięcie akurat "spóźni się" o jeden.
    const wlasne = await readKey("kupony_wlasne");
    const klucze = Object.keys(wlasne);
    const doUsuniecia = klucze.slice(0, Math.max(0, klucze.length - 40));
    const ok = await merge("kupony_wlasne", {
      [sygn]: {
        legi,
        kurs_laczny: Number(kk.kurs_laczny) || 0,
        p_model: Number(kk.p_model) || 0,
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
