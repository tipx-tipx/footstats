import { Hero } from "@/components/Hero";
import { ValueBoard } from "@/components/ValueBoard";
import {
  getMecze,
  getMeta,
  getOdrzucenia,
  getStsValue,
  getValueBets,
  getZawodnicy,
} from "@/lib/data";

/** Forma słowa "typ" do liczby: 1 typ, 3 typy, 8 typów, 22 typy. */
function formaTypow(n: number): string {
  if (n === 1) return "typ";
  const r10 = n % 10;
  const r100 = n % 100;
  return r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14) ? "typy" : "typów";
}

export default async function OkazjePage({
  searchParams,
}: {
  searchParams: Promise<{ mecz?: string; rodzaj?: string }>;
}) {
  const { mecz, rodzaj } = await searchParams;
  const [bets, zawodnicy, meta, mecze, odrzucenia, stsValue] = await Promise.all([
    getValueBets(),
    getZawodnicy(),
    getMeta(),
    getMecze(),
    getOdrzucenia(),
    getStsValue(),
  ]);

  // dowód selekcji do paska "sito modelu": rejestr odrzuceń liczymy tylko
  // dla meczów, które faktycznie są jeszcze przed nami (jak lista niżej)
  const meczeIds = new Set(mecze.map((m) => m.id));
  const odrzucone = odrzucenia.filter((o) => meczeIds.has(o.mecz_id)).length;
  const sprawdzone = odrzucone + bets.length;

  const okazje = bets.filter((b) => !b.sugestia);
  const sugestie = bets.filter((b) => b.sugestia);
  // żywy podgląd w hero: do 4 najlepszych pozycji rankingu silnika
  // (kolejność wejściowa = ranking), sugestie tylko gdy brak innych
  const spotlight = (okazje.length > 0 ? okazje : sugestie).slice(0, 4);
  const aktualizacja = new Intl.DateTimeFormat("pl-PL", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  }).format(new Date(meta.wygenerowano_ts * 1000));

  return (
    <>
      <Hero
        liga={meta.liga}
        sezon={meta.sezon}
        aktualizacja={aktualizacja}
        liczbaOkazji={bets.filter((b) => !b.sugestia).length}
        spotlightBets={spotlight}
        tickerBets={bets.filter((b) => !b.sugestia).slice(0, 14)}
      />

      {meta.tryb === "demo" ? (
        <div className="mb-6 flex max-w-3xl flex-wrap items-baseline gap-x-3 gap-y-1.5">
          <span className="font-display flex shrink-0 items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-data-amber-ink">
            <span aria-hidden className="h-px w-5 bg-data-amber" />
            tryb pokazowy
          </span>
          <p className="text-xs leading-relaxed text-muted">
            Statystyki zawodników są prawdziwe ({meta.liga} {meta.sezon}), ale
            kursy są przykładowe, bo trwa przerwa między sezonami.
          </p>
        </div>
      ) : meta.tryb === "ms2026" ? (
        <div
          className="mb-6 flex max-w-3xl flex-wrap items-baseline gap-x-3 gap-y-1.5"
          title={
            "Sito odrzuca typy z małą liczbą danych, chwiejną predykcją albo kursem bez przewagi. Pełną listę odrzuceń znajdziesz na stronie każdego meczu, w sekcji „Czego nie typujemy”"
          }
        >
          <span className="font-display flex shrink-0 items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-brand">
            <span aria-hidden className="h-px w-5 bg-brand-bright" />
            sito modelu
          </span>
          <p className="text-xs leading-relaxed text-muted">
            {odrzucone > 0 ? (
              <>
                Model sprawdził{" "}
                <strong className="font-data font-semibold text-ink">
                  {sprawdzone}
                </strong>{" "}
                {formaTypow(sprawdzone)} do najbliższych meczów i{" "}
                <strong className="font-data font-semibold text-ink">
                  {odrzucone}
                </strong>{" "}
                z nich odrzucił.{" "}
                {bets.length > 0
                  ? "Zostaje tylko to, gdzie masz realną przewagę."
                  : "W tej chwili żaden kurs nie daje realnej przewagi."}
              </>
            ) : (
              <>
                Okazji jest mało celowo: model odrzuca każdy typ, gdzie kurs
                nie daje realnej przewagi.
              </>
            )}
          </p>
        </div>
      ) : null}

      <div id="okazje" className="scroll-mt-24">
      <ValueBoard
        key={rodzaj ?? "domyslny"}
        bets={bets}
        stsAlerty={stsValue.alerty}
        zawodnicy={zawodnicy}
        initialMatchId={mecz ? Number(mecz) : undefined}
        initialRodzaj={
          rodzaj === "okazje" ||
          rodzaj === "pewniaki" ||
          rodzaj === "value" ||
          rodzaj === "wszystko"
            ? rodzaj
            : undefined
        }
      />
      </div>
    </>
  );
}
