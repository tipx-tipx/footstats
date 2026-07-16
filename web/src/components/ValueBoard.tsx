"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";

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

/** Poprawna polska odmiana: "1 pozycja", "3 pozycje", "8 pozycji". */
function odmienPozycje(n: number): string {
  if (n === 1) return "1 pozycja";
  const r10 = n % 10;
  const r100 = n % 100;
  const kilka = r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14);
  return `${n} ${kilka ? "pozycje" : "pozycji"}`;
}

type OpcjaFiltra = { value: string; label: string; n?: number };

/**
 * Dopracowany wybór z listą (zamiast natywnego selecta, którego nie da
 * się ostylować): podkreślenie rośnie od lewej przy hoverze/otwarciu,
 * panel wjeżdża z animacją, wybrana opcja ma znacznik, liczniki po
 * prawej. Klawiatura: Enter/spacja otwiera, strzałki chodzą po liście,
 * Esc zamyka i wraca na przycisk.
 */
function FilterDropdown({
  label,
  value,
  options,
  onChange,
  className = "",
}: {
  label: string;
  value: string;
  options: OpcjaFiltra[];
  onChange: (v: string) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const kontener = useRef<HTMLDivElement | null>(null);
  const panel = useRef<HTMLUListElement | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const klik = (e: PointerEvent) => {
      if (!kontener.current?.contains(e.target as Node)) setOpen(false);
    };
    const klawisz = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener("pointerdown", klik);
    document.addEventListener("keydown", klawisz);
    return () => {
      document.removeEventListener("pointerdown", klik);
      document.removeEventListener("keydown", klawisz);
    };
  }, [open]);

  const wybrana = options.find((o) => o.value === value);
  const przesunFokus = (kierunek: 1 | -1) => {
    const przyciski = Array.from(
      panel.current?.querySelectorAll("button") ?? [],
    );
    if (przyciski.length === 0) return;
    const i = przyciski.indexOf(document.activeElement as HTMLButtonElement);
    przyciski[(i + kierunek + przyciski.length) % przyciski.length]?.focus();
  };

  return (
    <div ref={kontener} className={`relative min-w-0 ${className}`}>
      <button
        ref={trigger}
        type="button"
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && open) {
            e.preventDefault();
            przesunFokus(1);
          }
        }}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="group flex w-full flex-col items-start gap-1 text-left"
      >
        <span className="text-[10px] font-semibold uppercase tracking-wide text-faint">
          {label}
        </span>
        <span className="relative flex w-full items-center justify-between gap-2 pb-1.5">
          <span className="truncate text-sm font-medium text-ink">
            {wybrana?.label ?? "–"}
            {wybrana?.n != null && (
              <span className="font-data text-xs text-faint"> ({wybrana.n})</span>
            )}
          </span>
          <svg
            aria-hidden
            width="12"
            height="12"
            viewBox="0 0 14 14"
            className={`shrink-0 transition-transform duration-200 ${
              open ? "rotate-180 text-brand" : "text-faint"
            }`}
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
          {/* podkreślenie: baza hairline + linia brand rosnąca od lewej */}
          <span aria-hidden className="absolute inset-x-0 bottom-0 h-px bg-hairline" />
          <span
            aria-hidden
            className={`absolute inset-x-0 bottom-0 h-px origin-left bg-brand transition-transform duration-300 ${
              open ? "scale-x-100" : "scale-x-0 group-hover:scale-x-100"
            }`}
          />
        </span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.ul
            ref={panel}
            role="listbox"
            aria-label={label}
            initial={{ opacity: 0, y: -6, scale: 0.99 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.99 }}
            transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                przesunFokus(1);
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                przesunFokus(-1);
              }
            }}
            className="absolute left-0 top-full z-30 mt-2 max-h-80 w-max min-w-full overflow-auto rounded-xl border border-hairline bg-card py-1.5 shadow-(--shadow-pop)"
          >
            {options.map((o) => {
              const aktywna = o.value === value;
              return (
                <li key={o.value}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={aktywna}
                    onClick={() => {
                      onChange(o.value);
                      setOpen(false);
                      trigger.current?.focus();
                    }}
                    className={`flex w-full items-center justify-between gap-6 px-3.5 py-2 text-left text-sm transition-colors hover:bg-brand-wash ${
                      aktywna ? "font-medium text-brand-deep" : "text-ink"
                    }`}
                  >
                    <span className="truncate">{o.label}</span>
                    <span className="flex shrink-0 items-center gap-2">
                      {o.n != null && (
                        <span className="font-data text-xs text-faint">{o.n}</span>
                      )}
                      {aktywna && (
                        <svg
                          aria-hidden
                          width="12"
                          height="12"
                          viewBox="0 0 14 14"
                          className="text-brand"
                        >
                          <path
                            d="M2.5 7.5 L5.5 10.5 L11.5 3.5"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.8"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
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

  // Kotwica ze spotlightu Hero (link „…#bet-<id>”): po wejściu na stronę
  // przewiń do wskazanej karty. Zakładkę ustawia initialRodzaj z ?rodzaj=,
  // a key na ValueBoard (page.tsx) wymusza remont, więc karta jest już w DOM.
  useEffect(() => {
    const scrollToHash = () => {
      const h = window.location.hash;
      if (!/^#bet-\d+$/.test(h)) return;
      const el = document.querySelector(h);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    };
    scrollToHash();
    window.addEventListener("hashchange", scrollToHash);
    return () => window.removeEventListener("hashchange", scrollToHash);
  }, []);

  // zakładki "rodzaj": role=tab wymaga obsługi strzałek (WAI-ARIA Tabs) —
  // roving tabindex, Left/Right/Home/End przenoszą FOKUS I WYBÓR
  const TABY_RODZAJ = [
    ["pewniaki", "Pewniaki", liczbaPewniakow],
    ["sugestie", "Sugestie STS", liczbaSugestii],
    ["okazje", "Okazje z kursem", null],
    ["wszystko", "Wszystko", null],
  ] as const;
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const wybierzRodzaj = (kod: (typeof TABY_RODZAJ)[number][0]) => {
    setRodzaj(kod);
    // sugestie nie mają kursów — sort po kursie/przewadze wraca do
    // "Polecane", zamiast udawać, że działa
    if (kod === "sugestie" && !SORTY_BEZ_KURSU.includes(sortuj)) {
      setSortuj("ranking");
    }
  };
  const onTabKeyDown = (
    e: React.KeyboardEvent<HTMLButtonElement>,
    idx: number,
  ) => {
    let next = idx;
    if (e.key === "ArrowRight") next = (idx + 1) % TABY_RODZAJ.length;
    else if (e.key === "ArrowLeft") {
      next = (idx - 1 + TABY_RODZAJ.length) % TABY_RODZAJ.length;
    } else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = TABY_RODZAJ.length - 1;
    else return;
    e.preventDefault();
    wybierzRodzaj(TABY_RODZAJ[next][0]);
    tabRefs.current[next]?.focus();
  };

  return (
    <section aria-label="Lista okazji">
      {/* przełącznik rodzaju — tablica wyników: czysty tekst, aktywna
          zakładka z podkreśleniem marki (żadnych kolejnych "przycisków") */}
      {(liczbaSugestii > 0 || liczbaPewniakow > 0) && (
        <div
          className="flex flex-wrap items-end gap-x-6 gap-y-1 border-b border-hairline"
          role="tablist"
          aria-label="Rodzaj pozycji"
        >
          {TABY_RODZAJ.map(([kod, label, liczba], i) => (
            <button
              key={kod}
              ref={(el) => { tabRefs.current[i] = el; }}
              role="tab"
              tabIndex={rodzaj === kod ? 0 : -1}
              aria-selected={rodzaj === kod}
              onClick={() => wybierzRodzaj(kod)}
              onKeyDown={(e) => onTabKeyDown(e, i)}
              className={`font-display -mb-px inline-flex items-baseline gap-1.5 border-b-2 px-0.5 pb-2.5 pt-1 text-xs font-semibold uppercase tracking-wide transition-colors ${
                rodzaj === kod
                  ? "border-brand text-brand-deep"
                  : "border-transparent text-muted hover:text-ink"
              }`}
            >
              {label}
              {liczba != null && (
                <span
                  className={`font-data text-[11px] ${
                    rodzaj === kod ? "" : "text-faint"
                  }`}
                >
                  {liczba}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* konsola filtrów: dopracowane dropdowny + żywy odczyt wyniku */}
      <div className="mb-6 grid grid-cols-2 items-end gap-x-6 gap-y-4 pt-4 lg:flex lg:gap-x-9">
        <FilterDropdown
          label="Rynek"
          value={rynek}
          onChange={setRynek}
          className="lg:w-48"
          options={RYNKI_FILTRY.map((r) => ({
            value: r.kod,
            label: r.label,
            n: liczbaPerRynek.get(r.kod) ?? 0,
          }))}
        />

        <FilterDropdown
          label="Pewność"
          value={pewnosc}
          onChange={(v) => setPewnosc(v as Pewnosc | "kazda")}
          className="lg:w-40"
          options={PEWNOSC_FILTRY.map((p) => ({ value: p.kod, label: p.label }))}
        />

        <FilterDropdown
          label="Mecz"
          value={meczId != null ? String(meczId) : ""}
          onChange={(v) => setMeczId(v ? Number(v) : undefined)}
          className="lg:w-56"
          options={[
            { value: "", label: "Wszystkie mecze" },
            ...mecze.map(([id, nazwa]) => ({
              value: String(id),
              label: nazwa,
            })),
          ]}
        />

        <FilterDropdown
          label="Sortuj"
          value={sortuj}
          onChange={(v) => setSortuj(v as SortKey)}
          className="lg:w-56"
          options={dostepneSorty.map((s) => ({ value: s.kod, label: s.label }))}
        />

        {/* żywy odczyt: liczba wjeżdża przy każdej zmianie filtrów */}
        <div
          aria-live="polite"
          className="col-span-2 flex items-baseline justify-between gap-2 lg:ml-auto lg:flex-col lg:items-end lg:justify-start lg:gap-1"
          title="Pozycje spełniające obecne filtry, najlepiej oceniane przez model najpierw"
        >
          <span className="text-[10px] font-semibold uppercase tracking-wide text-faint">
            wynik skanu
          </span>
          <motion.span
            key={filtered.length}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="font-data text-sm font-semibold text-brand-deep"
          >
            {odmienPozycje(filtered.length)}
          </motion.span>
        </div>
      </div>

      {filtered.length === 0 &&
        (rodzaj === "okazje" && !bets.some((b) => !b.sugestia && !b.pewniak) ? (
          <div className="rounded-(--radius-card) border border-hairline bg-card px-6 py-12 text-center shadow-(--shadow-card)">
            <p className="text-sm font-medium text-ink">
              Rynek w tej chwili nie daje okazji z kursem
            </p>
            <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted">
              Bukmacher wycenia dostępne zdarzenia blisko szans modelu, więc
              nie ma czego przepłacać. To się zmienia z każdą aktualizacją
              kursów: zajrzyj do sugestii STS albo wróć za jakiś czas.
            </p>
            {liczbaSugestii > 0 && (
              <button
                onClick={() => setRodzaj("sugestie")}
                className="mt-4 rounded-(--radius-control) bg-brand px-4 py-2 text-sm font-semibold text-on-brand shadow-(--shadow-card) transition-colors hover:bg-brand-strong"
              >
                Zobacz sugestie STS ({liczbaSugestii})
              </button>
            )}
          </div>
        ) : (
          <div className="rounded-(--radius-card) border border-hairline bg-card px-6 py-12 text-center shadow-(--shadow-card)">
            <p className="text-sm font-medium text-ink">
              Brak pozycji spełniających obecne filtry
            </p>
            <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted">
              Ustaw pewność na „Każda”, wybierz inny rynek albo mecz, albo
              zacznij od czysta.
            </p>
            <button
              onClick={wyczyscFiltry}
              className="mt-4 rounded-(--radius-control) bg-brand px-4 py-2 text-sm font-semibold text-on-brand shadow-(--shadow-card) transition-colors hover:bg-brand-strong"
            >
              Wyczyść filtry
            </button>
          </div>
        ))}

      {/* lista kart typów */}
      {shown.length > 0 && (
      <div className="space-y-3">
        {shown.map((bet, i) => (
          <motion.div
            key={bet.id}
            id={`bet-${bet.id}`}
            className="scroll-mt-24"
            initial={{ opacity: 0, y: 10 }}
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
      )}

      {filtered.length > limit && (
        <div className="mt-5 text-center">
          <button
            onClick={() => setLimit((l) => l + 25)}
            className="font-display inline-flex items-center gap-2 px-2 py-1 text-xs font-semibold uppercase tracking-widest text-muted transition-colors hover:text-brand"
          >
            Pokaż więcej
            <span className="font-data tracking-normal">
              ({filtered.length - limit} pozostało)
            </span>
            <span aria-hidden>↓</span>
          </button>
        </div>
      )}
    </section>
  );
}
