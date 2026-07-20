"use client";

import { useMemo, useState } from "react";

import { BetCard } from "./BetCard";
import { FilterDropdown } from "./FilterDropdown";
import { Reveal } from "./Reveal";
import type { DruzynaForma, ValueBet, Zawodnik } from "@/lib/types";

/**
 * Tablica typów drużynowych — projektowana pod SKALĘ sezonu (kilkadziesiąt
 * meczów dziennie, kilka dni naprzód): najmocniejsze typy najbliższej doby
 * na górze, reszta pogrupowana po dniach ze sticky nagłówkami (jak
 * terminarz), filtry rynku i rozgrywek. Karty są zwinięte do wiersza —
 * głębia (forma drużyny, czynniki, możliwe wyniki) na klik.
 */

function kluczDnia(ts: number): string {
  return new Intl.DateTimeFormat("en-CA", {
    dateStyle: "short",
    timeZone: "Europe/Warsaw",
  }).format(new Date(ts * 1000));
}

function etykietaDnia(ts: number, teraz: number): { glowna: string; data: string } {
  const pelna = new Intl.DateTimeFormat("pl-PL", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "Europe/Warsaw",
  }).format(new Date(ts * 1000));
  if (kluczDnia(ts) === kluczDnia(teraz)) return { glowna: "dziś", data: pelna };
  if (kluczDnia(ts) === kluczDnia(teraz + 86400))
    return { glowna: "jutro", data: pelna };
  const [dow, ...reszta] = pelna.split(" ");
  return { glowna: dow, data: reszta.join(" ") };
}

function odmienTypy(n: number): string {
  if (n === 1) return "1 typ";
  const r10 = n % 10;
  const r100 = n % 100;
  const kilka = r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14);
  return `${n} ${kilka ? "typy" : "typów"}`;
}

const PROG_SEKCJI_TOP = 6; // poniżej tylu typów sekcja "najmocniejsze" to szum

