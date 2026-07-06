import { NextResponse } from "next/server";

/**
 * Pomiń kupon (user go nie zagrał): dopisz klucz kuponu do
 * app_data.kupony_pominiete w Supabase. Pipeline w następnym cyklu zwolni
 * slot (nowy kupon w tym przedziale), a pominięty rozliczy się w tle —
 * model uczy się także z niezagranych kuponów.
 *
 * Wymaga SUPABASE_SERVICE_KEY w env (anon key jest tylko do odczytu).
 */
export async function POST(req: Request) {
  const url = process.env.SUPABASE_URL?.replace(/\/$/, "");
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) {
    return NextResponse.json(
      { error: "brak konfiguracji Supabase (SUPABASE_SERVICE_KEY)" },
      { status: 503 },
    );
  }

  let klucz: unknown;
  try {
    ({ klucz } = await req.json());
  } catch {
    return NextResponse.json({ error: "zły JSON" }, { status: 400 });
  }
  if (typeof klucz !== "string" || klucz.length < 3 || klucz.length > 160) {
    return NextResponse.json({ error: "zły klucz" }, { status: 400 });
  }

  const headers = {
    apikey: key,
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
  };
  const res = await fetch(
    `${url}/rest/v1/app_data?select=payload&key=eq.kupony_pominiete`,
    { headers, cache: "no-store" },
  );
  const rows: { payload: Record<string, number> }[] = res.ok
    ? await res.json()
    : [];
  const pominiete = rows[0]?.payload ?? {};
  pominiete[klucz] = Math.floor(Date.now() / 1000);

  const write = await fetch(`${url}/rest/v1/app_data?on_conflict=key`, {
    method: "POST",
    headers: { ...headers, Prefer: "resolution=merge-duplicates" },
    body: JSON.stringify([{ key: "kupony_pominiete", payload: pominiete }]),
  });
  if (!write.ok) {
    return NextResponse.json({ error: "zapis nieudany" }, { status: 502 });
  }
  return NextResponse.json({ ok: true });
}
