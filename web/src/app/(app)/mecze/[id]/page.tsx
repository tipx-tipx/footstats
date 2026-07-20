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
      ? `${mecz.gospodarz} – ${mecz.gosc} · FootStats`
      : "Mecz · FootStats",
  };
}

/** Separator odczytów w bandzie meta. */
function Kreska() {
  return <span aria-hidden className="h-3 w-px bg-hairline-strong" />;
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

        {/* nagłówek meczu = tablica przed transmisją: typografia i linie,
            bez karty w karcie (siatka boiska leży w tle samej sekcji) */}
        <div className="relative mt-5">
          {/* siatka boiska wyśrodkowana POD nazwami (własna maska — domyślna
              z .pitch-grid wygasa od lewego górnego rogu i zostawiała plamę
              kratki w rogu, wyglądającą przypadkowo) */}
          <div
            aria-hidden
            className="pitch-grid pointer-events-none absolute -inset-x-10 -top-6 bottom-8 -z-10"
            style={{
              maskImage:
                "radial-gradient(58% 100% at 50% 45%, black 15%, transparent 72%)",
              WebkitMaskImage:
                "radial-gradient(58% 100% at 50% 45%, black 15%, transparent 72%)",
            }}
          />

          <p className="flex items-center gap-2.5 text-xs font-semibold uppercase tracking-widest text-brand">
            <span aria-hidden className="h-px w-6 bg-brand-bright" />
            {kiedy(mecz.kickoff_ts)}
          </p>

          <div className="mt-5 grid grid-cols-[1fr_auto_1fr] items-center gap-4 sm:gap-10">
            <div className="text-right">
              <p className="font-display text-2xl font-bold leading-tight tracking-tight sm:text-4xl">
                {mecz.gospodarz}
              </p>
              <p className="mt-1.5 text-[10px] uppercase tracking-widest text-faint">
                gospodarz
              </p>
            </div>
            {/* „vs” jako kreska rozdzielająca, nie pastylka z cieniem */}
            <span className="flex flex-col items-center gap-1.5">
              <span aria-hidden className="h-4 w-px bg-hairline-strong" />
              <span className="font-data text-[10px] uppercase tracking-widest text-faint">
                vs
              </span>
              <span aria-hidden className="h-4 w-px bg-hairline-strong" />
            </span>
            <div>
              <p className="font-display text-2xl font-bold leading-tight tracking-tight sm:text-4xl">
                {mecz.gosc}
              </p>
              <p className="mt-1.5 text-[10px] uppercase tracking-widest text-faint">
                gość
              </p>
            </div>
          </div>

          {/* banda meta: odczyty rozdzielone pionowymi kreskami */}
          <div className="mt-7 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 border-y border-hairline py-2.5 text-xs">
            {okazje > 0 && (
              <Link
                href={`/?mecz=${mecz.id}`}
                className="font-display inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-brand transition-colors hover:text-brand-strong"
              >
                {okazje === 1 ? "1 okazja modelu" : `${okazje} okazji modelu`}
                <span aria-hidden>→</span>
              </Link>
            )}
            {mecz.sedzia && (
              <>
                {okazje > 0 && <Kreska />}
                <span className="text-muted">
                  Sędzia: <span className="text-ink-soft">{mecz.sedzia}</span>
                  {Math.abs(mecz.sedzia_mnoznik_fauli - 1) > 0.05 && (
                    <span
                      className={`font-data ml-1.5 font-semibold ${
                        mecz.sedzia_mnoznik_fauli > 1
                          ? "text-data-red-ink"
                          : "text-data-green-ink"
                      }`}
                      title="Ile fauli gwiżdże ten sędzia względem średniej ligi"
                    >
                      faule {fmtMnoznik(mecz.sedzia_mnoznik_fauli)}
                    </span>
                  )}
                </span>
              </>
            )}
            {(okazje > 0 || mecz.sedzia) && <Kreska />}
            {mecz.sklady_ogloszone ? (
              <span className="flex items-center gap-1.5 text-data-green-ink">
                <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-data-green" />
                składy ogłoszone
              </span>
            ) : (
              <span className="text-faint">składy ~1 h przed</span>
            )}
          </div>
        </div>
      </Reveal>

      {legiMeczu.length > 0 && (
        <Reveal className="mt-10">
          <h2 className="flex items-center gap-2.5 font-body text-xs font-semibold uppercase tracking-widest text-brand">
            <span aria-hidden className="h-px w-6 bg-brand-bright" />
            Kupon na ten mecz
          </h2>
          <p className="mt-2 mb-4 max-w-3xl text-sm leading-relaxed text-muted">
            Złóż AKO z najlepszych typów tego meczu (do 4 wydarzeń): ustaw kurs
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

      <Reveal className="mt-10">
        <h2 className="flex items-center gap-2.5 font-body text-xs font-semibold uppercase tracking-widest text-brand">
          <span aria-hidden className="h-px w-6 bg-brand-bright" />
          TOP POKRYCIA
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
          Kto ostatnio regularnie robił to, na co bukmacher daje kurs. Na mecz
          reprezentacji liczymy starty w kadrze, a gdy zawodnik gra w niej za
          rzadko, bierzemy klub. Najedź na kwadrat, żeby zobaczyć rywala i minuty.
        </p>
        <TopPokrycia
          wiersze={wiersze}
          druzyny={[mecz.gospodarz, mecz.gosc]}
        />
      </Reveal>

      {odrzucenia.length > 0 && (
        <Reveal className="mt-10">
          {/* sito modelu: banda z odczytem, nie karta — to przypis, nie sekcja */}
          <details className="group border-y border-hairline">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 py-3.5 text-sm font-semibold [&::-webkit-details-marker]:hidden">
              <span>
                Czego nie typujemy w tym meczu i dlaczego
                <span className="font-data ml-2 text-xs font-normal text-faint">
                  {odrzucenia.length} sprawdzonych bez typu
                </span>
              </span>
              <svg
                aria-hidden
                width="14"
                height="14"
                viewBox="0 0 14 14"
                className="shrink-0 text-faint transition-transform group-open:rotate-180"
              >
                <path
                  d="M3 5.5 L7 9.5 L11 5.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </summary>
            <div className="space-y-4 border-t border-hairline py-4">
              <p className="text-xs leading-relaxed text-muted">
                Model sprawdza każdego zawodnika i każdy rynek. Gdy typ się nie
                pojawia, to nie przeoczenie: poniżej dokładny powód dla każdej
                sprawdzonej pary.
              </p>
              {/* liczba i powód niosą treść; wyliczanka 200 nazwisk była
                  ścianą tekstu, więc zostaje kilka przykładów na zachętę */}
              {grupyOdrzucen(odrzucenia).map(([powod, wpisy]) => (
                <div key={powod}>
                  <div className="flex items-baseline justify-between gap-4 border-b border-hairline pb-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">
                      {POWOD_LABEL[powod] ?? powod}
                    </p>
                    <span className="font-data shrink-0 text-sm font-semibold text-ink-soft">
                      {wpisy.length}
                    </span>
                  </div>
                  <p className="mt-1.5 text-xs leading-relaxed text-muted">
                    {wpisy[0].szczegol}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-faint">
                    {wpisy
                      .slice(0, 6)
                      .map((w) => `${w.podmiot} (${w.rynek.toLowerCase()})`)
                      .join(", ")}
                    {wpisy.length > 6 && ` i ${wpisy.length - 6} więcej`}
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
  kwarantanna_rynku: "Rynek chwilowo wstrzymany (trafiał poniżej deklaracji)",
  stare_dane: "Zawodnik dawno nie grał, czekamy na świeże mecze",
  za_stara_historia: "Dane o zawodniku są nieaktualne",
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
