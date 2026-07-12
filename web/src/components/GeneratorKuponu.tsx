"use client";

import { useMemo, useState } from "react";

import { fmtDataCzas, fmtEV, fmtKurs, fmtLinia, fmtProc } from "@/lib/format";
import {
  KARY_DEFAULT,
  type Kary,
  type KuponWynik,
  type Profil,
  zlozKupon,
} from "@/lib/kuponBuilder";
import type { LegPool } from "@/lib/types";

const PROFILE: { kod: Profil; label: string; opis: string }[] = [
  { kod: "bezpieczny", label: "Bezpieczny", opis: "same kotwice o najwyższej szansie" },
  { kod: "zbalansowany", label: "Zbalansowany", opis: "szansa + realna wartość" },
  { kod: "agresywny", label: "Agresywny", opis: "mocno ku przewadze i matchupom" },
];

const STAWKA = 10; // do „z 10 zł robi się X zł"

export function GeneratorKuponu({
  pool,
  kary = KARY_DEFAULT,
  meczId,
}: {
  pool: LegPool[];
  kary?: Kary;
  /** gdy podany — generator ograniczony do jednego meczu (wersja na stronie meczu) */
  meczId?: number;
}) {
  const bazowa = useMemo(
    () => (meczId != null ? pool.filter((l) => l.mecz_id === meczId) : pool),
    [pool, meczId],
  );
  const mecze = useMemo(() => {
    const m = new Map<number, { label: string; ts: number }>();
    for (const l of bazowa) {
      if (!m.has(l.mecz_id)) m.set(l.mecz_id, { label: l.mecz, ts: l.kickoff_ts });
    }
    return [...m.entries()].sort((a, b) => a[1].ts - b[1].ts);
  }, [bazowa]);

  const [wybrane, setWybrane] = useState<Set<number>>(new Set());
  const [kursCel, setKursCel] = useState(meczId != null ? 4 : 10);
  const [minLegi, setMinLegi] = useState(3);
  const [profil, setProfil] = useState<Profil>("zbalansowany");
  const [wynik, setWynik] = useState<KuponWynik | null | "brak">(null);

  const toggleMecz = (id: number) => {
    setWybrane((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
    setWynik(null);
  };

  const zloz = () => {
    let p = bazowa;
    if (meczId == null && wybrane.size) p = p.filter((l) => wybrane.has(l.mecz_id));
    const cmin = kursCel * 0.85;
    const cmax = kursCel * 1.18;
    const k = zlozKupon(p, cmin, cmax, { profil, minLegi, kary });
    setWynik(k ?? "brak");
  };

  if (bazowa.length === 0) {
    return (
      <p className="rounded-xl border border-hairline bg-card px-4 py-3.5 text-sm text-muted">
        Brak legów w puli do złożenia kuponu{meczId != null ? " na ten mecz" : ""} —
        pojawią się, gdy Superbet dokwotuje linie (zwykle 1–2 dni przed meczem).
      </p>
    );
  }

  return (
    <div className="rounded-(--radius-card) border border-hairline bg-card p-4 shadow-(--shadow-card) sm:p-5">
      {/* wybór meczów — tylko w wersji pełnej (/kupony) */}
      {meczId == null && (
        <div className="mb-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[11px] font-medium uppercase tracking-wide text-faint">
              mecze {wybrane.size > 0 ? `(${wybrane.size} wybrane)` : "(wszystkie)"}
            </span>
            {wybrane.size > 0 && (
              <button
                onClick={() => { setWybrane(new Set()); setWynik(null); }}
                className="text-xs text-brand hover:underline"
              >
                wyczyść
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {mecze.map(([id, { label, ts }]) => (
              <button
                key={id}
                onClick={() => toggleMecz(id)}
                title={fmtDataCzas(ts)}
                className={`whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                  wybrane.has(id)
                    ? "bg-brand text-white"
                    : "bg-paper text-muted hover:text-ink"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* kurs docelowy + liczba legów */}
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 flex items-baseline justify-between text-[11px] font-medium uppercase tracking-wide text-faint">
            <span>kurs docelowy</span>
            <span className="font-data text-sm font-semibold text-ink">
              ×{fmtKurs(kursCel)}
            </span>
          </span>
          <input
            type="range"
            min={meczId != null ? 2 : 3}
            max={meczId != null ? 12 : 30}
            step={0.5}
            value={kursCel}
            onChange={(e) => { setKursCel(Number(e.target.value)); setWynik(null); }}
            className="w-full accent-[var(--color-brand)]"
          />
          <span className="text-[10px] text-faint">
            składamy w przedziale ×{fmtKurs(kursCel * 0.85)}–{fmtKurs(kursCel * 1.18)}
          </span>
        </label>
        <label className="block">
          <span className="mb-1 flex items-baseline justify-between text-[11px] font-medium uppercase tracking-wide text-faint">
            <span>min. legów</span>
            <span className="font-data text-sm font-semibold text-ink">{minLegi}</span>
          </span>
          <input
            type="range"
            min={2}
            max={8}
            step={1}
            value={minLegi}
            onChange={(e) => { setMinLegi(Number(e.target.value)); setWynik(null); }}
            className="w-full accent-[var(--color-brand)]"
          />
          <span className="text-[10px] text-faint">im więcej legów, tym wyższy kurs, niższa szansa</span>
        </label>
      </div>

      {/* profil */}
      <div className="mt-4">
        <span className="mb-2 block text-[11px] font-medium uppercase tracking-wide text-faint">
          charakter kuponu
        </span>
        <div className="flex flex-wrap gap-1.5">
          {PROFILE.map((pr) => (
            <button
              key={pr.kod}
              onClick={() => { setProfil(pr.kod); setWynik(null); }}
              title={pr.opis}
              className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                profil === pr.kod
                  ? "border-brand bg-brand-wash text-brand-deep"
                  : "border-hairline bg-paper text-muted hover:text-ink"
              }`}
            >
              {pr.label}
            </button>
          ))}
        </div>
      </div>

      <button
        onClick={zloz}
        className="mt-4 w-full rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white transition-transform hover:-translate-y-0.5"
      >
        {meczId != null ? "Złóż kupon na ten mecz" : "Złóż kupon"}
      </button>

      {/* wynik */}
      {wynik === "brak" && (
        <p className="mt-4 rounded-lg border border-data-amber/40 bg-data-amber-wash px-3 py-2.5 text-xs text-[#8a5613]">
          Z {wybrane.size > 0 ? "wybranych meczów" : "dostępnej puli"} nie da się
          domknąć kursu ×{fmtKurs(kursCel)} przy min. {minLegi} legach. Zmień kurs
          docelowy, liczbę legów{meczId == null ? " lub dobierz więcej meczów" : ""}.
        </p>
      )}
      {wynik && wynik !== "brak" && <KuponKarta k={wynik} />}
    </div>
  );
}

function KuponKarta({ k }: { k: KuponWynik }) {
  const zwrot = (STAWKA * k.kurs_laczny).toFixed(0);
  // legi grupowane po meczu (jak bet builder)
  const grupy = useMemo(() => {
    const m = new Map<number, { mecz: string; legi: typeof k.legi }>();
    for (const l of k.legi) {
      const g = m.get(l.mecz_id) ?? { mecz: l.mecz, legi: [] };
      g.legi.push(l);
      m.set(l.mecz_id, g);
    }
    return [...m.values()];
  }, [k]);

  return (
    <div className="mt-4 rounded-xl border border-brand/25 bg-gradient-to-br from-brand-wash to-card p-4 shadow-(--shadow-card)">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-data text-2xl font-bold text-ink">
          ×{fmtKurs(k.kurs_laczny)}
        </span>
        <span className="text-sm text-muted">
          szansa <strong className="font-data text-ink">{fmtProc(k.p_model)}</strong>
          {" · "}z {STAWKA} zł robi się <strong className="font-data text-ink">{zwrot} zł</strong>
        </span>
      </div>
      <div className="mt-3 space-y-3">
        {grupy.map((g, gi) => (
          <div key={gi}>
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-faint">
              {g.mecz}
            </p>
            <ul className="space-y-1.5">
              {g.legi.map((l, li) => (
                <li
                  key={li}
                  className="flex items-center justify-between gap-2 rounded-lg bg-card/70 px-3 py-2 text-sm"
                >
                  <span className="min-w-0">
                    <span className="font-medium">{l.podmiot}</span>{" "}
                    <span className="text-muted">
                      {l.rynek.toLowerCase()} powyżej {fmtLinia(l.linia)}
                    </span>
                    <span className="ml-1.5 inline-flex gap-1 align-middle">
                      {l.matchup && (
                        <span title="Profil rywala sprzyja" className="text-[10px]">🎯</span>
                      )}
                      {l.ev_uk != null && l.ev_uk >= 4 && (
                        <span
                          title={`Wartość vs no-vig UK: ${fmtEV(l.ev_uk)}`}
                          className="text-[10px] font-semibold text-data-green"
                        >
                          {fmtEV(l.ev_uk)}
                        </span>
                      )}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="font-data text-xs text-faint">{fmtProc(l.p_model)}</span>
                    <span className="font-data font-semibold">@{fmtKurs(l.kurs)}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[11px] text-faint">
        Kupon zbudowany z tej samej przeanalizowanej puli co automatyczne — te same
        bezpieczniki, kary korelacji i premia za wartość. Kursy zmrożone przy budowie.
      </p>
    </div>
  );
}
