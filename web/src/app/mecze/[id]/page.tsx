import Link from "next/link";
import { notFound } from "next/navigation";

import { Reveal } from "@/components/Reveal";
import { TopPokrycia } from "@/components/TopPokrycia";
import {
  getMecze,
  getOddsSuperbet,
  getValueBets,
  getZawodnicy,
} from "@/lib/data";
import { fmtMnoznik } from "@/lib/format";
import { topPokrycia } from "@/lib/pokrycie";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const mecz = (await getMecze()).find((m) => m.id === Number(id));
  return {
    title: mecz
      ? `${mecz.gospodarz} – ${mecz.gosc} — FootStats`
      : "Mecz — FootStats",
  };
}

function kiedy(ts: number): string {
  const d = new Date(ts * 1000);
  return new Intl.DateTimeFormat("pl-PL", {
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  }).format(d);
}

export default async function MeczPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const meczId = Number(id);
  const [mecze, zawodnicy, bets, odds] = await Promise.all([
    getMecze(),
    getZawodnicy(),
    getValueBets(),
    getOddsSuperbet(),
  ]);

  const mecz = mecze.find((m) => m.id === meczId);
  if (!mecz) notFound();

  // zawodnicy tego meczu = grający w jednej z dwóch drużyn (mapowanie po nazwie)
  const druzyny = new Set([mecz.gospodarz, mecz.gosc]);
  const gracze = zawodnicy.filter((z) => druzyny.has(z.druzyna));
  const wszystkie = topPokrycia(gracze, meczId, odds);
  const LIMIT = 40;
  const wiersze = wszystkie.slice(0, LIMIT);
  const okazje = bets.filter((b) => b.mecz_id === meczId && !b.sugestia).length;

  return (
    <div>
      <Reveal>
        <Link
          href="/mecze"
          className="inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-ink"
        >
          <span aria-hidden>←</span> Mecze
        </Link>

        <div className="mt-4 rounded-2xl border border-hairline bg-card p-5 shadow-(--shadow-card) sm:p-6">
          <p className="text-xs font-medium uppercase tracking-widest text-faint">
            {kiedy(mecz.kickoff_ts)}
          </p>
          <h1 className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-2xl font-bold sm:text-3xl">
            {mecz.gospodarz}
            <span className="text-base font-medium uppercase tracking-widest text-faint">
              vs
            </span>
            {mecz.gosc}
          </h1>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            {okazje > 0 && (
              <Link
                href={`/?mecz=${mecz.id}`}
                className="inline-flex items-center gap-1 rounded-full bg-brand-wash px-2.5 py-1 font-medium text-brand-deep transition-colors hover:bg-brand-wash/70"
              >
                {okazje === 1 ? "1 okazja modelu" : `${okazje} okazji modelu`} →
              </Link>
            )}
            {mecz.sklady_ogloszone ? (
              <span className="inline-flex items-center rounded-full bg-data-green-wash px-2.5 py-1 font-medium text-brand-deep">
                ✓ składy ogłoszone
              </span>
            ) : (
              <span className="inline-flex items-center rounded-full bg-paper px-2.5 py-1 text-faint">
                składy ~1 h przed
              </span>
            )}
            {mecz.sedzia && (
              <span className="inline-flex items-center gap-1 rounded-full bg-paper px-2.5 py-1 text-muted">
                Sędzia: {mecz.sedzia}
                {Math.abs(mecz.sedzia_mnoznik_fauli - 1) > 0.05 && (
                  <span
                    className={`font-data ml-1 rounded px-1 ${
                      mecz.sedzia_mnoznik_fauli > 1
                        ? "bg-data-red-wash text-data-red"
                        : "bg-data-green-wash text-brand-deep"
                    }`}
                    title="Ile fauli gwiżdże ten sędzia względem średniej ligi"
                  >
                    faule {fmtMnoznik(mecz.sedzia_mnoznik_fauli)}
                  </span>
                )}
              </span>
            )}
          </div>
        </div>
      </Reveal>

      <Reveal className="mt-8">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <span aria-hidden>✅</span> TOP POKRYCIA
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          Zawodnicy z najlepszym pokryciem historycznym (≥ 60%) — ile z{" "}
          <strong>ostatnich 5 rozegranych</strong> meczów pokryło linię 1+, 2+
          lub 3+. Zielony boks = mecz pokrył linię, czerwony = nie. Kursy:
          Superbet (kolejne buki wkrótce).
          {wszystkie.length > LIMIT && (
            <>
              {" "}
              Pokazujemy <strong>top {LIMIT}</strong> z {wszystkie.length}{" "}
              propozycji.
            </>
          )}
        </p>
        <TopPokrycia wiersze={wiersze} />
      </Reveal>
    </div>
  );
}
