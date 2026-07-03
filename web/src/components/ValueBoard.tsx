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
  const [rodzaj, setRodzaj] = useState<"okazje" | "sugestie" | "wszystko">("okazje");
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
  };

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
      if (rodzaj === "okazje" && b.sugestia) return false;
      if (rodzaj === "sugestie" && !b.sugestia) return false;
      if (pewnosc === "wysoka" && b.pewnosc !== "wysoka") return false;
      if (pewnosc === "srednia" && b.pewnosc === "niska") return false;
      // sugestie nie mają EV — omijają filtr wartości
      if (!b.sugestia && (b.ev_pct == null || b.ev_pct < minEv)) return false;
      if (meczId !== undefined && b.mecz_id !== meczId) return false;
      return true;
    });
  }, [bets, rynek, pewnosc, minEv, meczId, rodzaj]);

  const shown = filtered.slice(0, limit);

  return (
    <section aria-label="Lista okazji">
      {/* przełącznik: okazje z kursem / sugestie STS */}
      {liczbaSugestii > 0 && (
        <div className="mb-3 inline-flex rounded-lg border border-hairline bg-card p-0.5 text-sm">
          {([
            ["okazje", "Okazje z kursem"],
            ["sugestie", `Sugestie STS (${liczbaSugestii})`],
            ["wszystko", "Wszystko"],
          ] as const).map(([kod, label]) => (
            <button
              key={kod}
              onClick={() => setRodzaj(kod)}
              className={`rounded-md px-3 py-1 transition-colors ${
                rodzaj === kod
                  ? "bg-brand text-white"
                  : "text-muted hover:text-ink"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {/* filtry */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select
          value={rynek}
          onChange={(e) => setRynek(e.target.value)}
          className="rounded-lg border border-hairline bg-card px-3 py-1.5 text-sm"
          aria-label="Filtruj po rynku"
        >
          {RYNKI_FILTRY.map((r) => {
            const n = liczbaPerRynek.get(r.kod) ?? 0;
            return (
              <option key={r.kod} value={r.kod}>
                {r.label} ({n})
              </option>
            );
          })}
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

      {/* legenda: jak czytać karty (zwijana, bez JS) */}
      <details className="group mb-4 rounded-lg border border-hairline bg-card text-sm">
        <summary className="flex cursor-pointer select-none items-center gap-2 px-4 py-2.5 text-muted transition-colors hover:text-ink [&::-webkit-details-marker]:hidden">
          <span
            aria-hidden
            className="flex h-4 w-4 items-center justify-center rounded-full bg-brand-wash text-[10px] font-bold text-brand"
          >
            ?
          </span>
          Jak czytać te karty
          <svg
            aria-hidden
            width="12"
            height="12"
            viewBox="0 0 14 14"
            className="ml-auto text-faint transition-transform group-open:rotate-180"
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
        <ul className="space-y-2 border-t border-hairline px-4 py-3 text-xs leading-relaxed text-ink-soft">
          <li>
            <strong className="text-data-green">Zielona wartość (np. +12%)</strong>{" "}
            — o ile procent kurs bukmachera płaci lepiej, niż powinien według
            modelu. Im wyżej, tym lepsza okazja.
          </li>
          <li>
            <strong>Kropki pewności (●●●)</strong> — ile danych i jak stabilnych
            stoi za predykcją. Trzy kropki = duża próba i pewne minuty; jedna =
            traktuj ostrożnie.
          </li>
          <li>
            <strong>Kolorowy pasek</strong> — możliwe wyniki i ich szanse:
            zielona część to scenariusze „powyżej linii”, kreskowana pionowa
            linia to linia bukmachera.
          </li>
          <li>
            <strong className="text-[#8a5613]">„Sprawdź w STS”</strong> — model
            widzi potencjalną wartość, ale kurs musisz sprawdzić ręcznie w STS
            (podajemy próg, od którego się opłaca).
          </li>
          <li>
            Kliknij kartę, żeby zobaczyć pełne uzasadnienie: dlaczego ten
            zakład, forma zawodnika i przewidywane minuty.
          </li>
        </ul>
      </details>

      <p className="mb-3 text-xs text-faint" aria-live="polite">
        {filtered.length === 0
          ? ""
          : `${filtered.length} okazji · posortowane od najlepszej (wartość × pewność)`}
      </p>

      {filtered.length === 0 && (
        <div className="rounded-(--radius-card) border border-hairline bg-card px-6 py-10 text-center shadow-(--shadow-card)">
          <p className="text-sm font-medium text-ink">
            Brak okazji spełniających obecne filtry
          </p>
          <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted">
            Zmniejsz minimalną wartość, wybierz „Każda pewność” albo inny rynek
            — lub wyczyść wszystko jednym kliknięciem.
          </p>
          <button
            onClick={wyczyscFiltry}
            className="mt-4 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-deep"
          >
            Wyczyść filtry
          </button>
        </div>
      )}

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
