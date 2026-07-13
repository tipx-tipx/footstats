import { NextResponse } from "next/server";

import { createSessionToken, SESSION_COOKIE, SESSION_DAYS } from "@/lib/auth";
import { mergeAppData, readAppData } from "@/lib/appDataWrite";

// Rate-limit prób logowania per IP — bez tego jedyna obrona było 400ms
// sekwencyjnego opóźnienia, które równoległe żądania całkowicie omijają
// (jedno hasło na cały produkt = tania powierzchnia na brute-force). Zapis
// idzie przez mergeAppData (migracja 0003, atomowy merge/remove) — dwie
// równoległe próby logowania z TEGO SAMEGO IP już się nie nadpisują.
const RATE_LIMIT_WINDOW_S = 15 * 60;
const RATE_LIMIT_MAX_PROB = 8;
const RATE_LIMIT_KEY = "login_proby";

function clientIp(request: Request): string {
  const fwd = request.headers.get("x-forwarded-for");
  if (fwd) return fwd.split(",")[0].trim();
  return request.headers.get("x-real-ip") ?? "unknown";
}

type LoginProby = Record<string, { count: number; first_ts: number }>;

/** Logowanie: poprawne hasło -> ciasteczko sesji na SESSION_DAYS dni. */
export async function POST(request: Request) {
  const password = process.env.APP_PASSWORD;
  const secret = process.env.AUTH_SECRET;
  if (!password || !secret) {
    return NextResponse.json({ ok: true }); // tryb otwarty (dev)
  }

  const supaUrl = process.env.SUPABASE_URL?.replace(/\/$/, "");
  const supaKey = process.env.SUPABASE_SERVICE_KEY;
  const rateLimitOn = Boolean(supaUrl && supaKey);
  const ip = clientIp(request);
  const now = Math.floor(Date.now() / 1000);

  // stare wpisy (poza oknem) do wywalenia przy najbliższym zapisie — best
  // effort, nie musi być idealnie świeże (rzadka operacja porządkowa)
  const proby: LoginProby = rateLimitOn
    ? (await readAppData(supaUrl!, supaKey!, RATE_LIMIT_KEY)) as LoginProby
    : {};
  const stale = Object.entries(proby)
    .filter(([, rec]) => now - rec.first_ts >= RATE_LIMIT_WINDOW_S)
    .map(([ip2]) => ip2);
  const rec = stale.includes(ip) ? undefined : proby[ip];

  if (rateLimitOn && rec && rec.count >= RATE_LIMIT_MAX_PROB) {
    return NextResponse.json(
      { ok: false, error: "zbyt wiele prób — spróbuj ponownie za kilkanaście minut" },
      { status: 429 },
    );
  }

  let given = "";
  try {
    const body = await request.json();
    given = String(body?.haslo ?? "");
  } catch {
    /* puste body -> złe hasło */
  }

  // porównanie stałoczasowe
  const a = new TextEncoder().encode(given);
  const b = new TextEncoder().encode(password);
  let diff = a.length === b.length ? 0 : 1;
  for (let i = 0; i < Math.min(a.length, b.length); i++) diff |= a[i] ^ b[i];

  if (diff !== 0) {
    if (rateLimitOn) {
      const nowRec = rec
        ? { count: rec.count + 1, first_ts: rec.first_ts }
        : { count: 1, first_ts: now };
      await mergeAppData(
        supaUrl!, supaKey!, RATE_LIMIT_KEY,
        { [ip]: nowRec }, stale.filter((s) => s !== ip),
      );
    }
    // drobne opóźnienie utrudnia zgadywanie na ślepo
    await new Promise((r) => setTimeout(r, 400));
    return NextResponse.json({ ok: false }, { status: 401 });
  }

  if (rateLimitOn) {
    const toRemove = stale.includes(ip) ? stale : [...stale, ip];
    if (toRemove.length) {
      await mergeAppData(supaUrl!, supaKey!, RATE_LIMIT_KEY, {}, toRemove);
    }
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set(SESSION_COOKIE, await createSessionToken(secret), {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_DAYS * 24 * 60 * 60,
  });
  return res;
}

/** Wylogowanie: skasuj ciasteczko. */
export async function DELETE() {
  const res = NextResponse.json({ ok: true });
  res.cookies.set(SESSION_COOKIE, "", { path: "/", maxAge: 0 });
  return res;
}