export function DruzynyTablica({
  bets,
  forma,
  ligaByMecz,
  teraz,
}: {
  /** typy drużynowe w kolejności rankingu silnika (najlepsze pierwsze) */
  bets: ValueBet[];
  forma: DruzynaForma[];
  /** mecz_id -> nazwa rozgrywek (z matches.json) */
  ligaByMecz: Record<number, string>;
  /** timestamp serwera (s) — spójne "dziś/jutro" bez zegara klienta */
  teraz: number;
}) {
  const [rynek, setRynek] = useState("wszystkie");
  const [liga, setLiga] = useState("wszystkie");

  const formaById = useMemo(
    () => new Map(forma.map((f) => [f.id, f])),
    [forma],
  );

  const rynki = useMemo(
    () => [...new Set(bets.map((b) => b.rynek))].sort(),
    [bets],
  );
  const ligi = useMemo(
    () =>
      [...new Set(bets.map((b) => ligaByMecz[b.mecz_id]).filter(Boolean))].sort(),
    [bets, ligaByMecz],
  );

  const widoczne = useMemo(
    () =>
      bets.filter(
        (b) =>
          (rynek === "wszystkie" || b.rynek === rynek) &&
          (liga === "wszystkie" || ligaByMecz[b.mecz_id] === liga),
      ),
    [bets, rynek, liga, ligaByMecz],
  );

  // najmocniejsze z najbliższej doby (ranking silnika, nie sama szansa)
  const topIds = useMemo(() => {
    if (widoczne.length < PROG_SEKCJI_TOP) return new Set<number>();
    return new Set(
      widoczne
        .filter((b) => b.kickoff_ts - teraz < 24 * 3600)
        .slice(0, 3)
        .map((b) => b.id),
    );
  }, [widoczne, teraz]);
  const top = widoczne.filter((b) => topIds.has(b.id));
  const reszta = widoczne.filter((b) => !topIds.has(b.id));

  // pełna lista chronologicznie: dni, w dniu wg rankingu silnika
  const dni = useMemo(() => {
    const m = new Map<string, ValueBet[]>();
    for (const b of [...reszta].sort((a, z) => a.kickoff_ts - z.kickoff_ts)) {
      const k = kluczDnia(b.kickoff_ts);
      (m.get(k) ?? m.set(k, []).get(k)!).push(b);
    }
    for (const lista of m.values()) {
      const rankiem = new Map(reszta.map((b, i) => [b.id, i]));
      lista.sort((a, z) => (rankiem.get(a.id) ?? 0) - (rankiem.get(z.id) ?? 0));
    }
    return [...m.entries()];
  }, [reszta]);

  const meczeN = new Set(widoczne.map((b) => b.mecz_id)).size;
  const ligiN = new Set(
    widoczne.map((b) => ligaByMecz[b.mecz_id]).filter(Boolean),
  ).size;

  const kartaDla = (bet: ValueBet, rank: number) => (
    <BetCard
      bet={bet}
      rank={rank}
      zawodnik={
        // BetCard czyta z tego obiektu wyłącznie `forma` — kształt
        // DruzynaForma celowo pokrywa potrzebne pola
        formaById.get(bet.podmiot_id) as unknown as Zawodnik | undefined
      }
    />
  );

  return (
    <div>
      {/* odczyty + filtry w jednej bandzie: żywy stan tablicy, nie dekoracja */}
      <div className="mt-6 flex flex-wrap items-center justify-between gap-x-5 gap-y-2.5 border-y border-hairline py-3">
        <p className="font-data text-xs text-muted">
          <span className="font-semibold text-ink">{odmienTypy(widoczne.length)}</span>
          {" · "}
          {meczeN} {meczeN === 1 ? "mecz" : meczeN < 5 ? "mecze" : "meczów"}
          {ligiN > 0 && (
            <>
              {" · "}
              {ligiN} {ligiN === 1 ? "rozgrywki" : "rozgrywek"}
            </>
          )}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          {rynki.length > 1 && (
            <FilterDropdown
              label="Rynek"
              value={rynek}
              options={[
                { value: "wszystkie", label: "Wszystkie rynki" },
                ...rynki.map((r) => ({ value: r, label: r })),
              ]}
              onChange={setRynek}
            />
          )}
          {ligi.length > 1 && (
            <FilterDropdown
              label="Rozgrywki"
              value={liga}
              options={[
                { value: "wszystkie", label: "Wszystkie rozgrywki" },
                ...ligi.map((l) => ({ value: l, label: l })),
              ]}
              onChange={setLiga}
            />
          )}
        </div>
      </div>

      {widoczne.length === 0 ? (
        <p className="mt-8 text-sm text-muted">
          Brak typów dla tych filtrów. Zdejmij filtr, żeby zobaczyć całą listę.
        </p>
      ) : (
        <>
          {top.length > 0 && (
            <section aria-label="Najmocniejsze typy najbliższej doby" className="mt-7">
              <h2 className="flex items-center gap-2.5 font-body text-xs font-semibold uppercase tracking-widest text-brand">
                <span aria-hidden className="h-px w-6 bg-brand-bright" />
                Najmocniejsze w 24 godziny
              </h2>
              <div className="mt-3 space-y-4">
                {top.map((bet, i) => (
                  <Reveal key={bet.id} delay={Math.min(i * 0.05, 0.2)}>
                    {kartaDla(bet, i + 1)}
                  </Reveal>
                ))}
              </div>
            </section>
          )}

          <section aria-label="Wszystkie typy drużynowe po dniach" className="mt-9">
            {top.length > 0 && (
              <h2 className="flex items-center gap-2.5 font-body text-xs font-semibold uppercase tracking-widest text-muted">
                <span aria-hidden className="h-px w-6 bg-hairline" />
                Pełna lista po dniach
              </h2>
            )}
            {dni.map(([klucz, lista]) => {
              const et = etykietaDnia(lista[0].kickoff_ts, teraz);
              return (
                <div key={klucz} className="mt-5">
                  <div className="sticky top-[4.4rem] z-10 -mx-4 bg-paper/85 px-4 py-2 backdrop-blur-md sm:-mx-6 sm:px-6">
                    <p className="font-body text-xs font-semibold uppercase tracking-widest">
                      <span className="text-ink">{et.glowna}</span>{" "}
                      <span className="font-normal normal-case tracking-normal text-faint">
                        {et.data} · {odmienTypy(lista.length)}
                      </span>
                    </p>
                  </div>
                  <div className="mt-2.5 space-y-4">
                    {lista.map((bet) => {
                      const rank = widoczne.findIndex((b) => b.id === bet.id) + 1;
                      return <div key={bet.id}>{kartaDla(bet, rank)}</div>;
                    })}
                  </div>
                </div>
              );
            })}
          </section>
        </>
      )}
    </div>
  );
}
