"use client";

import { useRouter } from "next/navigation";

import type { MeczE } from "../../_dane/elementy";
import { WierszA } from "../elementy/mecz";

/** 404: najbliższe mecze z typami – droga dalej zamiast ślepego zaułka */
export function Najblizsze({ najblizsze }: { najblizsze: MeczE[] }) {
  const router = useRouter();
  return (
    <section className="sy-najblizsze el-liga" aria-label="Najbliższe mecze z typami">
      <div className="sy-najblizsze-glowa">
        <b>Najbliższe mecze z typami</b>
        <span>wejdź w mecz albo przejdź do całej listy</span>
      </div>
      {najblizsze.map((m) => (
        <WierszA key={m.id} m={m} wybierz={() => router.push(`/mecze/${m.id}`)} />
      ))}
    </section>
  );
}
