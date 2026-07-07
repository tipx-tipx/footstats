import { NextResponse } from "next/server";

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
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "zły JSON" }, { status: 400 });
  }
  const akcja = typeof body.akcja === "string" ? body.akcja : "pomin";

  const headers = {
    apikey: key,
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
  };

  async function readKey(name: string): Promise<Record<string, unknown>> {
    const res = await fetch(
      `${url}/rest/v1/app_data?select=payload&key=eq.${name}`,
      { headers, cache: "no-store" },
    );
    const rows: { payload: Record<string, unknown> }[] = res.ok
      ? await res.json()
      : [];
    return rows[0]?.payload ?? {};
  }

  async function writeKey(name: string, payload: unknown): Promise<boolean> {
    const write = await fetch(`${url}/rest/v1/app_data?on_conflict=key`, {
      method: "POST",
      headers: { ...headers, Prefer: "resolution=merge-duplicates" },
      body: JSON.stringify([{ key: name, payload }]),
    });
    return write.ok;
  }

  const now = Math.floor(Date.now() / 1000);

  if (akcja === "profil") {
    if (typeof body.profil !== "string" || !PROFILE.has(body.profil)) {
      return NextResponse.json({ error: "zły profil" }, { status: 400 });
    }
    if (!(await writeKey("kupony_profil", body.profil))) {
      return NextResponse.json({ error: "zapis nieudany" }, { status: 502 });
    }
    return NextResponse.json({ ok: true, profil: body.profil });
  }

  const klucz = body.klucz;
  if (typeof klucz !== "string" || klucz.length < 3 || klucz.length > 160) {
    return NextResponse.json({ error: "zły klucz" }, { status: 400 });
  }

  if (akcja === "pomin") {
    const pominiete = await readKey("kupony_pominiete");
    const powod =
      typeof body.powod === "string" && POWODY.has(body.powod)
        ? body.powod
        : null;
    pominiete[klucz] = powod ? { ts: now, powod } : now;
    if (!(await writeKey("kupony_pominiete", pominiete))) {
      return NextResponse.json({ error: "zapis nieudany" }, { status: 502 });
    }
    return NextResponse.json({ ok: true });
  }

  if (akcja === "przywroc") {
    const pominiete = await readKey("kupony_pominiete");
    delete pominiete[klucz];
    if (!(await writeKey("kupony_pominiete", pominiete))) {
      return NextResponse.json({ error: "zapis nieudany" }, { status: 502 });
    }
    return NextResponse.json({ ok: true });
  }

  if (akcja === "wymien" || akcja === "przebuduj") {
    const name = akcja === "wymien" ? "kupony_wymiana" : "kupony_przebudowa";
    const payload = await readKey(name);
    payload[klucz] = now;
    if (!(await writeKey(name, payload))) {
      return NextResponse.json({ error: "zapis nieudany" }, { status: 502 });
    }
    return NextResponse.json({ ok: true });
  }

  return NextResponse.json({ error: "nieznana akcja" }, { status: 400 });
}
