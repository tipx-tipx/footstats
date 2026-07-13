/**
 * Zapisy do Supabase app_data (service_role) — WYŁĄCZNIE z route handlerów,
 * nigdy z komponentów klienckich (service key nie może wyciekać do przeglądarki).
 */

export async function readAppData(
  url: string,
  key: string,
  name: string,
): Promise<Record<string, unknown>> {
  const res = await fetch(`${url}/rest/v1/app_data?select=payload&key=eq.${name}`, {
    headers: { apikey: key, Authorization: `Bearer ${key}` },
    cache: "no-store",
  });
  const rows: { payload: Record<string, unknown> }[] = res.ok ? await res.json() : [];
  return rows[0]?.payload ?? {};
}

/** Nadpisz WHOLE payload (poprawne tylko dla wartości bez współbieżnych
 * częściowych aktualizacji — np. skalar jak wybrany profil buildera). Dla
 * obiektów mutowanych po kluczu (pomiń/przywróć/...) użyj mergeAppData. */
export async function writeAppData(
  url: string,
  key: string,
  name: string,
  payload: unknown,
): Promise<boolean> {
  const res = await fetch(`${url}/rest/v1/app_data?on_conflict=key`, {
    method: "POST",
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
      Prefer: "resolution=merge-duplicates",
    },
    body: JSON.stringify([{ key: name, payload }]),
  });
  return res.ok;
}

/**
 * Atomowy merge/usunięcie top-level kluczy w app_data.payload (migracja
 * 0003, funkcja SQL merge_app_data) — jedno zapytanie do Postgresa zamiast
 * read-modify-write z klienta, więc dwa równoległe żądania do TEGO SAMEGO
 * klucza (dwie karty przeglądarki, klik + auto-retry) już się nie nadpisują.
 *
 * GRACEFUL FALLBACK: gdy RPC jeszcze nie istnieje (migracja niezaaplikowana
 * na danym projekcie Supabase — PostgREST odpowiada 404), spada do starego
 * read-modify-write. Dzięki temu wdrożenie tego kodu jest bezpieczne
 * niezależnie od tego, czy/kiedy migracja zostanie odpalona.
 */
export async function mergeAppData(
  url: string,
  key: string,
  name: string,
  patch: Record<string, unknown> = {},
  remove: string[] = [],
): Promise<boolean> {
  const rpc = await fetch(`${url}/rest/v1/rpc/merge_app_data`, {
    method: "POST",
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ p_key: name, p_patch: patch, p_remove: remove }),
  });
  if (rpc.ok) return true;
  if (rpc.status !== 404) return false; // realny błąd — nie maskuj fallbackiem

  const current = await readAppData(url, key, name);
  for (const [k, v] of Object.entries(patch)) current[k] = v;
  for (const k of remove) delete current[k];
  return writeAppData(url, key, name, current);
}
