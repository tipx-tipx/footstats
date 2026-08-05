import Link from "next/link";
import { notFound } from "next/navigation";

import { CzegoNieTypujemy } from "@/components/CzegoNieTypujemy";
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
import { etykietaPowodu } from "@/lib/odrzucenia";
import { fmtKurs, fmtMnoznik, opisZakladu } from "@/lib/format";
import { kluczWerdyktu, topPokrycia, type WerdyktRynku } from "@/lib/pokrycie";

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

/**
 * „1 okazja", „2 okazje", „5 okazji" – TRZY formy, nie dwie.
 *
 * Było `okazje === 1 ? "1 okazja" : "N okazji"`, więc banda meta pokazywała
 * „2 OKAZJI MODELU" (przegląd sprzedażowy, szlif). Ta sama funkcja stoi już
 * w Hero.tsx — tam odmienia poprawnie; tutaj był drugi, uproszczony wariant.
 */
function odmienOkazje(n: number): string {
  if (n === 1) return "1 okazja";
  const r10 = n % 10;
  const r100 = n % 100;
  const kilka = r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14);
  return `${n} ${kilka ? "okazje" : "okazji"}`;
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
  const ligowy = meta.tryb === "liga";
  const wiersze = topPokrycia(gracze, meczId, odds, ligowy);
  const betyMeczu = bets.filter((b) => b.mecz_id === meczId && !b.sugestia);
  const okazje = betyMeczu.length;

  /**
   * WERDYKT MODELU DLA KAŻDEGO WIERSZA TABELI POKRYĆ.
   *
   * Liczony na SERWERZE, bo obie składowe (lista typów, rejestr odrzuceń) i tak
   * są tu już wczytane, a `TopPokrycia` jest komponentem klienta — przesyłanie
   * do przeglądarki całych `value_bets` i `odrzucenia` tylko po to, żeby
   * dopasować kilkadziesiąt wierszy, byłoby kilkoma megabajtami za rozpoznanie,
   * które da się zrobić raz (patrz nota o okrojDlaKlienta w AGENTS.md).
   *
   * Kolejność ma znaczenie: NAJPIERW typy, potem odrzucenia. Ten sam zawodnik
   * i rynek potrafi mieć jedno i drugie — typ na linii 1,5 i odrzucenie na 2,5.
   * „Typujemy" jest wtedy prawdziwsze niż „odrzucone", bo na liście coś stoi.
   */
  const werdykty = new Map<string, WerdyktRynku>();
  for (const o of odrzucenia) {
    if (o.podmiot_typ === "druzyna") continue; // tabela jest o zawodnikach
    werdykty.set(kluczWerdyktu(o.podmiot, o.rynek_kod), {
      stan: "odrzucony",
      opis: etykietaPowodu(o.powod),
    });
  }
  for (const b of betyMeczu) {
    if (b.podmiot_typ === "druzyna") continue;
    werdykty.set(kluczWerdyktu(b.podmiot, b.rynek_kod), {
      stan: "typujemy",
      // kurs bywa pusty tylko przy sugestiach STS (odfiltrowane wyżej), ale
      // typ bez ceny ma pokazać sam zakład zamiast „@ null"
      opis:
        b.kurs != null
          ? `${opisZakladu(b, true)} @ ${fmtKurs(b.kurs)}`
          : opisZakladu(b, true),
    });
  }

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
          {/* siatka boiska wyśrodkowana POD nazwami (własna maska – domyślna
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
                {odmienOkazje(okazje)} modelu
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
            kalibracja={meta.kalibracja_kuponow}
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
          {/* mecz bez oferty zawodniczej u Superbetu: nie obiecuj kursów,
              których w tabeli nie będzie (patrz nota w TopPokrycia) */}
          {wiersze.some((w) => w.maKurs)
            ? "Kto ostatnio regularnie robił to, na co bukmacher daje kurs."
            : "Kto ostatnio regularnie zbierał te statystyki."}{" "}
          {ligowy
            ? "Liczymy z 5 ostatnich meczów, w których zawodnik zaczynał."
            : "Na mecz reprezentacji liczymy starty w kadrze, a gdy zawodnik gra w niej za rzadko, bierzemy klub."}{" "}
          Najedź na kwadrat, żeby zobaczyć rywala i minuty.
        </p>
        <TopPokrycia
          wiersze={wiersze}
          druzyny={[mecz.gospodarz, mecz.gosc]}
          ligowy={ligowy}
          zawodnikow={gracze.length}
          propsySuperbet={mecz.propsy_superbet}
          werdykty={werdykty}
        />
      </Reveal>

      {odrzucenia.length > 0 && (
        <Reveal className="mt-10">
          {/* sito modelu: banda z odczytem, nie karta – to przypis, nie sekcja.
              Blok jest wspolny z Druzynami (CzegoNieTypujemy) — dwie kopie tej
              samej sekcji rozjechalyby sie przy pierwszej poprawce tekstu. */}
          <CzegoNieTypujemy
            odrzucenia={odrzucenia}
            tytul="Czego nie typujemy w tym meczu i dlaczego"
          />
        </Reveal>
      )}
    </div>
  );
}
