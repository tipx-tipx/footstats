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
  return new Intl.DateTimeFormat("pl-PL", {
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  }).format(new Date(ts * 1000));
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
  const wiersze = topPokrycia(gracze, meczId, odds);
  const okazje = bets.filter((b) => b.mecz_id === meczId && !b.sugestia).length;

  return (
    <div>
      <Reveal>
        <Link
          href="/mecze"
          className="inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-ink"
        >
          <span aria-hidden>←</span> Wszystkie mecze
        </Link>

        {/* nagłówek meczu */}
        <div className="mt-4 rounded-2xl border border-hairline bg-card px-5 py-5 shadow-(--shadow-card) sm:px-8 sm:py-7">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-medium uppercase tracking-widest text-faint">
              {kiedy(mecz.kickoff_ts)}
            </p>
            {mecz.sklady_ogloszone ? (
              <span className="inline-flex items-center rounded-full bg-data-green-wash px-2.5 py-1 text-[11px] font-medium text-brand-deep">
                ✓ składy ogłoszone
              </span>
            ) : (
              <span className="inline-flex items-center rounded-full bg-paper px-2.5 py-1 text-[11px] text-faint">
                składy ~1 h przed
              </span>
            )}
          </div>

          <div className="mt-5 grid grid-cols-[1fr_auto_1fr] items-center gap-3 sm:gap-8">
            <div className="text-right">
              <p className="text-xl font-bold leading-tight sm:text-3xl">
                {mecz.gospodarz}
              </p>
              <p className="mt-1 text-[10px] uppercase tracking-widest text-faint">
                gospodarz
              </p>
            </div>
            <span className="font-data flex h-9 w-9 items-center justify-center rounded-full bg-paper text-xs font-semibold text-muted sm:h-11 sm:w-11 sm:text-sm">
              vs
            </span>
            <div>
              <p className="text-xl font-bold leading-tight sm:text-3xl">
                {mecz.gosc}
              </p>
              <p className="mt-1 text-[10px] uppercase tracking-widest text-faint">
                gość
              </p>
            </div>
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-center gap-2 border-t border-hairline pt-4 text-xs">
            {okazje > 0 && (
              <Link
                href={`/?mecz=${mecz.id}`}
                className="inline-flex items-center gap-1 rounded-full bg-brand-wash px-3 py-1.5 font-medium text-brand-deep transition-colors hover:bg-brand-wash/70"
              >
                {okazje === 1 ? "1 okazja modelu" : `${okazje} okazji modelu`}{" "}
                <span aria-hidden>→</span>
              </Link>
            )}
            {mecz.sedzia && (
              <span className="inline-flex items-center gap-1 rounded-full bg-paper px-3 py-1.5 text-muted">
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
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <span aria-hidden>✅</span> TOP POKRYCIA
          </h2>
        </div>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          Pokrycie z <strong>ostatnich 5 startów</strong>. Na mecz reprezentacji{" "}
          <strong>preferujemy starty w kadrze</strong> — a gdy zawodnik gra w niej
          za rzadko, liczymy z klubu (oznaczone „forma klubowa”, niżej). Kolumna{" "}
          1+/2+/3+ to pokrycie linii z kursem Superbet. Najedź na boks: rywal,
          minuty, data.
        </p>
        <TopPokrycia
          wiersze={wiersze}
          druzyny={[mecz.gospodarz, mecz.gosc]}
        />
      </Reveal>
    </div>
  );
}
