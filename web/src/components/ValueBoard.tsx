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

// Kolejność wejściowa bets = ranking silnika (szansa × kurs + kontekst:
// matchup, świeże składy, miękka linia) — to jest "Polecane".
const SORTOWANIA: { kod: SortKey; label: string }[] = [
  { kod: "ranking", label: "Polecane przez model" },
  { kod: "pewnosc", label: "Największa szansa trafienia" },
  { kod: "ev", label: "Największa przewaga nad kursem" },
  { kod: "kurs", label: "Najwyższy kurs" },
  { kod: "kickoff", label: "Najbliższy mecz" },
];
// sugestie nie mają kursu — sorty po kursie/przewadze nic by nie mówiły
const SORTY_BEZ_KURSU: SortKey[] = ["ranking", "pewnosc", "kickoff"];

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
  initialRodzaj,
}: {
  bets: ValueBet[];
  zawodnicy: Zawodnik[];
  initialMatchId?: number;
  initialRodzaj?: "okazje" | "pewniaki" | "sugestie" | "wszystko";
}) {
  const [rynek, setRynek] = useState("wszystkie");
  const [pewnosc, setPewnosc] = useState<Pewnosc | "kazda">("kazda");
  const [meczId, setMeczId] = useState<number | undefined>(initialMatchId);
  // Pewniaki pierwsze i domyślne (user wybiera z nich legi na kupony);
  // domyślny sort = ranking silnika ("Polecane") — samo p_model wynosiłoby
  // na górę zawsze linie 0,5 gwiazd i chowało typy kontekstowe (matchup)
  const [rodzaj, setRodzaj] = useState<
    "okazje" | "pewniaki" | "sugestie" | "wszystko"
  >(
    () =>
      initialRodzaj ?? (bets.some((b) => b.pewniak) ? "pewniaki" : "wszystko"),
  );
  const [sortuj, setSortuj] = useState<SortKey>("ranking");
  const [limit, setLimit] = useState(25);
  const reduced = useReducedMotion();

  const liczbaSugestii = useMemo(
    () => bets.filter((b) => b.sugestia).length,
    [bets],
  );
  const liczbaPewniakow = useMemo(
    () => bets.filter((b) => b.pewniak).length,
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
      if (rodzaj === "okazje" && (b.sugestia || b.pewniak)) continue;
      if (rodzaj === "pewniaki" && !b.pewniak) continue;
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
    setMeczId(undefined);
    setSortuj("ranking"); // spójnie ze stanem początkowym
  };

  // sorty dostępne w bieżącej zakładce (sugestie są bez kursów)
  const dostepneSorty = useMemo(
    () =>
      rodzaj === "sugestie"
        ? SORTOWANIA.filter((s) => SORTY_BEZ_KURSU.includes(s.kod))
        : SORTOWANIA,
    [rodzaj],
  );

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
      if (rodzaj === "okazje" && (b.sugestia || b.pewniak)) return false;
      if (rodzaj === "pewniaki" && !b.pewniak) return false;
      if (rodzaj === "sugestie" && !b.sugestia) return false;
      if (pewnosc === "wysoka" && b.pewnosc !== "wysoka") return false;
      if (pewnosc === "srednia" && b.pewnosc === "niska") return false;
      if (meczId !== undefined && b.mecz_id !== meczId) return false;
      return true;
    });
    // kolejność wejściowa = ranking silnika ("Polecane"); sort jest stabilny,
    // więc remisy każdego kryterium zachowują tę kolejność — m.in. przy
    // "najbliższym meczu" typy w obrębie meczu idą od najlepiej ocenianych
    switch (sortuj) {
      case "ev":
        wynik.sort((a, b) => (b.ev_pct ?? -999) - (a.ev_pct ?? -999));
        break;
      case "pewnosc":
        // "największa szansa" = liczba, którą user widzi na karcie
        wynik.sort((a, b) => b.p_model - a.p_model);
        break;
      case "kickoff":
        wynik.sort((a, b) => a.kickoff_ts - b.kickoff_ts);
        break;
      case "kurs":
        wynik.sort((a, b) => (b.kurs ?? 0) - (a.kurs ?? 0));
        break;
    }
    return wynik;
  }, [bets, rynek, pewnosc, meczId, rodzaj, sortuj]);

  const shown = filtered.slice(0, limit);

  return (
    <section aria-label="Lista okazji">
      {/* pasek narzędzi: rodzaj + filtry + sortowanie */}
      <div className="mb-4 rounded-(--radius-card) border border-hairline bg-card p-3.5 shadow-(--shadow-card) sm:p-4">
        {(liczbaSugestii > 0 || liczbaPewniakow > 0) && (
          <div
            className="mb-3.5 inline-flex flex-wrap gap-0.5 rounded-lg bg-paper p-0.5 text-sm"
            role="tablist"
            aria-label="Rodzaj pozycji"
          >
            {([
              ["pewniaki", `Pewniaki (${liczbaPewniakow})`],
              ["sugestie", `Sugestie STS (${liczbaSugestii})`],
              ["okazje", "Okazje z kursem"],
              ["wszystko", "Wszystko"],
            ] as const).map(([kod, label]) => (
              <button
                key={kod}
                role="tab"
                aria-selected={rodzaj === kod}
                onClick={() => {
                  setRodzaj(kod);
                  // sugestie nie mają kursów — sort po kursie/przewadze
                  // wraca do "Polecane", zamiast udawać, że działa
                  if (
                    kod === "sugestie" &&
                    !SORTY_BEZ_KURSU.includes(sortuj)
                  )
                    setSortuj("ranking");
                }}
                className={`rounded-md px-3 py-2 font-medium transition-colors ${
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

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-[1.2fr_1fr_1.2fr_1.4fr]">
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
            {dostepneSorty.map((s) => (
              <option key={s.kod} value={s.kod}>
                {s.label}
              </option>
            ))}
          </FilterSelect>
        </div>
      </div>

      <p className="mb-3 text-xs text-faint" aria-live="polite">
        {filtered.length > 0 &&
          `${filtered.length} ${filtered.length === 1 ? "pozycja" : "pozycji"}${
            sortuj === "ranking" ? " · najlepiej oceniane przez model najpierw" : ""
          }`}
      </p>

      {filtered.length === 0 &&
        (rodzaj === "okazje" && !bets.some((b) => !b.sugestia && !b.pewniak) ? (
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
              Ustaw pewność na „Każda”, wybierz inny rynek albo mecz — lub
              zacznij od czysta.
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
