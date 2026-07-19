import { GeneratorKuponu } from "@/components/GeneratorKuponu";
import { KuponyScena } from "@/components/KuponyScena";
import { PageHeader } from "@/components/PageHeader";
import { Reveal } from "@/components/Reveal";
import { TrafioneKupony } from "@/components/TrafioneKupony";
import { getKupony, getLegiPool, getMeta, getTypyWyniki } from "@/lib/data";

export const metadata = { title: "Kupony – FootStats" };

export default async function KuponyPage() {
  const [kupony, meta, legiPool, typyWyniki] = await Promise.all([
    getKupony(),
    getMeta(),
    getLegiPool(),
    getTypyWyniki(),
  ]);

  return (
    <div>
      <PageHeader
        eyebrow="gotowe zestawy"
        title="Wybierz, ile chcesz wygrać"
        lead={
          <>
            Model składa gotowe kupony z typów po pełnej analizie. Ty wybierasz
            tylko cel: im wyższy kurs, tym rzadziej wchodzi całość. Kupon Ci
            nie leży? Pomiń go, a model złoży inny.
          </>
        }
      />

      {kupony.length === 0 ? (
        <Reveal className="mt-8">
          <div className="rounded-(--radius-card) border border-hairline bg-card px-8 py-14 text-center shadow-(--shadow-card)">
            <p className="font-semibold">
              Za mało typów z wartością na sensowny kupon
            </p>
            <p className="mx-auto mt-1.5 max-w-md text-sm leading-relaxed text-muted">
              Kupon wymaga co najmniej dwóch niezależnych typów z dodatnią
              wartością i przyzwoitą pewnością. Model nie skleja typów na siłę.
              Kupony pojawią się, gdy rynek da okazje ({meta.liga} {meta.sezon}
              ).
            </p>
          </div>
        </Reveal>
      ) : (
        <div className="mt-7">
          <KuponyScena kupony={kupony} jestGenerator={legiPool.length > 0} />
        </div>
      )}

      {/* zasady gry — cała dawna ściana tekstu, ale na żądanie */}
      <Reveal className="mt-8">
        <details className="group max-w-3xl">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted transition-colors hover:text-ink [&::-webkit-details-marker]:hidden">
            jak powstają te kupony
            <svg
              aria-hidden
              width="12"
              height="12"
              viewBox="0 0 14 14"
              className="shrink-0 transition-transform group-open:rotate-180"
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
          <div className="mt-3 space-y-2 border-l border-hairline pl-4 text-xs leading-relaxed text-muted">
            <p>
              Każdy typ przechodzi pełną analizę modelu: historia, minuty,
              składy z dwóch źródeł, profil rywala. Do kuponu wchodzą typy o
              najlepszym stosunku pewności do kursu, a szansa całości to
              iloczyn szans typów (z karą, gdy kilka typów gra w jednym meczu).
            </p>
            <p>
              Po publikacji kupon jest zamrożony. Nowy w danym przedziale
              powstaje, gdy poprzedni się rozliczy, gdy ogłoszone składy
              wywrócą któryś typ albo gdy sam go pominiesz. Pominięty kupon i
              tak rozlicza się w tle, żeby model się uczył.
            </p>
          </div>
        </details>
      </Reveal>

      <TrafioneKupony kupony={typyWyniki.kupony_wygrane ?? []} />

      {/* druga ścieżka: własny kupon z tej samej przeanalizowanej puli */}
      {legiPool.length > 0 && (
        <Reveal className="mt-14">
          <section id="generator" aria-label="Zbuduj własny kupon" className="scroll-mt-24">
            <p className="flex items-center gap-2.5 text-xs font-semibold uppercase tracking-widest text-brand">
              <span aria-hidden className="h-px w-6 bg-brand-bright" />
              druga ścieżka
            </p>
            <h2 className="mt-2 text-xl font-bold tracking-tight sm:text-2xl">
              Zbuduj własny kupon
            </h2>
            <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-muted">
              Ta sama przeanalizowana pula, z której model buduje automaty: te
              same bezpieczniki i kary korelacji. Wybierz mecze, ustaw kurs
              docelowy i charakter. Gotowy zestaw możesz poprawiać: usuń typ, a
              model dobierze inny; przypnij typ, a zostanie na pewno.
            </p>
            <div className="mt-4">
              <GeneratorKuponu
                pool={legiPool}
                kary={meta.kary_korelacji}
                wagi={meta.wagi_zaufania}
              />
            </div>
          </section>
        </Reveal>
      )}
    </div>
  );
}
