import { headers } from "next/headers";

/** zgadnij telefon po przeglądarce – pierwszy render od razu w dobrym układzie (przeglądarka potem doprecyzuje szerokością) */
export async function czyTelefon(): Promise<boolean> {
  const ua = (await headers()).get("user-agent") ?? "";
  return /Mobi|Android|iPhone|iPod/i.test(ua);
}
