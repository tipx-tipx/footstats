"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState } from "react";

import {
  CountUpKurs,
  LegiStagger,
  LegWpada,
  PasekSzansy,
} from "./KuponAnim";
import { fmtDataCzas, fmtEV, fmtKurs, fmtLinia, fmtProc } from "@/lib/format";
import {
  KARY_DEFAULT,
  MIN_LEG_EV,
  type Kary,
  type KuponWynik,
  type OpcjeKuponu,
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

function odmienTyp(n: number): string {
  return n === 1 ? "typ" : n < 5 ? "typy" : "typów";
}

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
  const [liczbaTypow, setLiczbaTypow] = useState(3);
  const [trybDokladny, setTrybDokladny] = useState(false);
  const [profil, setProfil] = useState<Profil>("zbalansowany");
  const [tylkoValue, setTylkoValue] = useState(false);
  const [maxJedenZMeczu, setMaxJedenZMeczu] = useState(false);
  const [wynik, setWynik] = useState<KuponWynik | null | "brak">(null);
  const [nauka, setNauka] = useState<"idle" | "wysylanie" | "ok" | "blad">("idle");

  // pula po filtrach meczów/value — bez tego podgląd liczyłby się na całej puli
  const pulaFiltrowana = useMemo(() => {
    let pp = bazowa;
    if (meczId == null && wybrane.size) pp = pp.filter((l) => wybrane.has(l.mecz_id));
    // styl "value" backendu (kupony.py:_kandydaci): wyraźna przewaga + 1 leg
    // na mecz — bez tego generator dawał legi słabsze niż automatyczne kupony
    // value mimo tekstu "te same bezpieczniki"
    if (tylkoValue) pp = pp.filter((l) => (l.ev_pct ?? -Infinity) >= MIN_LEG_EV);
    return pp;
  }, [bazowa, meczId, wybrane, tylkoValue]);

  const opcje: OpcjeKuponu = useMemo(
    () => ({
      profil,
      minLegi: liczbaTypow,
      maxLegi: trybDokladny ? liczbaTypow : undefined,
      maxNaMecz: tylkoValue || maxJedenZMeczu ? 1 : undefined,
      kary,
    }),
    [profil, liczbaTypow, trybDokladny, tylkoValue, maxJedenZMeczu, kary],
  );

  // ŻYWY podgląd — liczony na bieżąco przy każdej zmianie suwaka, żeby user
  // widział OSIĄGALNOŚĆ przed kliknięciem, nie dopiero po (ten sam wynik,
  // klik tylko go "promuje" do dużej animowanej karty)
  const podglad = useMemo(() => {
    const cmin = kursCel * 0.85;
    const cmax = kursCel * 1.18;
    return zlozKupon(pulaFiltrowana, cmin, cmax, opcje);
  }, [pulaFiltrowana, kursCel, opcje]);

  const podpowiedzBrak = useMemo(() => {
    if (podglad) return null;
    if (pulaFiltrowana.length < liczbaTypow) {
      return `Za mało dostępnych typów w tej puli (masz ${pulaFiltrowana.length}, potrzeba ${
        trybDokladny ? "dokładnie" : "co najmniej"
      } ${liczbaTypow}).`;
    }
    const gornyLimit = trybDokladny ? liczbaTypow : Math.min(pulaFiltrowana.length, 12);
    const rosnaco = pulaFiltrowana.map((l) => l.kurs).sort((a, b) => a - b);
    const malejaco = pulaFiltrowana.map((l) => l.kurs).sort((a, b) => b - a);
    const minKursN = rosnaco.slice(0, liczbaTypow).reduce((a, b) => a * b, 1);
    const maxKursN = malejaco.slice(0, gornyLimit).reduce((a, b) => a * b, 1);
    const cmin = kursCel * 0.85;
    const cmax = kursCel * 1.18;
    if (cmax < minKursN) {
      return `Przy ${trybDokladny ? "dokładnie" : "co najmniej"} ${liczbaTypow} ${odmienTyp(liczbaTypow)} najniższy osiągalny kurs w tej puli to ok. ×${fmtKurs(minKursN)} — podnieś kurs docelowy albo zmniejsz liczbę typów.`;
    }
    if (cmin > maxKursN) {
      return `Przy ${trybDokladny ? "dokładnie" : "maks."} ${gornyLimit} ${odmienTyp(gornyLimit)} najwyższy osiągalny kurs w tej puli to ok. ×${fmtKurs(maxKursN)} — obniż kurs docelowy albo zwiększ liczbę typów${meczId == null ? " lub dobierz więcej meczów" : ""}.`;
    }
    return "Ten zestaw parametrów nie daje się złożyć z tej puli — spróbuj innego charakteru kuponu albo profilu.";
  }, [podglad, pulaFiltrowana, liczbaTypow, trybDokladny, kursCel, meczId]);

  const odrzuc = () => {
    setWynik(null);
    setNauka("idle");
  };

  const uczModel = async (k: KuponWynik) => {
    setNauka("wysylanie");
    try {
      const res = await fetch("/api/kupon-pomin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          akcja: "wlasny_nauka",
          kupon: { legi: k.legi, kurs_laczny: k.kurs_laczny, p_model: k.p_model },
        }),
      });
      if (res.ok) {
        setNauka("ok");
        setTimeout(() => {
          setWynik(null);
          setNauka("idle");
        }, 1700);
      } else {
        setNauka("blad");
      }
    } catch {
      setNauka("blad");
    }
  };

  const toggleMecz = (id: number) => {
    setWybrane((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
    setWynik(null);
  };

  const zloz = () => setWynik(podglad ?? "brak");

  if (bazowa.length === 0) {
    return (
      <p className="rounded-xl border border-hairline bg-card px-4 py-3.5 text-sm text-muted">
        Brak typów w puli do złożenia kuponu{meczId != null ? " na ten mecz" : ""} —
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

      {/* kurs docelowy + liczba typów */}
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
            <span>{trybDokladny ? "dokładnie typów" : "co najmniej typów"}</span>
            <span className="font-data text-sm font-semibold text-ink">{liczbaTypow}</span>
          </span>
          <input
            type="range"
            min={2}
            max={8}
            step={1}
            value={liczbaTypow}
            onChange={(e) => { setLiczbaTypow(Number(e.target.value)); setWynik(null); }}
            className="w-full accent-[var(--color-brand)]"
          />
          <div className="mt-1 flex items-center justify-between gap-2">
            <span className="text-[10px] text-faint">
              {trybDokladny
                ? "kupon będzie miał dokładnie tyle typów"
                : "model może dołożyć więcej, jeśli to podnosi szansę"}
            </span>
            <button
              onClick={() => { setTrybDokladny((v) => !v); setWynik(null); }}
              className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium transition-colors ${
                trybDokladny
                  ? "border-brand/40 bg-brand-wash text-brand-deep"
                  : "border-hairline bg-paper text-faint hover:text-ink"
              }`}
              title="Przełącz między 'co najmniej N' a 'dokładnie N' typów"
            >
              {trybDokladny ? "✓ dokładnie" : "co najmniej"}
            </button>
          </div>
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

      <div className="mt-3 space-y-2.5">
        <label
          className="flex cursor-pointer items-start gap-2 text-xs"
          title={`Techniczne kryterium: typ z przewagą liczoną na ≥${MIN_LEG_EV}% i maks. 1 typ z meczu`}
        >
          <input
            type="checkbox"
            checked={tylkoValue}
            onChange={(e) => { setTylkoValue(e.target.checked); setWynik(null); }}
            className="mt-0.5 accent-[var(--color-brand)]"
          />
          <span>
            <span className="font-medium text-ink">Tylko pewne typy z przewagą</span>
            <br />
            <span className="text-muted">
              Bukmacher płaci za nie więcej, niż powinien. Maks. 1 typ z meczu.
            </span>
          </span>
        </label>
        <label
          className={`flex items-start gap-2 text-xs ${
            tylkoValue ? "cursor-not-allowed" : "cursor-pointer"
          }`}
          title="Ogranicza kupon do jednego typu z każdego meczu, niezależnie od opcji powyżej"
        >
          <input
            type="checkbox"
            checked={tylkoValue || maxJedenZMeczu}
            disabled={tylkoValue}
            onChange={(e) => { setMaxJedenZMeczu(e.target.checked); setWynik(null); }}
            className="mt-0.5 accent-[var(--color-brand)]"
          />
          <span>
            <span className={`font-medium ${tylkoValue ? "text-faint" : "text-ink"}`}>
              Nie więcej niż 1 typ z jednego meczu
            </span>
            <br />
            <span className={tylkoValue ? "text-faint" : "text-muted"}>
              Typy z tego samego meczu często wygrywają albo przegrywają razem
              {tylkoValue ? " (już włączone powyżej)" : ""}.
            </span>
          </span>
        </label>
      </div>

      {/* żywy podgląd osiągalności — zanim user w ogóle kliknie */}
      <p
        className={`mt-3 text-xs leading-relaxed ${
          podglad ? "text-brand-deep" : "text-[#8a5613]"
        }`}
      >
        {podglad
          ? `✓ da się złożyć: kurs ×${fmtKurs(podglad.kurs_laczny)} · szansa ${fmtProc(
              podglad.p_model,
            )} · ${podglad.legi.length} ${odmienTyp(podglad.legi.length)}`
          : `✕ ${podpowiedzBrak}`}
      </p>

      <button
        onClick={zloz}
        disabled={!podglad}
        className="mt-2 w-full rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white transition-transform hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0"
      >
        {meczId != null ? "Złóż kupon na ten mecz" : "Złóż kupon"}
      </button>

      {/* wynik */}
      <AnimatePresence mode="wait">
        {wynik === "brak" && (
          <motion.p
            key="brak"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mt-4 rounded-lg border border-data-amber/40 bg-data-amber-wash px-3 py-2.5 text-xs text-[#8a5613]"
          >
            {podpowiedzBrak ?? "Nie da się domknąć tego kompletu — zmień parametry."}
          </motion.p>
        )}
        {wynik && wynik !== "brak" && (
          <KuponKarta
            key="kupon"
            k={wynik}
            nauka={nauka}
            tylkoValue={tylkoValue}
            onOdrzuc={odrzuc}
            onNauka={() => uczModel(wynik)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function KuponKarta({
  k,
  nauka,
  tylkoValue,
  onOdrzuc,
  onNauka,
}: {
  k: KuponWynik;
  nauka: "idle" | "wysylanie" | "ok" | "blad";
  tylkoValue: boolean;
  onOdrzuc: () => void;
  onNauka: () => void;
}) {
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
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className="mt-4 rounded-xl border border-brand/25 bg-gradient-to-br from-brand-wash to-card p-4 shadow-(--shadow-card)"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <CountUpKurs
          value={k.kurs_laczny}
          className="font-data text-2xl font-bold text-ink"
        />
        <span className="text-sm text-muted">
          szansa <strong className="font-data text-ink">{fmtProc(k.p_model)}</strong>
          {" · "}z {STAWKA} zł robi się{" "}
          <strong className="font-data text-ink">{zwrot} zł</strong>
        </span>
      </div>
      <PasekSzansy p={k.p_model} className="mt-2.5" />

      <LegiStagger className="mt-3 space-y-3">
        {grupy.map((g, gi) => (
          <div key={gi}>
            <LegWpada>
              <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-faint">
                {g.mecz}
              </p>
            </LegWpada>
            <ul className="space-y-1.5">
              {g.legi.map((l, li) => {
                const globalIdx = k.legi.indexOf(l);
                return (
                <LegWpada key={li}>
                  <li className="flex items-center justify-between gap-2 rounded-lg bg-card/70 px-3 py-2 text-sm">
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
                        {globalIdx === k.najslabszy_idx && k.legi.length > 1 && (
                          <span
                            title="Typ o najniższej szansie — najmocniej ciągnie szansę kuponu w dół"
                            className="rounded-md bg-data-amber-wash px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-[#8a5613]"
                          >
                            ⚠ najsłabsze
                          </span>
                        )}
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      <span className="font-data text-xs text-faint">{fmtProc(l.p_model)}</span>
                      <span className="font-data font-semibold">@{fmtKurs(l.kurs)}</span>
                    </span>
                  </li>
                </LegWpada>
                );
              })}
            </ul>
          </div>
        ))}
      </LegiStagger>

      {/* rentgen: propozycja wymiany najsłabszego ogniwa (doradcza) */}
      {k.alternatywa && (
        <div className="mt-3 rounded-lg border border-dashed border-brand/30 bg-brand-wash/40 px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-brand">
            ✦ mocniejsza wersja tego kuponu
          </p>
          <p className="mt-1.5 text-sm leading-relaxed">
            <span className="text-muted line-through decoration-data-red/50">
              {k.legi[k.alternatywa.zamiast_idx]?.podmiot}{" "}
              {k.legi[k.alternatywa.zamiast_idx]?.rynek.toLowerCase()}{" "}
              {fmtLinia(k.legi[k.alternatywa.zamiast_idx]?.linia ?? 0)}
            </span>{" "}
            → <strong>{k.alternatywa.podmiot}</strong>{" "}
            <span className="text-muted">
              {k.alternatywa.rynek.toLowerCase()} powyżej {fmtLinia(k.alternatywa.linia)}
            </span>{" "}
            <span className="font-data font-semibold">@{fmtKurs(k.alternatywa.kurs)}</span>
          </p>
          <p className="font-data mt-1 text-xs text-muted">
            szansa {fmtProc(k.p_model)} →{" "}
            <strong className="text-brand-deep">{fmtProc(k.alternatywa.p_po)}</strong>
            {" · "}kurs {fmtKurs(k.kurs_laczny)} → {fmtKurs(k.alternatywa.kurs_po)}
          </p>
        </div>
      )}

      {/* dołożenie: dobicie kursu pewnym typem, gdy kupon wisi nisko */}
      {k.dolozenie && (
        <div className="mt-3 rounded-lg border border-dashed border-hairline bg-paper/60 px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted">
            + dobij kurs pewnym typem
          </p>
          <p className="mt-1 text-sm leading-relaxed">
            <strong>{k.dolozenie.podmiot}</strong>{" "}
            <span className="text-muted">
              {k.dolozenie.rynek.toLowerCase()} powyżej {fmtLinia(k.dolozenie.linia)}
            </span>{" "}
            <span className="font-data font-semibold">@{fmtKurs(k.dolozenie.kurs)}</span>
          </p>
          <p className="font-data mt-1 text-xs text-muted">
            kurs {fmtKurs(k.kurs_laczny)} → {fmtKurs(k.dolozenie.kurs_po)}
            {" · "}szansa {fmtProc(k.p_model)} → {fmtProc(k.dolozenie.p_po)}
          </p>
        </div>
      )}

      {/* wariant B: wyraźnie inny zestaw z tej samej puli */}
      {k.wariant_b && (
        <details className="mt-3 rounded-lg border border-dashed border-hairline">
          <summary className="cursor-pointer list-none px-3 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted transition-colors hover:text-ink-soft [&::-webkit-details-marker]:hidden">
            ⇄ pokaż inny wariant — kurs {fmtKurs(k.wariant_b.kurs_laczny)}, szansa{" "}
            {fmtProc(k.wariant_b.p_model)}
          </summary>
          <div className="space-y-1 px-3 pb-2.5">
            {k.wariant_b.legi.map((l, wi) => (
              <p
                key={`${l.mecz_id}-${l.podmiot_id}-${wi}`}
                className="flex items-baseline justify-between gap-2 text-xs"
              >
                <span className="min-w-0 truncate">
                  <strong>{l.podmiot}</strong>{" "}
                  <span className="text-muted">
                    {l.rynek.toLowerCase()} powyżej {fmtLinia(l.linia)} · {l.mecz}
                  </span>
                </span>
                <span className="font-data shrink-0">{fmtKurs(l.kurs)}</span>
              </p>
            ))}
            <p className="pt-1 text-[10px] text-faint">
              wariant podglądowy — jeśli wolisz ten zestaw, zbuduj go wybierając te mecze
            </p>
          </div>
        </details>
      )}

      <p className="mt-3 text-[11px] text-faint">
        {tylkoValue
          ? "Ten sam dobór co w automatycznych kuponach value — tylko typy z wyraźną przewagą, maks. 1 z meczu."
          : "Ta sama przeanalizowana pula i te same reguły doboru typów co w automatycznych kuponach."}
      </p>

      {/* usuwanie kuponu: całkowite albo z nauką modelu */}
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-hairline pt-3">
        {nauka === "ok" ? (
          <span className="text-xs font-medium text-brand-deep">
            ✓ Kupon trafił do nauki — rozliczy się w tle i poprawi model.
          </span>
        ) : (
          <>
            <button
              onClick={onOdrzuc}
              disabled={nauka === "wysylanie"}
              className="rounded-lg border border-hairline bg-card px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:text-ink disabled:opacity-50"
            >
              ✕ Odrzuć
            </button>
            <button
              onClick={onNauka}
              disabled={nauka === "wysylanie"}
              title="Kupon rozliczy się w tle (jak pominięty) i pomoże modelowi lepiej dobierać typy w przyszłości"
              className="rounded-lg border border-brand/40 bg-brand-wash px-3 py-1.5 text-xs font-medium text-brand-deep transition-colors hover:bg-brand-wash/70 disabled:opacity-50"
            >
              {nauka === "wysylanie" ? "zapisuję…" : "✕ Odrzuć i ucz model"}
            </button>
            {nauka === "blad" && (
              <span className="text-xs text-data-red">
                nie udało się zapisać — spróbuj ponownie
              </span>
            )}
          </>
        )}
      </div>
    </motion.div>
  );
}
