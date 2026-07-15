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
  legKey,
  pulaEfektywna,
  zakresOsiagalny,
  zlozKupon,
} from "@/lib/kuponBuilder";
import type { LegPool } from "@/lib/types";

const PROFILE: { kod: Profil; label: string; opis: string }[] = [
  { kod: "bezpieczny", label: "Bezpieczny", opis: "same kotwice o najwyższej szansie" },
  {
    kod: "zbalansowany",
    label: "Zbalansowany",
    opis: "pewne typy; ryzykowny dołoży tylko, gdy kurs jest wyraźnie zawyżony",
  },
  {
    kod: "agresywny",
    label: "Agresywny",
    opis: "dopuszcza ryzykowne typy, mocno ku przewadze i matchupom",
  },
];

const STAWKA = 10; // do „z 10 zł robi się X zł"

function odmienTyp(n: number): string {
  return n === 1 ? "typ" : n < 5 ? "typy" : "typów";
}

/** pinezka „na pewno w kuponie" — glif zamiast emoji, dziedziczy kolor */
function PinIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      width="11"
      height="11"
      viewBox="0 0 12 12"
      className={className}
    >
      <circle cx="7.4" cy="4.6" r="2.7" fill="currentColor" />
      <path
        d="M5.2 6.8 L2.2 9.8"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function GeneratorKuponu({
  pool,
  kary = KARY_DEFAULT,
  wagi,
  meczId,
}: {
  pool: LegPool[];
  kary?: Kary;
  /** zmierzone delty wag zaufania (meta.wagi_zaufania) — te same co backend */
  wagi?: Record<string, number>;
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
  // wybory typów usera: przypięte MUSZĄ wejść do kuponu, usunięte nie wejdą.
  // Mapy (klucz -> typ), żeby chipy znały nazwy nawet gdy kupon się nie składa.
  const [przypiete, setPrzypiete] = useState<Map<string, LegPool>>(new Map());
  const [wykluczone, setWykluczone] = useState<Map<string, LegPool>>(new Map());
  // karta kuponu pokazuje ŻYWY podgląd (nie zamrożoną kopię) — dzięki temu
  // przypięcie/usunięcie typu przelicza kupon na oczach usera
  const [pokazany, setPokazany] = useState(false);
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
      wagi,
      przypiete: [...przypiete.values()],
      wykluczone: new Set(wykluczone.keys()),
    }),
    [profil, liczbaTypow, trybDokladny, tylkoValue, maxJedenZMeczu, kary, wagi, przypiete, wykluczone],
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
    const maxNaMecz = opcje.maxNaMecz ?? 4;
    const gornyLimit = trybDokladny ? liczbaTypow : 12;
    const cmin = kursCel * 0.85;
    const cmax = kursCel * 1.18;
    const piny = [...przypiete.values()];
    // najpierw powody wynikające z WYBORÓW usera — są najłatwiejsze do cofnięcia
    if (piny.length > gornyLimit) {
      return `Wybrałeś ${piny.length} typów „na pewno”, a kupon ma mieć ${
        trybDokladny ? `dokładnie ${liczbaTypow}` : `najwyżej ${gornyLimit}`
      }. Zwiększ liczbę typów albo odepnij któryś.`;
    }
    const naMeczPin = new Map<number, number>();
    for (const l of piny) naMeczPin.set(l.mecz_id, (naMeczPin.get(l.mecz_id) ?? 0) + 1);
    if ([...naMeczPin.values()].some((c) => c > maxNaMecz)) {
      return `Masz przypięte więcej niż ${maxNaMecz} ${odmienTyp(maxNaMecz)} z jednego meczu. Odepnij któryś albo wyłącz ograniczenie „1 typ z meczu”.`;
    }
    const kursPin = piny.reduce((a, l) => a * l.kurs, 1);
    if (kursPin > cmax) {
      return `Same wybrane typy dają już kurs ×${fmtKurs(kursPin)}, czyli powyżej celu. Podnieś kurs docelowy albo odepnij któryś typ.`;
    }
    // osiągalność liczona z TYMI SAMYMI ograniczeniami co dobór typów:
    // filtry profilu (bezpieczny/gambity), unikalny zawodnik, limit z meczu —
    // plus wybory usera (bez usuniętych, sloty zajęte przez przypięte)
    const pinIds = new Set(piny.map((l) => l.podmiot_id));
    const dostepna = pulaFiltrowana.filter(
      (l) => !wykluczone.has(legKey(l)) && !pinIds.has(l.podmiot_id),
    );
    const efektywna = pulaEfektywna(dostepna, profil);
    const zakres = zakresOsiagalny(
      efektywna,
      Math.max(liczbaTypow - piny.length, 0),
      gornyLimit - piny.length,
      maxNaMecz,
    );
    const dopisekProfil =
      profil !== "agresywny" && efektywna.length < dostepna.length
        ? " Charakter kuponu pomija najbardziej ryzykowne typy. Agresywny ma ich więcej."
        : "";
    const dopisekUsuniete = wykluczone.size
      ? " Możesz też przywrócić usunięte typy."
      : "";
    if (!zakres) {
      return `Za mało dostępnych typów przy tych ustawieniach (potrzeba ${
        trybDokladny ? "dokładnie" : "co najmniej"
      } ${liczbaTypow}, maks. ${maxNaMecz} z meczu).${dopisekProfil}${dopisekUsuniete}`;
    }
    if (cmax < zakres.min * kursPin) {
      return `Przy ${trybDokladny ? "dokładnie" : "co najmniej"} ${liczbaTypow} ${odmienTyp(liczbaTypow)} najniższy osiągalny kurs to ok. ×${fmtKurs(zakres.min * kursPin)}. Podnieś kurs docelowy albo zmniejsz liczbę typów.`;
    }
    if (cmin > zakres.max * kursPin) {
      const nMax = zakres.maxN + piny.length;
      return `Przy ${trybDokladny ? "dokładnie" : "maks."} ${nMax} ${odmienTyp(nMax)} najwyższy osiągalny kurs to ok. ×${fmtKurs(zakres.max * kursPin)}. Obniż kurs docelowy${trybDokladny ? " albo zwiększ liczbę typów" : ""}${meczId == null ? " lub dobierz więcej meczów" : ""}.${dopisekProfil}${dopisekUsuniete}`;
    }
    return `Ten zestaw parametrów nie daje się złożyć z tej puli. Zmień kurs docelowy, liczbę typów albo charakter kuponu.${dopisekProfil}${dopisekUsuniete}`;
  }, [podglad, pulaFiltrowana, profil, opcje.maxNaMecz, liczbaTypow, trybDokladny, kursCel, meczId, przypiete, wykluczone]);

  const odrzuc = () => {
    setPokazany(false);
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
          setPokazany(false);
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
    setPokazany(false);
  };

  // przypnij typ ("na pewno w kuponie") — ponowne kliknięcie odpina.
  // Jeden typ na zawodnika: nowy pin zastępuje wcześniejszy pin tego samego
  // zawodnika (np. inna linia strzałów). Pin zdejmuje wcześniejsze usunięcie.
  const przypnij = (l: LegPool) => {
    const k = legKey(l);
    setPrzypiete((m) => {
      const n = new Map(m);
      if (n.has(k)) {
        n.delete(k);
        return n;
      }
      for (const [kk, ll] of n) {
        if (ll.podmiot_id === l.podmiot_id) n.delete(kk);
      }
      n.set(k, l);
      return n;
    });
    setWykluczone((m) => {
      if (!m.has(k)) return m;
      const n = new Map(m);
      n.delete(k);
      return n;
    });
  };

  // usuń typ z kuponu — model od razu dobiera inny (karta przelicza się sama)
  const usunTyp = (l: LegPool) => {
    const k = legKey(l);
    setWykluczone((m) => new Map(m).set(k, l));
    setPrzypiete((m) => {
      if (!m.has(k)) return m;
      const n = new Map(m);
      n.delete(k);
      return n;
    });
  };

  const przywrocTyp = (k: string) =>
    setWykluczone((m) => {
      const n = new Map(m);
      n.delete(k);
      return n;
    });

  const wyczyscWybory = () => {
    setPrzypiete(new Map());
    setWykluczone(new Map());
  };

  const zloz = () => setPokazany(true);

  if (bazowa.length === 0) {
    return (
      <p className="rounded-(--radius-card) border border-hairline bg-card px-4 py-3.5 text-sm text-muted shadow-(--shadow-card)">
        Brak typów w puli do złożenia kuponu{meczId != null ? " na ten mecz" : ""}.
        Pojawią się, gdy Superbet dokwotuje linie (zwykle 1–2 dni przed meczem).
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
                onClick={() => { setWybrane(new Set()); setPokazany(false); }}
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
                className={`whitespace-nowrap rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                  wybrane.has(id)
                    ? "border-brand bg-brand text-on-brand shadow-(--shadow-card)"
                    : "border-hairline bg-card-soft text-muted hover:border-hairline-strong hover:text-ink"
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
            onChange={(e) => { setKursCel(Number(e.target.value)); setPokazany(false); }}
            className="h-8 w-full cursor-pointer accent-brand"
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
            onChange={(e) => { setLiczbaTypow(Number(e.target.value)); setPokazany(false); }}
            className="h-8 w-full cursor-pointer accent-brand"
          />
          <div className="mt-1 flex items-center justify-between gap-2">
            <span className="text-[10px] text-faint">
              {trybDokladny
                ? "kupon będzie miał dokładnie tyle typów"
                : "model może dołożyć więcej, jeśli to podnosi szansę"}
            </span>
            <button
              onClick={() => { setTrybDokladny((v) => !v); setPokazany(false); }}
              className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium transition-colors ${
                trybDokladny
                  ? "border-brand/40 bg-brand-wash text-brand-deep"
                  : "border-hairline bg-card-soft text-faint hover:text-ink"
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
        <div className="inline-flex max-w-full flex-wrap rounded-(--radius-control) border border-hairline bg-paper p-0.5">
          {PROFILE.map((pr) => (
            <button
              key={pr.kod}
              onClick={() => { setProfil(pr.kod); setPokazany(false); }}
              title={pr.opis}
              className={`rounded-lg px-3 py-1.5 text-xs transition-colors ${
                profil === pr.kod
                  ? "bg-card font-semibold text-ink shadow-(--shadow-card)"
                  : "font-medium text-muted hover:text-ink"
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
            onChange={(e) => { setTylkoValue(e.target.checked); setPokazany(false); }}
            className="mt-0.5 accent-brand"
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
            onChange={(e) => { setMaxJedenZMeczu(e.target.checked); setPokazany(false); }}
            className="mt-0.5 accent-brand"
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

      {/* własny wybór typów: przypnij z puli — resztę dobiera model */}
      <details className="mt-3 rounded-(--radius-control) border border-dashed border-hairline">
        <summary className="flex cursor-pointer list-none items-center gap-1.5 px-3 py-2 text-xs font-medium text-muted transition-colors hover:text-ink [&::-webkit-details-marker]:hidden">
          <PinIcon className="shrink-0 text-brand" />
          Chcę konkretne typy w kuponie
          {przypiete.size > 0 && (
            <span className="ml-1.5 rounded-full bg-brand-wash px-1.5 py-0.5 text-[10px] font-semibold text-brand-deep">
              {przypiete.size}
            </span>
          )}
        </summary>
        <div className="space-y-2.5 px-3 pb-3">
          <p className="text-[11px] leading-relaxed text-faint">
            Kliknij typ, żeby na pewno wszedł do kuponu, a resztę dobierze
            model. Kliknij drugi raz, żeby odpiąć.
          </p>
          {mecze.map(([mid, { label }]) => {
            const typyMeczu = pulaFiltrowana
              .filter((l) => l.mecz_id === mid && !wykluczone.has(legKey(l)))
              .sort((a, b) => b.p_model - a.p_model);
            if (typyMeczu.length === 0) return null;
            return (
              <div key={mid}>
                <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-faint">
                  {label}
                </p>
                <div className="flex flex-wrap gap-1">
                  {typyMeczu.map((l) => {
                    const k = legKey(l);
                    const pin = przypiete.has(k);
                    return (
                      <button
                        key={k}
                        onClick={() => przypnij(l)}
                        title={`Szansa ${fmtProc(l.p_model)}${pin ? ". Kliknij, żeby odpiąć" : ""}`}
                        className={`inline-flex items-center gap-1 rounded-(--radius-control) border px-2 py-1 text-[11px] transition-colors ${
                          pin
                            ? "border-brand bg-brand-wash font-medium text-brand-deep"
                            : "border-hairline bg-card text-muted hover:border-hairline-strong hover:text-ink"
                        }`}
                      >
                        {pin && <PinIcon className="shrink-0" />}
                        <span>
                          {l.podmiot} · {l.rynek.toLowerCase()} {fmtLinia(l.linia)}+{" "}
                          <span className="font-data">@{fmtKurs(l.kurs)}</span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </details>

      {/* podsumowanie wyborów usera — widoczne też, gdy kupon się nie składa */}
      {(przypiete.size > 0 || wykluczone.size > 0) && (
        <div className="mt-3 space-y-1.5 text-xs">
          {przypiete.size > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-faint">na pewno w kuponie:</span>
              {[...przypiete.entries()].map(([k, l]) => (
                <button
                  key={k}
                  onClick={() => przypnij(l)}
                  title="Kliknij, żeby odpiąć. Model będzie mógł wybrać inny typ"
                  className="inline-flex items-center gap-1 rounded-full border border-brand/40 bg-brand-wash px-2 py-0.5 text-[11px] font-medium text-brand-deep transition-colors hover:bg-brand-wash/70"
                >
                  <PinIcon className="shrink-0" />
                  {l.podmiot} · {l.rynek.toLowerCase()} {fmtLinia(l.linia)}+ ✕
                </button>
              ))}
            </div>
          )}
          {wykluczone.size > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-faint">usunięte z kuponu:</span>
              {[...wykluczone.entries()].map(([k, l]) => (
                <button
                  key={k}
                  onClick={() => przywrocTyp(k)}
                  title="Kliknij, żeby przywrócić. Typ znów będzie mógł wejść do kuponu"
                  className="rounded-full border border-hairline bg-card-soft px-2 py-0.5 text-[11px] text-muted line-through transition-colors hover:text-ink"
                >
                  {l.podmiot} · {l.rynek.toLowerCase()} {fmtLinia(l.linia)}+ ↺
                </button>
              ))}
            </div>
          )}
          <button
            onClick={wyczyscWybory}
            className="text-[11px] text-brand hover:underline"
          >
            wyczyść moje wybory
          </button>
        </div>
      )}

      {/* żywy podgląd osiągalności — zanim user w ogóle kliknie */}
      <p
        className={`mt-3 rounded-(--radius-control) px-3 py-2 text-xs leading-relaxed ${
          podglad
            ? "bg-data-green-wash text-data-green-ink"
            : "bg-data-amber-wash text-data-amber-ink"
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
        className="mt-2.5 w-full rounded-(--radius-control) bg-brand px-4 py-2.5 text-sm font-semibold text-on-brand shadow-(--shadow-card) transition-colors hover:bg-brand-strong disabled:cursor-not-allowed disabled:bg-card-soft disabled:text-faint disabled:shadow-none"
      >
        {meczId != null ? "Złóż kupon na ten mecz" : "Złóż kupon"}
      </button>

      {/* wynik — karta pokazuje ŻYWY podgląd: usunięcie/przypięcie typu
          przelicza kupon od razu, bez ponownego klikania "Złóż kupon" */}
      <AnimatePresence mode="wait">
        {pokazany && !podglad && (
          <motion.p
            key="brak"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mt-4 rounded-(--radius-control) border border-data-amber/40 bg-data-amber-wash px-3 py-2.5 text-xs text-data-amber-ink"
          >
            {podpowiedzBrak ?? "Nie da się domknąć tego kompletu. Zmień parametry."}
          </motion.p>
        )}
        {pokazany && podglad && (
          <KuponKarta
            key="kupon"
            k={podglad}
            nauka={nauka}
            tylkoValue={tylkoValue}
            przypieteKeys={przypiete}
            onOdrzuc={odrzuc}
            onNauka={() => uczModel(podglad)}
            onPrzypnij={przypnij}
            onUsun={usunTyp}
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
  przypieteKeys,
  onOdrzuc,
  onNauka,
  onPrzypnij,
  onUsun,
}: {
  k: KuponWynik;
  nauka: "idle" | "wysylanie" | "ok" | "blad";
  tylkoValue: boolean;
  przypieteKeys: ReadonlyMap<string, LegPool>;
  onOdrzuc: () => void;
  onNauka: () => void;
  onPrzypnij: (l: LegPool) => void;
  onUsun: (l: LegPool) => void;
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
      className="mt-4 overflow-hidden rounded-(--radius-card) border border-brand/25 bg-card shadow-(--shadow-card)"
    >
      {/* nagłówek biletu */}
      <div className="bg-gradient-to-br from-brand-wash via-brand-wash/60 to-card px-4 pb-4 pt-4">
        <p className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-brand">
          <span aria-hidden className="h-px w-5 bg-brand-bright" />
          twój kupon
        </p>
        <div className="mt-2.5 flex flex-wrap items-baseline justify-between gap-2">
          <CountUpKurs
            value={k.kurs_laczny}
            className="font-data text-3xl font-bold text-ink"
          />
          <span className="text-sm text-muted">
            szansa <strong className="font-data text-ink">{fmtProc(k.p_model)}</strong>
            {" · "}z {STAWKA} zł robi się{" "}
            <strong className="font-data text-ink">{zwrot} zł</strong>
          </span>
        </div>
        <PasekSzansy p={k.p_model} className="mt-3" />
      </div>

      {/* perforacja biletu */}
      <div aria-hidden className="relative">
        <span className="absolute -left-2.5 top-1/2 h-5 w-5 -translate-y-1/2 rounded-full border border-brand/25 bg-card" />
        <span className="absolute -right-2.5 top-1/2 h-5 w-5 -translate-y-1/2 rounded-full border border-brand/25 bg-card" />
        <span className="mx-4 block border-t border-dashed border-hairline-strong" />
      </div>

      <div className="px-4 pb-4 pt-3">
      <LegiStagger className="space-y-3">
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
                  <li className="flex items-center justify-between gap-2 rounded-(--radius-control) bg-card-soft px-3 py-2 text-sm">
                    <span className="min-w-0">
                      <span className="font-medium">{l.podmiot}</span>{" "}
                      <span className="text-muted">
                        {l.rynek.toLowerCase()} powyżej {fmtLinia(l.linia)}
                      </span>
                      <span className="ml-1.5 inline-flex gap-1 align-middle">
                        {l.matchup && (
                          <span
                            title="Profil rywala sprzyja"
                            className="text-[10px] font-semibold text-brand"
                          >
                            ◎
                          </span>
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
                            title="Typ o najniższej szansie, najmocniej ciągnie szansę kuponu w dół"
                            className="rounded-full bg-data-amber-wash px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-data-amber-ink"
                          >
                            najsłabszy typ
                          </span>
                        )}
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      <span className="font-data text-xs text-faint">{fmtProc(l.p_model)}</span>
                      <span className="font-data font-semibold">@{fmtKurs(l.kurs)}</span>
                      <span className="flex items-center gap-1">
                        <button
                          onClick={() => onPrzypnij(l)}
                          title={
                            przypieteKeys.has(legKey(l))
                              ? "Typ przypięty. Kliknij, żeby odpiąć"
                              : "Zostaw ten typ na pewno (model nie będzie go wymieniał)"
                          }
                          className={`rounded-md px-1.5 py-1 transition-colors ${
                            przypieteKeys.has(legKey(l))
                              ? "bg-brand-wash text-brand-deep"
                              : "text-faint hover:bg-card hover:text-ink"
                          }`}
                        >
                          <PinIcon />
                        </button>
                        <button
                          onClick={() => onUsun(l)}
                          title="Usuń ten typ, a model dobierze inny"
                          className="rounded-md px-1.5 py-1 text-xs text-faint transition-colors hover:bg-data-red-wash hover:text-data-red-ink"
                        >
                          ✕
                        </button>
                      </span>
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
        <div className="mt-3 rounded-(--radius-control) border border-dashed border-brand/30 bg-brand-wash/40 px-3 py-2.5">
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
        <div className="mt-3 rounded-(--radius-control) border border-dashed border-hairline bg-card-soft/70 px-3 py-2.5">
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
        <details className="mt-3 rounded-(--radius-control) border border-dashed border-hairline">
          <summary className="cursor-pointer list-none px-3 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted transition-colors hover:text-ink-soft [&::-webkit-details-marker]:hidden">
            ⇄ pokaż inny wariant: kurs {fmtKurs(k.wariant_b.kurs_laczny)}, szansa{" "}
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
              wariant podglądowy. Jeśli wolisz ten zestaw, zbuduj go wybierając te mecze
            </p>
          </div>
        </details>
      )}

      <p className="mt-3 text-[11px] text-faint">
        {tylkoValue
          ? "Ten sam dobór co w automatycznych kuponach value: tylko typy z wyraźną przewagą, maks. 1 z meczu."
          : "Ta sama przeanalizowana pula i te same reguły doboru typów co w automatycznych kuponach."}
      </p>

      {/* usuwanie kuponu: całkowite albo z nauką modelu */}
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-hairline pt-3">
        {nauka === "ok" ? (
          <span className="text-xs font-medium text-brand-deep">
            ✓ Kupon trafił do nauki. Rozliczy się w tle i poprawi model.
          </span>
        ) : (
          <>
            <button
              onClick={onOdrzuc}
              disabled={nauka === "wysylanie"}
              className="rounded-(--radius-control) border border-hairline bg-card px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:text-ink disabled:bg-card-soft disabled:text-faint"
            >
              ✕ Odrzuć
            </button>
            <button
              onClick={onNauka}
              disabled={nauka === "wysylanie"}
              title="Kupon rozliczy się w tle (jak pominięty) i pomoże modelowi lepiej dobierać typy w przyszłości"
              className="rounded-(--radius-control) border border-brand/40 bg-brand-wash px-3 py-1.5 text-xs font-medium text-brand-deep transition-colors hover:bg-brand-wash/70 disabled:border-hairline disabled:bg-card-soft disabled:text-faint"
            >
              {nauka === "wysylanie" ? "zapisuję…" : "✕ Odrzuć i ucz model"}
            </button>
            {nauka === "blad" && (
              <span className="text-xs text-data-red">
                nie udało się zapisać, spróbuj ponownie
              </span>
            )}
          </>
        )}
      </div>
      </div>
    </motion.div>
  );
}
