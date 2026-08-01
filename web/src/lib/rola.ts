import { cookies } from "next/headers";

import { SESSION_COOKIE, verifySessionRole, type Rola } from "./auth";

/**
 * Rola zalogowanego z ciasteczka – do użycia w komponentach serwerowych.
 *
 * Bez hasła w env (lokalny development) zwraca `admin`, żeby praca na
 * własnej maszynie nie wymagała logowania.
 */
export async function czytajRole(): Promise<Rola> {
  const secret = process.env.AUTH_SECRET;
  if (!process.env.APP_PASSWORD || !secret) return "admin";
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  return (await verifySessionRole(token, secret)) ?? "klient";
}

/**
 * Czy pokazywać kuchnię (diagnostyka, typy „na próbę", sprawdziany modelu).
 *
 * `podgladKlienta` to przełącznik dla admina: „pokaż mi to, co widzi klient".
 * Bez niego przygotowanie strony pod sprzedaż byłoby zgadywanką – trzeba by
 * się wylogowywać, żeby zobaczyć własny produkt.
 */
export function czyPelnyWglad(rola: Rola, podgladKlienta = false): boolean {
  return rola === "admin" && !podgladKlienta;
}
