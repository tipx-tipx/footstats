import Link from "next/link";
import { notFound } from "next/navigation";

import { GeneratorKuponu } from "@/components/GeneratorKuponu";
import { Reveal } from "@/components/Reveal";
import { TopPokrycia } from "@/components/TopPokrycia";
import {
  getLegiPool,
  getMecze,
  getMeta,
  getOddsSuperbet,
  getOdrzucenia,
  getValueBets,
  getZawodnicy,
} from "@/lib/data";
import type { Odrzucenie } from "@/lib/types";
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
  const [mecze, zawodnicy, bets, odds, legiPool, meta, odrzucenia] =
    await Promise.all([
      getMecze(),
      getZawodnicy(),
      getValueBets(),
      getOddsSuperbet(),
      getLegiPool(),
      getMeta(),
      getOdrzucenia(Number(id)),
    ]);

  const mecz = mecze.find((m) => m.id === meczId);
  if (!mecz) notFound();

  const legiMeczu = legiPool.filter((l) => l.mecz_id === meczId);

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

      {legiMeczu.length > 0 && (
        <Reveal className="mt-8">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <span aria-hidden>🧩</span> Kupon na ten mecz
          </h2>
          <p className="mt-1 mb-3 max-w-3xl text-sm text-muted">
            Złóż AKO z najlepszych legów tego meczu (do 4 wydarzeń) — ustaw kurs
            docelowy i charakter. Ta sama pula i bezpieczniki co kupony automatyczne.
          </p>
          <GeneratorKuponu
            pool={legiPool}
            kary={meta.kary_korelacji}
            wagi={meta.wagi_zaufania}
            meczId={meczId}
          />
        </Reveal>
      )}

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

      {odrzucenia.length > 0 && (
        <Reveal className="mt-8">
          <details className="rounded-(--radius-card) border border-hairline bg-paper/40">
            <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold [&::-webkit-details-marker]:hidden">
              🔍 Czego nie typujemy w tym meczu — i dlaczego
              <span className="ml-2 text-xs font-normal text-faint">
                ({odrzucenia.length} sprawdzonych bez typu)
              </span>
            </summary>
            <div className="space-y-4 border-t border-hairline p-4">
              <p className="text-xs leading-relaxed text-muted">
                Model sprawdza każdego zawodnika i każdy rynek. Gdy typ się nie
                pojawia, to nie przeoczenie — poniżej dokładny powód dla każdej
                sprawdzonej pary.
              </p>
              {grupyOdrzucen(odrzucenia).map(([powod, wpisy]) => (
                <div key={powod}>
                  <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-faint">
                    {POWOD_LABEL[powod] ?? powod}
                    <span className="ml-1.5 normal-case">
                      · {wpisy.length} — {wpisy[0].szczegol}
                    </span>
                  </p>
                  <p className="text-xs leading-relaxed text-muted">
                    {wpisy
                      .slice(0, 40)
                      .map((w) => `${w.podmiot} (${w.rynek.toLowerCase()})`)
                      .join(", ")}
                    {wpisy.length > 40 && ` … i ${wpisy.length - 40} więcej`}
                  </p>
                </div>
              ))}
            </div>
          </details>
        </Reveal>
      )}
    </div>
  );
}

const POWOD_LABEL: Record<string, string> = {
  tylko_w_puli: "Dostępne w generatorze kuponów",
  brak_kursu: "Superbet nie kwotuje tego rynku",
  za_malo_zdarzen: "Model oczekuje za mało zdarzeń",
  za_malo_historii: "Za mało meczów w historii",
  krotka_historia: "Za krótka historia",
  chwiejna_predykcja: "Model sam nie jest pewny swojej liczby",
  rozjazd_z_rynkiem: "Model za daleko od kursu bukmachera",
  kurs_lub_szansa_poza_widelkami: "Kurs i szansa nie składają się w grywalny typ",
};

/** Grupuj wpisy po powodzie, w kolejności z POWOD_LABEL (reszta na końcu). */
function grupyOdrzucen(wpisy: Odrzucenie[]): [string, Odrzucenie[]][] {
  const m = new Map<string, Odrzucenie[]>();
  for (const w of wpisy) {
    const g = m.get(w.powod) ?? [];
    g.push(w);
    m.set(w.powod, g);
  }
  const kolejnosc = Object.keys(POWOD_LABEL);
  return [...m.entries()].sort(
    (a, b) =>
      (kolejnosc.indexOf(a[0]) + 99) % 99 - (kolejnosc.indexOf(b[0]) + 99) % 99,
  );
}
