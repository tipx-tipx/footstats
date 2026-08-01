/**
 * Autoryzacja FootStats – dwa poziomy dostępu, hasło zamiast kont.
 *
 * Schemat: hasło z env → po poprawnym logowaniu ciasteczko HttpOnly
 * `fs_sesja` o wartości "<wygasa_ts>.<rola>.<podpis HMAC-SHA256>".
 * Podpis liczony z AUTH_SECRET z OBU pól naraz, więc podmiana roli w
 * ciasteczku unieważnia podpis – nie da się awansować na admina.
 * Serwer nie musi niczego pamiętać (bez bazy, bez sesji).
 *
 * Role:
 *   admin  (APP_PASSWORD)    – pełny wgląd: kuchnia modelu, diagnostyka,
 *                              typy liczone „na próbę", sprawdziany.
 *   klient (KLIENT_PASSWORD) – sam produkt: werdykt, wyniki, dowody.
 *                              Nie widzi wewnętrznych narzędzi.
 * KLIENT_PASSWORD jest opcjonalne – bez niego działa jak dotąd, jedno hasło.
 *
 * Web Crypto (crypto.subtle) – działa i w proxy (edge), i w route handlerach.
 * Brak APP_PASSWORD w env = tryb otwarty (lokalny development, rola admin).
 */

export const SESSION_COOKIE = "fs_sesja";
export const SESSION_DAYS = 30;

export type Rola = "admin" | "klient";

const ROLE: readonly Rola[] = ["admin", "klient"];

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

/** Porównanie stałoczasowe dwóch podpisów (bez wycieku przez czas). */
function podpisyRowne(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** Zbuduj wartość ciasteczka sesji ważnego SESSION_DAYS dni. */
export async function createSessionToken(
  secret: string,
  rola: Rola = "admin",
): Promise<string> {
  const expires = Date.now() + SESSION_DAYS * 24 * 60 * 60 * 1000;
  return `${expires}.${rola}.${await hmac(secret, `${expires}.${rola}`)}`;
}

/**
 * Sprawdź ciasteczko sesji – zwraca ROLĘ albo null.
 *
 * Rozumie dwa formaty: nowy "<ts>.<rola>.<podpis>" i stary "<ts>.<podpis>"
 * (sprzed podziału na role). Stary jest ważny i znaczy `admin`, żeby wdrożenie
 * nie wylogowało nikogo w środku pracy – wygaśnie sam w ciągu 30 dni.
 */
export async function verifySessionRole(
  token: string | undefined,
  secret: string,
): Promise<Rola | null> {
  if (!token) return null;
  const czesci = token.split(".");
  if (czesci.length < 2 || czesci.length > 3) return null;
  const expires = czesci[0];
  if (!/^\d+$/.test(expires) || Number(expires) < Date.now()) return null;

  if (czesci.length === 3) {
    const [, rola, sig] = czesci;
    if (!ROLE.includes(rola as Rola)) return null;
    // podpis liczony z OBU pól – sama podmiana roli go unieważnia
    const oczekiwany = await hmac(secret, `${expires}.${rola}`);
    return podpisyRowne(sig, oczekiwany) ? (rola as Rola) : null;
  }
  // format sprzed ról
  const oczekiwany = await hmac(secret, expires);
  return podpisyRowne(czesci[1], oczekiwany) ? "admin" : null;
}

/** Czy ciasteczko w ogóle uprawnia do wejścia (bramka w proxy.ts). */
export async function verifySessionToken(
  token: string | undefined,
  secret: string,
): Promise<boolean> {
  return (await verifySessionRole(token, secret)) !== null;
}
