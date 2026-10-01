import { czyTelefon } from "@/lib/nowe/telefon";

import { LogowanieAplikacji } from "../projekt/_ui/systemowe/LogowanieAplikacji";

export const metadata = { title: "Logowanie – FootStats" };

/** tylko ścieżki tej strony – `//inna.pl` albo pełny adres nie mogą wyprowadzić poza aplikację */
function bezpiecznyPowrot(next: string | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\") || next.startsWith("/login")) return "/";
  return next;
}

export default async function LoginPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const q = await searchParams;
  const stan = q.stan === "wylogowano" || q.stan === "sesja" ? q.stan : "zwykly";
  return <LogowanieAplikacji telefon={await czyTelefon()} stan={stan} dalej={bezpiecznyPowrot(q.next)} />;
}
