import { NextResponse } from "next/server";

import { druzyna } from "@/app/projekt/_dane/przygotuj";
import { zDanymi } from "@/app/projekt/_dane/zrodlo";
import { getIndeksZawodnikow } from "@/lib/data";
import type { Mecz } from "@/lib/types";
import { pobierzSurowe } from "@/lib/nowe/surowe";

/**
 * Szukaj zawodnika (Ctrl+K) w całej ofercie – `zaw_indeks` z pipeline'u (7B):
 * każdy zawodnik z kursem albo typem, nie tylko ci z listy dnia. Indeks
 * zostaje na serwerze (tysiące wpisów), do przeglądarki idzie najwyżej 8
 * trafień. Za bramką logowania jak cała aplikacja (proxy.ts).
 */
const norm = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l");

export async function GET(req: Request) {
  const q = norm(new URL(req.url).searchParams.get("q") ?? "").trim();
  if (q.length < 3) return NextResponse.json({ zawodnicy: [] });
  const [indeks, surowe] = await Promise.all([getIndeksZawodnikow(), pobierzSurowe()]);
  if (!indeks) return NextResponse.json({ zawodnicy: [] });
  const mecze = new Map((surowe.mecze as Mecz[]).map((m) => [m.id, m]));
  const trafienia = indeks
    .filter((z) => norm(z.n ?? "").includes(q))
    // najpierw ci, u których zapytanie zaczyna słowo (nazwisko), potem reszta
    .sort((a, b) => Number(!norm(a.n).split(/\s+/).some((w) => w.startsWith(q))) - Number(!norm(b.n).split(/\s+/).some((w) => w.startsWith(q))))
    .slice(0, 8);
  const zawodnicy = zDanymi(surowe, () =>
    trafienia.map((z) => {
      const m = mecze.get(z.m);
      return { id: z.id, nazwa: z.n, druzyna: z.d ? druzyna(z.d) : null, opis: m ? `${m.gospodarz} – ${m.gosc}` : "" };
    }),
  );
  return NextResponse.json({ zawodnicy }, { headers: { "Cache-Control": "private, max-age=300" } });
}
