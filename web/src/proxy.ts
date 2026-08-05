/**
 * Bramka dostępu – cała aplikacja za hasłem (narzędzie osobiste).
 *
 * Przepuszcza: /login, /api/login, zasoby statyczne (pliki z kropką, _next).
 * Reszta wymaga ważnego ciasteczka sesji (lib/auth.ts), inaczej -> /login.
 * Brak APP_PASSWORD w env = tryb otwarty (lokalny development).
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { SESSION_COOKIE, verifySessionToken } from "@/lib/auth";

export default async function proxy(request: NextRequest) {
  const password = process.env.APP_PASSWORD;
  const secret = process.env.AUTH_SECRET;
  if (!password || !secret) return NextResponse.next(); // dev bez hasła

  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (await verifySessionToken(token, secret)) {
    return NextResponse.next();
  }
  const loginUrl = new URL("/login", request.url);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  // wszystko poza logowaniem, API logowania, PINGIEM CRONA, wewnętrznymi
  // zasobami Next i plikami statycznymi (ścieżki z kropką: logo.png, ...)
  //
  // `api/tick` musi być poza bramką, bo woła go zewnętrzny pinger, który nie
  // ma jak się zalogować — bez tego dostawałby przekierowanie na /login
  // i cykl nigdy by nie ruszył. Trasa NIE jest przez to otwarta: pilnuje się
  // sama sekretem `TICK_SECRET` porównywanym stałoczasowo, a bez tej zmiennej
  // w ogóle nic nie robi.
  matcher: ["/((?!login|api/login|api/tick|_next/static|_next/image|.*\\..*).*)"],
};
