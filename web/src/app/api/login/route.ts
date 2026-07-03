import { NextResponse } from "next/server";

import { createSessionToken, SESSION_COOKIE, SESSION_DAYS } from "@/lib/auth";

/** Logowanie: poprawne hasło -> ciasteczko sesji na SESSION_DAYS dni. */
export async function POST(request: Request) {
  const password = process.env.APP_PASSWORD;
  const secret = process.env.AUTH_SECRET;
  if (!password || !secret) {
    return NextResponse.json({ ok: true }); // tryb otwarty (dev)
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
    // drobne opóźnienie utrudnia zgadywanie na ślepo
    await new Promise((r) => setTimeout(r, 400));
    return NextResponse.json({ ok: false }, { status: 401 });
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
