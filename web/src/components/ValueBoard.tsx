"use client";

import { motion, useReducedMotion } from "framer-motion";
import { useMemo, useState } from "react";

import { BetCard } from "./BetCard";
import type { Pewnosc, ValueBet, Zawodnik } from "@/lib/types";

const RYNKI_FILTRY: { kod: string; label: string }[] = [
  { kod: "wszystkie", label: "Wszystkie rynki" },
  { kod: "shots", label: "Strzały" },
  { kod: "sot", label: "Strzały celne" },
  { kod: "fouls_committed", label: "Faule" },
  { kod: "fouls_won", label: "Faule wywalczone" },
  { kod: "tackles", label: "Odbiory" },
  { kod: "interceptions", label: "Przechwyty" },
  { kod: "shots_outside_box", label: "Zza pola karnego" },
  { kod: "fh_shots", label: "Strzały 1. połowa" },
  { kod: "yellow_card", label: "Żółte kartki" },
  { kod: "shots_off_target", label: "Strzały niecelne" },
  { kod: "shots_blocked", label: "Strzały zablokowane" },
  { kod: "druzyny", label: "Rynki drużynowe" },
  { kod: "inne", label: "Pozostałe" },
];
const GLOWNE_KODY = new Set(RYNKI_FILTRY.map((r) => r.kod));

const PEWNOSC_FILTRY: { kod: Pewnosc | "kazda"; label: string }[] = [
  { kod: "kazda", label: "Każda pewność" },
  { kod: "wysoka", label: "Tylko wysoka" },
  { kod: "srednia", label: "Średnia i wyższa" },
];

export function ValueBoard({
  bets,
  zawodnicy,
  initialMatchId,
}: {
  bets: ValueBet[];
  zawodnicy: Zawodnik[];
  initialMatchId?: number;
}) {
  const [rynek, setRynek] = useState("wszystkie");
  const [pewnosc, setPewnosc] = useState<Pewnosc | "kazda">("kazda");
  const [minEv, setMinEv] = useState(3);
  const [meczId, setMeczId] = useState<number | undefined>(initialMatchId);
  const [limit, setLimit] = useState(25);
  const reduced = useReducedMotion();

  const zawodnikById = useMemo(
    () => new Map(zawodnicy.map((z) => [z.id, z])),
    [zawodnicy],
  );

  const mecze = useMemo(() => {
    const seen = new Map<number, string>();
    for (const b of bets) if (!seen.has(b.mecz_id)) seen.set(b.mecz_id, b.mecz);
    return [...seen.entries()];
  }, [bets]);

  const filtered = useMemo(() => {
    return bets.filter((b) => {
      if (rynek === "druzyny" && !b.rynek_kod.startsWith("team_")) return false;
      if (
        rynek === "inne" &&
        (GLOWNE_KODY.has(b.rynek_kod) || b.rynek_kod.startsWith("team_"))
      )
        return false;
      if (
        rynek !== "wszystkie" &&
        rynek !== "inne" &&
        rynek !== "druzyny" &&
        b.rynek_kod !== rynek
      )
        return false;
      if (pewnosc === "wysoka" && b.pewnosc !== "wysoka") return false;
      if (pewnosc === "srednia" && b.pewnosc === "niska") return false;
      if (b.ev_pct < minEv) return false;
      if (meczId !== undefined && b.mecz_id !== meczId) return false;
      return true;
    });
  }, [bets, rynek, pewnosc, minEv, meczId]);

  const shown = filtered.slice(0, limit);

  return (
    <section aria-label="Lista okazji">
      {/* filtry */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select
          value={rynek}
          onChange={(e) => setRynek(e.target.value)}
          className="rounded-lg border border-hairline bg-card px-3 py-1.5 text-sm"
          aria-label="Filtruj po rynku"
        >
          {RYNKI_FILTRY.map((r) => (
            <option key={r.kod} value={r.kod}>
              {r.label}
            </option>
          ))}
        </select>
        <select
          value={pewnosc}
          onChange={(e) => setPewnosc(e.target.value as Pewnosc | "kazda")}
          className="rounded-lg border border-hairline bg-card px-3 py-1.5 text-sm"
          aria-label="Filtruj po pewności"
        >
          {PEWNOSC_FILTRY.map((p) => (
            <option key={p.kod} value={p.kod}>
              {p.label}
            </option>
          ))}
        </select>
        <select
          value={meczId ?? ""}
          onChange={(e) =>
            setMeczId(e.target.value ? Number(e.target.value) : undefined)
          }
          className="max-w-56 rounded-lg border border-hairline bg-card px-3 py-1.5 text-sm"
          aria-label="Filtruj po meczu"
        >
          <option value="">Wszystkie mecze</option>
          {mecze.map(([id, nazwa]) => (
            <option key={id} value={id}>
              {nazwa}
            </option>
          ))}
        </select>
        <label className="ml-auto flex items-center gap-2 text-sm text-muted">
          min. wartość:
          <input
            type="range"
            min={3}
            max={20}
            step={1}
            value={minEv}
            onChange={(e) => setMinEv(Number(e.target.value))}
            className="accent-(--color-brand)"
          />
          <span className="font-data w-12 text-ink">+{minEv}%</span>
        </label>
      </div>

      <p className="mb-3 text-xs text-faint" aria-live="polite">
        {filtered.length === 0
          ? "Brak okazji spełniających filtry — poluzuj kryteria."
          : `${filtered.length} okazji · posortowane od najlepszej (wartość × pewność)`}
      </p>

      {/* lista */}
      <div className="space-y-2.5">
        {shown.map((bet, i) => (
          <motion.div
            key={bet.id}
            initial={reduced ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(i * 0.03, 0.4), duration: 0.3 }}
          >
            <BetCard
              bet={bet}
              rank={i + 1}
              zawodnik={zawodnikById.get(bet.podmiot_id)}
            />
          </motion.div>
        ))}
      </div>

      {filtered.length > limit && (
        <div className="mt-5 text-center">
          <button
            onClick={() => setLimit((l) => l + 25)}
            className="rounded-lg border border-hairline bg-card px-5 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-brand hover:text-brand"
          >
            Pokaż więcej ({filtered.length - limit} pozostało)
          </button>
        </div>
      )}
    </section>
  );
}
