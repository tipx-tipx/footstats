/**
 * Autoryzacja FootStats — narzędzie osobiste, jeden użytkownik, jedno hasło.
 *
 * Schemat: hasło (APP_PASSWORD w env) → po poprawnym logowaniu ciasteczko
 * HttpOnly `fs_sesja` o wartości "<wygasa_ts>.<podpis HMAC-SHA256>".
 * Podpis liczony z AUTH_SECRET, więc ciasteczka nie da się podrobić,
 * a serwer nie musi niczego pamiętać (bez bazy, bez sesji).
 *
 * Web Crypto (crypto.subtle) — działa i w proxy (edge), i w route handlerach.
 * Brak APP_PASSWORD w env = tryb otwarty (lokalny development).
 */

export const SESSION_COOKIE = "fs_sesja";
export const SESSION_DAYS = 30;

const enc = new TextEncoder();

async function hmac(secret: string, payload: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(payload));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Zbuduj wartość ciasteczka sesji ważnego SESSION_DAYS dni. */
export async function createSessionToken(secret: string): Promise<string> {
  const expires = Date.now() + SESSION_DAYS * 24 * 60 * 60 * 1000;
  return `${expires}.${await hmac(secret, String(expires))}`;
}

/** Sprawdź ciasteczko sesji: podpis musi się zgadzać, a termin nie minąć. */
export async function verifySessionToken(
  token: string | undefined,
  secret: string,
): Promise<boolean> {
  if (!token) return false;
  const dot = token.indexOf(".");
  if (dot <= 0) return false;
  const expires = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  if (!/^\d+$/.test(expires) || Number(expires) < Date.now()) return false;
  const expected = await hmac(secret, expires);
  // porównanie stałoczasowe
  if (sig.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < sig.length; i++) diff |= sig.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}
