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
  { kod: "kazda", label: "Każda" },
  { kod: "srednia", label: "Średnia i wyższa" },
  { kod: "wysoka", label: "Tylko wysoka" },
];

type SortKey = "ranking" | "ev" | "pewnosc" | "kickoff" | "kurs";

const SORTOWANIA: { kod: SortKey; label: string }[] = [
  { kod: "ranking", label: "Najtrafniejsze (wartość × pewność)" },
  { kod: "ev", label: "Największa wartość" },
  { kod: "pewnosc", label: "Najwyższa pewność" },
  { kod: "kickoff", label: "Najbliższy mecz" },
  { kod: "kurs", label: "Najwyższy kurs" },
];

/** Ostylowany select z etykietą — wspólny wygląd wszystkich filtrów. */
function FilterSelect({
  label,
  value,
  onChange,
  children,
  className = "",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={`flex min-w-0 flex-col gap-1 ${className}`}>
      <span className="text-[10px] font-semibold uppercase tracking-wide text-faint">
        {label}
      </span>
      <span className="relative">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full cursor-pointer appearance-none rounded-lg border border-hairline bg-paper py-1.5 pl-3 pr-8 text-sm text-ink transition-colors hover:border-hairline-strong focus:border-brand"
        >
          {children}
        </select>
        <svg
          aria-hidden
          width="12"
          height="12"
          viewBox="0 0 14 14"
          className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-faint"
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
      </span>
    </label>
  );
}

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
  // gdy rynek chwilowo nie daje okazji z kursem, otwórz od razu sugestie
  const [rodzaj, setRodzaj] = useState<"okazje" | "sugestie" | "wszystko">(() =>
    bets.some((b) => !b.sugestia)
      ? "okazje"
      : bets.some((b) => b.sugestia)
        ? "sugestie"
        : "okazje",
  );
  const [sortuj, setSortuj] = useState<SortKey>("ranking");
  const [limit, setLimit] = useState(25);
  const reduced = useReducedMotion();

  const liczbaSugestii = useMemo(
    () => bets.filter((b) => b.sugestia).length,
    [bets],
  );

  const zawodnikById = useMemo(
    () => new Map(zawodnicy.map((z) => [z.id, z])),
    [zawodnicy],
  );

  const mecze = useMemo(() => {
    const seen = new Map<number, string>();
    for (const b of bets) if (!seen.has(b.mecz_id)) seen.set(b.mecz_id, b.mecz);
    return [...seen.entries()];
  }, [bets]);

  // liczba pozycji per rynek (przy aktywnym rodzaju) — do etykiet filtra
  const liczbaPerRynek = useMemo(() => {
    const m = new Map<string, number>();
    for (const b of bets) {
      if (rodzaj === "okazje" && b.sugestia) continue;
      if (rodzaj === "sugestie" && !b.sugestia) continue;
      let kod = b.rynek_kod;
      if (b.rynek_kod.startsWith("team_")) kod = "druzyny";
      else if (!GLOWNE_KODY.has(b.rynek_kod)) kod = "inne";
      m.set(kod, (m.get(kod) ?? 0) + 1);
      m.set("wszystkie", (m.get("wszystkie") ?? 0) + 1);
    }
    return m;
  }, [bets, rodzaj]);

  const wyczyscFiltry = () => {
    setRynek("wszystkie");
    setPewnosc("kazda");
    setMinEv(3);
    setMeczId(undefined);
    setSortuj("ranking");
  };

  const filtered = useMemo(() => {
    const wynik = bets.filter((b) => {
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
      if (rodzaj === "okazje" && b.sugestia) return false;
      if (rodzaj === "sugestie" && !b.sugestia) return false;
      if (pewnosc === "wysoka" && b.pewnosc !== "wysoka") return false;
      if (pewnosc === "srednia" && b.pewnosc === "niska") return false;
      // sugestie nie mają EV — omijają filtr wartości
      if (!b.sugestia && (b.ev_pct == null || b.ev_pct < minEv)) return false;
      if (meczId !== undefined && b.mecz_id !== meczId) return false;
      return true;
    });
    // kolejność wejściowa = ranking (wartość × pewność) z pipeline
    switch (sortuj) {
      case "ev":
        wynik.sort((a, b) => (b.ev_pct ?? -1) - (a.ev_pct ?? -1));
        break;
      case "pewnosc":
        wynik.sort((a, b) => b.pewnosc_score - a.pewnosc_score);
        break;
      case "kickoff":
        wynik.sort((a, b) => a.kickoff_ts - b.kickoff_ts);
        break;
      case "kurs":
        wynik.sort((a, b) => (b.kurs ?? 0) - (a.kurs ?? 0));
        break;
    }
    return wynik;
  }, [bets, rynek, pewnosc, minEv, meczId, rodzaj, sortuj]);

  const shown = filtered.slice(0, limit);

  return (
    <section aria-label="Lista okazji">
      {/* pasek narzędzi: rodzaj + filtry + sortowanie */}
      <div className="mb-4 rounded-(--radius-card) border border-hairline bg-card p-3.5 shadow-(--shadow-card) sm:p-4">
        {liczbaSugestii > 0 && (
          <div
            className="mb-3.5 inline-flex rounded-lg bg-paper p-0.5 text-sm"
            role="tablist"
            aria-label="Rodzaj pozycji"
          >
            {([
              ["okazje", "Okazje z kursem"],
              ["sugestie", `Sugestie STS (${liczbaSugestii})`],
              ["wszystko", "Wszystko"],
            ] as const).map(([kod, label]) => (
              <button
                key={kod}
                role="tab"
                aria-selected={rodzaj === kod}
                onClick={() => setRodzaj(kod)}
                className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
                  rodzaj === kod
                    ? "bg-card text-brand-deep shadow-(--shadow-card)"
                    : "text-muted hover:text-ink"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-[1.2fr_1fr_1.2fr_1.4fr_auto]">
          <FilterSelect label="Rynek" value={rynek} onChange={setRynek}>
            {RYNKI_FILTRY.map((r) => {
              const n = liczbaPerRynek.get(r.kod) ?? 0;
              return (
                <option key={r.kod} value={r.kod}>
                  {r.label} ({n})
                </option>
              );
            })}
          </FilterSelect>

          <FilterSelect
            label="Pewność"
            value={pewnosc}
            onChange={(v) => setPewnosc(v as Pewnosc | "kazda")}
          >
            {PEWNOSC_FILTRY.map((p) => (
              <option key={p.kod} value={p.kod}>
                {p.label}
              </option>
            ))}
          </FilterSelect>

          <FilterSelect
            label="Mecz"
            value={meczId != null ? String(meczId) : ""}
            onChange={(v) => setMeczId(v ? Number(v) : undefined)}
          >
            <option value="">Wszystkie mecze</option>
            {mecze.map(([id, nazwa]) => (
              <option key={id} value={id}>
                {nazwa}
              </option>
            ))}
          </FilterSelect>

          <FilterSelect
            label="Sortuj"
            value={sortuj}
            onChange={(v) => setSortuj(v as SortKey)}
          >
            {SORTOWANIA.map((s) => (
              <option key={s.kod} value={s.kod}>
                {s.label}
              </option>
            ))}
          </FilterSelect>

          <label className="col-span-2 flex flex-col gap-1 sm:col-span-4 lg:col-span-1 lg:w-44">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-faint">
              Min. wartość: <span className="font-data text-ink">+{minEv}%</span>
            </span>
            <input
              type="range"
              min={3}
              max={20}
              step={1}
              value={minEv}
              onChange={(e) => setMinEv(Number(e.target.value))}
              className="h-8 accent-(--color-brand)"
              aria-label="Minimalna wartość okazji w procentach"
            />
          </label>
        </div>
      </div>

      <p className="mb-3 text-xs text-faint" aria-live="polite">
        {filtered.length > 0 &&
          `${filtered.length} ${filtered.length === 1 ? "pozycja" : "pozycji"}${
            sortuj === "ranking" ? " · od najtrafniejszej" : ""
          }`}
      </p>

      {filtered.length === 0 &&
        (rodzaj === "okazje" && !bets.some((b) => !b.sugestia) ? (
          <div className="rounded-(--radius-card) border border-hairline bg-card px-6 py-10 text-center shadow-(--shadow-card)">
            <p className="text-sm font-medium text-ink">
              Rynek w tej chwili nie daje okazji z kursem
            </p>
            <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted">
              Bukmacher wycenia dostępne zdarzenia blisko szans modelu — nie ma
              czego przepłacać. To się zmienia z każdą aktualizacją kursów:
              zajrzyj do sugestii STS albo wróć za pół godziny.
            </p>
            {liczbaSugestii > 0 && (
              <button
                onClick={() => setRodzaj("sugestie")}
                className="mt-4 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-deep"
              >
                Zobacz sugestie STS ({liczbaSugestii})
              </button>
            )}
          </div>
        ) : (
          <div className="rounded-(--radius-card) border border-hairline bg-card px-6 py-10 text-center shadow-(--shadow-card)">
            <p className="text-sm font-medium text-ink">
              Brak pozycji spełniających obecne filtry
            </p>
            <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted">
              Zmniejsz minimalną wartość, ustaw pewność na „Każda” albo wybierz
              inny rynek — lub zacznij od czysta.
            </p>
            <button
              onClick={wyczyscFiltry}
              className="mt-4 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-deep"
            >
              Wyczyść filtry
            </button>
          </div>
        ))}

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
