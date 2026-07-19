"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";

import {
  CountUpKurs,
  LegiStagger,
  LegWpada,
  PasekSzansy,
} from "./KuponAnim";
import { Segmented } from "./Segmented";
import { useStawka } from "./useStawka";
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

// zapas na obstawienie — jak pipeline (kupony.py: MARGINES_STARTU_S)
const MARGINES_STARTU_S = 15 * 60;

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
  // odcięcie startu jak backend (kupony.py: MARGINES_STARTU_S) — bez tego
  // dało się złożyć (i wysłać do nauki) kupon z meczem już trwającym;
  // znacznik czasu w stanie, żeby nie liczyć Date.now() w renderze
  const [teraz, setTeraz] = useState<number | null>(null);
  useEffect(() => {
    setTeraz(Math.floor(Date.now() / 1000));
  }, []);
  const bazowa = useMemo(() => {
    const zrodlo =
      meczId != null ? pool.filter((l) => l.mecz_id === meczId) : pool;
    if (teraz == null) return zrodlo;
    return zrodlo.filter((l) => l.kickoff_ts > teraz + MARGINES_STARTU_S);
  }, [pool, meczId, teraz]);
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
  const [stawka, setStawka] = useStawka();
  // komunikat mostu ze sceny (ile typów kuponu udało się przypiąć)
  const [mostInfo, setMostInfo] = useState<string | null>(null);

  // pamięć ustawień (tylko pełna wersja na /kupony) — generator bez amnezji
  useEffect(() => {
    if (meczId != null) return;
    try {
      const u = JSON.parse(
        localStorage.getItem("footstats.generator.v1") ?? "null",
      );
      if (!u) return;
      if (typeof u.kursCel === "number")
        setKursCel(Math.min(30, Math.max(3, u.kursCel)));
      if (typeof u.liczbaTypow === "number")
        setLiczbaTypow(Math.min(8, Math.max(2, u.liczbaTypow)));
      if (typeof u.trybDokladny === "boolean") setTrybDokladny(u.trybDokladny);
      if (
        u.profil === "bezpieczny" ||
        u.profil === "zbalansowany" ||
        u.profil === "agresywny"
      )
        setProfil(u.profil);
      if (typeof u.tylkoValue === "boolean") setTylkoValue(u.tylkoValue);
      if (typeof u.maxJedenZMeczu === "boolean")
        setMaxJedenZMeczu(u.maxJedenZMeczu);
    } catch {
      /* uszkodzony wpis — zostają domyślne */
    }
    // mądry start: konsola nie może otwierać się w stanie „nie da się
    // złożyć" — jeśli zapamiętany/domyślny cel jest poza zasięgiem puli,
    // dosuwamy go do osiągalnych widełek
    try {
      const u = JSON.parse(
        localStorage.getItem("footstats.generator.v1") ?? "null",
      );
      const cel: number =
        typeof u?.kursCel === "number"
          ? Math.min(30, Math.max(3, u.kursCel))
          : 10;
      const prof =
        u?.profil === "bezpieczny" || u?.profil === "agresywny"
          ? u.profil
          : "zbalansowany";
      const zakres = zakresOsiagalny(pulaEfektywna(bazowa, prof), 2, 12, 4, prof);
      if (!zakres) return;
      if (cel * 0.85 > zakres.max) {
        setKursCel(
          Math.min(30, Math.max(3, Math.round(zakres.max * 0.95 * 2) / 2)),
        );
      } else if (cel * 1.18 < zakres.min) {
        setKursCel(
          Math.min(30, Math.max(3, Math.round(zakres.min * 1.1 * 2) / 2)),
        );
      }
    } catch {
      /* bez dopasowania */
    }
  }, [meczId, bazowa]);
  useEffect(() => {
    if (meczId != null) return;
    localStorage.setItem(
      "footstats.generator.v1",
      JSON.stringify({
        kursCel,
        liczbaTypow,
        trybDokladny,
        profil,
        tylkoValue,
        maxJedenZMeczu,
      }),
    );
  }, [meczId, kursCel, liczbaTypow, trybDokladny, profil, tylkoValue, maxJedenZMeczu]);

  // most ze sceny („zmień coś w tym kuponie"): przypnij typy kuponu modelu,
  // ustaw cel na jego kurs i od razu pokaż wynik — dalej edytuje się tu
  useEffect(() => {
    const handler = (e: Event) => {
      const det = (e as CustomEvent).detail as
        | {
            legi?: {
              mecz_id: number;
              podmiot: string;
              rynek: string;
              linia: number;
              strona: string;
            }[];
            cel?: number;
          }
        | undefined;
      if (!det?.legi?.length) return;
      const szukane = det.legi;
      const legi = bazowa.filter((l) =>
        szukane.some(
          (s) =>
            s.mecz_id === l.mecz_id &&
            s.podmiot === l.podmiot &&
            s.rynek === l.rynek &&
            s.strona === l.strona &&
            Math.abs(s.linia - l.linia) < 0.01,
        ),
      );
      // pula żyje (Superbet zmienia ofertę), kupon jest zamrożony — więc
      // przypinamy co się da i mówimy wprost, ile typów już nie ma w puli
      setPrzypiete(new Map(legi.map((l) => [legKey(l), l])));
      setWykluczone(new Map());
      setWybrane(new Set());
      setTrybDokladny(false);
      setLiczbaTypow(Math.min(8, Math.max(2, szukane.length)));
      if (det.cel)
        setKursCel(Math.min(30, Math.max(3, Math.round(det.cel * 2) / 2)));
      setPokazany(true);
      setMostInfo(
        legi.length === szukane.length
          ? `Przypięliśmy wszystkie ${legi.length} typy tego kuponu. Usuń albo dodaj, co chcesz — resztę dobierze model.`
          : legi.length > 0
            ? `Przypięliśmy ${legi.length} z ${szukane.length} typów tego kuponu. Reszty nie ma już w aktualnej puli (oferta bukmachera się zmieniła), model dobierze zastępstwa.`
            : `Typów tego kuponu nie ma już w aktualnej puli (oferta bukmachera się zmieniła). Składamy podobny kupon od nowa przy kursie ×${det.cel ? fmtKurs(det.cel) : ""}.`,
      );
    };
    window.addEventListener("footstats:kupon-edytuj", handler);
    return () => window.removeEventListener("footstats:kupon-edytuj", handler);
  }, [bazowa]);

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
      profil,
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

  // ratunek ze stanu „nie da się złożyć": dosuń kurs docelowy do widełek
  // osiągalnych przy OBECNYCH ograniczeniach (piny, wykluczenia, profil)
  const dopasujKurs = () => {
    const maxNaMecz = opcje.maxNaMecz ?? 4;
    const gornyLimit = trybDokladny ? liczbaTypow : 12;
    const piny = [...przypiete.values()];
    const pinIds = new Set(piny.map((l) => l.podmiot_id));
    const kursPin = piny.reduce((a, l) => a * l.kurs, 1);
    const dostepna = pulaFiltrowana.filter(
      (l) => !wykluczone.has(legKey(l)) && !pinIds.has(l.podmiot_id),
    );
    const zakres = zakresOsiagalny(
      pulaEfektywna(dostepna, profil),
      Math.max(liczbaTypow - piny.length, 0),
      gornyLimit - piny.length,
      maxNaMecz,
      profil,
    );
    if (!zakres) return;
    const min = zakres.min * kursPin;
    const max = zakres.max * kursPin;
    const cel = Math.min(Math.max(kursCel, min * 1.05), max * 0.95);
    setKursCel(
      Math.min(
        meczId != null ? 12 : 30,
        Math.max(meczId != null ? 2 : 3, Math.round(cel * 2) / 2),
      ),
    );
    setPokazany(false);
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
    <div className="overflow-hidden rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card)">
      <div className="grid lg:grid-cols-[1.3fr_1fr]">
      {/* KONSOLA — sterowanie krok po kroku */}
      <div className="p-4 sm:p-5 [&>*+*]:mt-5 [&>*+*]:border-t [&>*+*]:border-hairline [&>*+*]:pt-5">
      {mostInfo && (
        <p className="flex items-start justify-between gap-3 rounded-(--radius-control) border border-brand/25 bg-brand-wash/50 px-3 py-2.5 text-xs leading-relaxed text-brand-deep">
          {mostInfo}
          <button
            onClick={() => setMostInfo(null)}
            className="shrink-0 text-brand-deep/60 transition-colors hover:text-brand-deep"
            aria-label="zamknij"
          >
            ✕
          </button>
        </p>
      )}
      {/* wybór meczów — tylko w wersji pełnej (/kupony) */}
      {meczId == null && (
        <div>
          <div className="flex items-baseline justify-between gap-2">
            <p className="flex items-baseline gap-2 text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
              <span aria-hidden className="font-data text-[10px] text-brand/70">01</span>
              mecze
            </p>
            {wybrane.size > 0 ? (
              <button
                onClick={() => { setWybrane(new Set()); setPokazany(false); }}
                className="text-xs text-brand hover:underline"
              >
                wyczyść ({wybrane.size})
              </button>
            ) : (
              <span className="text-[10px] text-faint">wszystkie</span>
            )}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {mecze.map(([id, { label, ts }]) => {
              const on = wybrane.has(id);
              return (
                <button
                  key={id}
                  onClick={() => toggleMecz(id)}
                  title={fmtDataCzas(ts)}
                  aria-pressed={on}
                  className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1.5 text-xs transition-colors ${
                    on
                      ? "border-brand/50 bg-brand-wash font-semibold text-brand-deep"
                      : "border-hairline bg-card-soft font-medium text-muted hover:border-hairline-strong hover:text-ink"
                  }`}
                >
                  {on && (
                    <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-brand" />
                  )}
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* cel: kurs docelowy z dużym odczytem */}
      <div>
        <div className="flex items-baseline justify-between gap-2">
          <p className="flex items-baseline gap-2 text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
            <span aria-hidden className="font-data text-[10px] text-brand/70">
              {meczId == null ? "02" : "01"}
            </span>
            kurs docelowy
          </p>
          <p className="font-data text-xl font-bold leading-none text-ink">
            ×{fmtKurs(kursCel)}
          </p>
        </div>
        <input
          type="range"
          min={meczId != null ? 2 : 3}
          max={meczId != null ? 12 : 30}
          step={0.5}
          value={kursCel}
          onChange={(e) => { setKursCel(Number(e.target.value)); setPokazany(false); }}
          aria-label="Kurs docelowy"
          className="suwak mt-3 w-full cursor-pointer"
          style={{
            "--p": `${(((kursCel - (meczId != null ? 2 : 3)) / ((meczId != null ? 12 : 30) - (meczId != null ? 2 : 3))) * 100).toFixed(1)}%`,
          } as React.CSSProperties}
        />
        <p className="mt-1.5 text-[10px] text-faint">
          składamy w przedziale{" "}
          <span className="font-data">
            ×{fmtKurs(kursCel * 0.85)}–{fmtKurs(kursCel * 1.18)}
          </span>
        </p>
      </div>

      {/* liczba typów + tryb */}
      <div>
        <div className="flex items-baseline justify-between gap-2">
          <p className="flex items-baseline gap-2 text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
            <span aria-hidden className="font-data text-[10px] text-brand/70">
              {meczId == null ? "03" : "02"}
            </span>
            {trybDokladny ? "dokładnie typów" : "co najmniej typów"}
          </p>
          <p className="font-data text-xl font-bold leading-none text-ink">
            {liczbaTypow}
          </p>
        </div>
        <input
          type="range"
          min={2}
          max={8}
          step={1}
          value={liczbaTypow}
          onChange={(e) => { setLiczbaTypow(Number(e.target.value)); setPokazany(false); }}
          aria-label="Liczba typów"
          className="suwak mt-3 w-full cursor-pointer"
          style={{ "--p": `${(((liczbaTypow - 2) / 6) * 100).toFixed(1)}%` } as React.CSSProperties}
        />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <Segmented
            id="generator-tryb"
            opcje={[
              {
                kod: "conajmniej",
                label: "co najmniej",
                title: "Model może dołożyć więcej typów, jeśli to podnosi szansę",
              },
              {
                kod: "dokladnie",
                label: "dokładnie",
                title: "Kupon będzie miał dokładnie tyle typów",
              },
            ]}
            wartosc={trybDokladny ? "dokladnie" : "conajmniej"}
            onChange={(v) => { setTrybDokladny(v === "dokladnie"); setPokazany(false); }}
          />
          <span className="text-[10px] text-faint">
            {trybDokladny
              ? "kupon będzie miał dokładnie tyle typów"
              : "model może dołożyć więcej, jeśli to podnosi szansę"}
          </span>
        </div>
      </div>

      {/* profil */}
      <div>
        <p className="flex items-baseline gap-2 text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
          <span aria-hidden className="font-data text-[10px] text-brand/70">
            {meczId == null ? "04" : "03"}
          </span>
          charakter kuponu
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <Segmented
            id="generator-profil"
            opcje={PROFILE.map((pr) => ({
              kod: pr.kod,
              label: pr.label,
              title: pr.opis,
            }))}
            wartosc={profil}
            onChange={(v) => { setProfil(v); setPokazany(false); }}
          />
          <span className="text-[11px] text-faint">
            {PROFILE.find((pr) => pr.kod === profil)?.opis}
          </span>
        </div>
      </div>

      {/* bezpieczniki — przełączniki zamiast checkboxów */}
      <div className="space-y-3">
        <button
          role="switch"
          aria-checked={tylkoValue}
          onClick={() => { setTylkoValue(!tylkoValue); setPokazany(false); }}
          title={`Techniczne kryterium: typ z przewagą liczoną na ≥${MIN_LEG_EV}% i maks. 1 typ z meczu`}
          className="group flex w-full items-start gap-3 text-left"
        >
          <span
            aria-hidden
            className={`relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors ${
              tylkoValue ? "bg-brand" : "bg-hairline-strong group-hover:bg-ink/25"
            }`}
          >
            <span
              className={`absolute top-0.5 h-4 w-4 rounded-full bg-card shadow-(--shadow-card) transition-all ${
                tylkoValue ? "left-[18px]" : "left-0.5"
              }`}
            />
          </span>
          <span className="text-xs">
            <span className="font-medium text-ink">
              Tylko pewne typy z przewagą
            </span>
            <span className="block text-muted">
              Bukmacher płaci za nie więcej, niż powinien. Maks. 1 typ z meczu.
              Pula jest tu szersza niż w automatycznych kuponach value.
            </span>
          </span>
        </button>
        <button
          role="switch"
          aria-checked={tylkoValue || maxJedenZMeczu}
          disabled={tylkoValue}
          onClick={() => { setMaxJedenZMeczu(!maxJedenZMeczu); setPokazany(false); }}
          title="Ogranicza kupon do jednego typu z każdego meczu, niezależnie od opcji powyżej"
          className="group flex w-full items-start gap-3 text-left disabled:cursor-not-allowed"
        >
          <span
            aria-hidden
            className={`relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors ${
              tylkoValue || maxJedenZMeczu
                ? "bg-brand"
                : "bg-hairline-strong group-hover:bg-ink/25"
            } ${tylkoValue ? "opacity-40" : ""}`}
          >
            <span
              className={`absolute top-0.5 h-4 w-4 rounded-full bg-card shadow-(--shadow-card) transition-all ${
                tylkoValue || maxJedenZMeczu ? "left-[18px]" : "left-0.5"
              }`}
            />
          </span>
          <span className="text-xs">
            <span className={`font-medium ${tylkoValue ? "text-faint" : "text-ink"}`}>
              Nie więcej niż 1 typ z jednego meczu
            </span>
            <span className={`block ${tylkoValue ? "text-faint" : "text-muted"}`}>
              Typy z tego samego meczu często wygrywają albo przegrywają razem
              {tylkoValue ? " (już włączone powyżej)" : ""}.
            </span>
          </span>
        </button>
      </div>

      {/* własny wybór typów: przypnij z puli — resztę dobiera model */}
      <details className="group rounded-(--radius-control) border border-dashed border-hairline transition-colors open:border-solid open:bg-card-soft/50">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2.5 text-xs font-medium text-muted transition-colors hover:text-ink [&::-webkit-details-marker]:hidden">
          <span className="flex items-center gap-1.5">
            <PinIcon className="shrink-0 text-brand" />
            Chcę konkretne typy w kuponie
            {przypiete.size > 0 && (
              <span className="font-data ml-1 rounded-full bg-brand-wash px-1.5 py-0.5 text-[10px] font-semibold text-brand-deep">
                {przypiete.size}
              </span>
            )}
          </span>
          <svg
            aria-hidden
            width="12"
            height="12"
            viewBox="0 0 14 14"
            className="shrink-0 text-faint transition-transform group-open:rotate-180"
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
        <div className="space-y-3 px-3 pb-3">
          <p className="text-[11px] leading-relaxed text-faint">
            Kliknij linię, żeby typ na pewno wszedł do kuponu (drugi klik
            odpina). Kropka przy linii to szansa modelu: zielona pewna,
            bursztynowa środek, czerwona ryzyko.
          </p>
          {mecze.map(([mid, { label }]) => {
            const typyMeczu = pulaFiltrowana
              .filter((l) => l.mecz_id === mid && !wykluczone.has(legKey(l)))
              .sort((a, b) => b.p_model - a.p_model);
            if (typyMeczu.length === 0) return null;
            // wiersze zawodnik+rynek, linie jako przełączane pastylki —
            // czytelniej niż ściana chipów i skaluje się na sezon ligowy
            const wiersze: {
              klucz: string;
              podmiot: string;
              rynek: string;
              linie: LegPool[];
            }[] = [];
            for (const l of typyMeczu) {
              const kw = `${l.podmiot_id}-${l.rynek_kod}`;
              const w = wiersze.find((x) => x.klucz === kw);
              if (w) w.linie.push(l);
              else
                wiersze.push({
                  klucz: kw,
                  podmiot: l.podmiot,
                  rynek: l.rynek,
                  linie: [l],
                });
            }
            for (const w of wiersze) w.linie.sort((a, b) => a.linia - b.linia);
            return (
              <div key={mid}>
                <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-ink-soft">
                  {label}
                </p>
                <div className="max-h-72 divide-y divide-hairline/70 overflow-auto rounded-(--radius-control) border border-hairline bg-card">
                  {wiersze.map((w) => (
                    <div
                      key={w.klucz}
                      className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3 py-2"
                    >
                      <p className="min-w-0 flex-1 truncate text-xs">
                        <span className="font-semibold text-ink">
                          {w.podmiot}
                        </span>{" "}
                        <span className="text-muted">
                          {w.rynek.toLowerCase()}
                        </span>
                      </p>
                      <div className="flex flex-wrap items-center gap-1">
                        {w.linie.map((l) => {
                          const kx = legKey(l);
                          const pin = przypiete.has(kx);
                          const kropka =
                            l.p_model >= 0.65
                              ? "bg-data-green"
                              : l.p_model >= 0.5
                                ? "bg-data-amber"
                                : "bg-data-red";
                          return (
                            <button
                              key={kx}
                              onClick={() => przypnij(l)}
                              aria-pressed={pin}
                              title={`Szansa ${fmtProc(l.p_model)}${
                                pin ? ". Kliknij, żeby odpiąć" : ""
                              }`}
                              className={`font-data inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors ${
                                pin
                                  ? "border-brand bg-brand-wash font-semibold text-brand-deep"
                                  : "border-hairline bg-card-soft text-ink-soft hover:border-brand/50 hover:text-ink"
                              }`}
                            >
                              {pin ? (
                                <PinIcon className="shrink-0" />
                              ) : (
                                <span
                                  aria-hidden
                                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${kropka}`}
                                />
                              )}
                              {fmtLinia(l.linia)}+
                              <span className={pin ? "" : "text-muted"}>
                                @{fmtKurs(l.kurs)}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </details>

      {/* podsumowanie wyborów usera — widoczne też, gdy kupon się nie składa */}
      {(przypiete.size > 0 || wykluczone.size > 0) && (
        <div className="space-y-1.5 text-xs">
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

      </div>

      {/* PODGLĄD NA ŻYWO — prawa kolumna: osiągalność zanim klikniesz */}
      <div className="flex flex-col border-t border-hairline bg-card-soft/60 p-4 sm:p-5 lg:border-l lg:border-t-0">
        <p className="font-display flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-brand">
          <span
            aria-hidden
            className={`live-dot h-1.5 w-1.5 rounded-full ${
              podglad ? "bg-data-green" : "bg-data-amber"
            }`}
          />
          podgląd na żywo
        </p>

        {podglad ? (
          <div className="mt-4">
            <p className="text-[10px] uppercase tracking-wide text-faint">
              kurs łączny
            </p>
            <p className="font-data mt-1 text-[2rem] font-bold leading-none text-ink">
              ×{fmtKurs(podglad.kurs_laczny)}
            </p>
            <dl className="mt-4 space-y-2 border-t border-hairline pt-3 text-xs">
              <div className="flex items-baseline justify-between gap-2">
                <dt className="text-faint">szansa modelu</dt>
                <dd className="font-data font-semibold text-ink">
                  {fmtProc(podglad.p_model)}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-2">
                <dt className="text-faint">typów w kuponie</dt>
                <dd className="font-data font-semibold text-ink">
                  {podglad.legi.length}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-2">
                <dt className="flex items-baseline gap-1.5 text-faint">
                  z
                  <input
                    type="number"
                    min={1}
                    step={5}
                    value={stawka}
                    onChange={(e) => setStawka(Number(e.target.value))}
                    aria-label="Twoja stawka w złotych"
                    title="Twoja stawka. Zapamiętujemy ją dla wszystkich przeliczników"
                    className="font-data w-14 rounded-(--radius-control) border border-hairline bg-card px-1.5 py-0.5 text-xs text-ink"
                  />
                  zł robi się
                </dt>
                <dd className="font-data font-semibold text-ink">
                  {Math.round(podglad.kurs_laczny * stawka)} zł
                </dd>
              </div>
            </dl>
            <PasekSzansy p={podglad.p_model} className="mt-4" />
          </div>
        ) : (
          <div className="mt-4">
            <p className="text-sm font-semibold text-ink">
              Ten zestaw się nie składa
            </p>
            <p className="mt-1.5 text-xs leading-relaxed text-muted">
              {podpowiedzBrak}
            </p>
            <button
              onClick={dopasujKurs}
              className="mt-3 rounded-(--radius-control) border border-brand/40 bg-brand-wash px-3 py-1.5 text-xs font-semibold text-brand-deep transition-colors hover:bg-brand-wash/70"
              title="Ustawia kurs docelowy w widełkach osiągalnych z obecnej puli i ustawień"
            >
              dopasuj kurs do puli
            </button>
          </div>
        )}

        <button
          onClick={zloz}
          disabled={!podglad}
          className="font-display mt-5 w-full rounded-(--radius-control) bg-brand px-4 py-3 text-sm font-semibold uppercase tracking-wide text-on-brand shadow-(--shadow-card) transition-colors hover:bg-brand-strong disabled:cursor-not-allowed disabled:bg-card disabled:text-faint disabled:shadow-none lg:mt-auto"
        >
          {meczId != null ? "Złóż kupon na ten mecz" : "Złóż kupon"}
        </button>
      </div>
      </div>

      {/* wynik — karta pokazuje ŻYWY podgląd: usunięcie/przypięcie typu
          przelicza kupon od razu, bez ponownego klikania "Złóż kupon" */}
      {pokazany && (
        <div className="border-t border-hairline px-4 pb-4 sm:px-5">
          <AnimatePresence mode="wait">
            {!podglad ? (
              <motion.p
                key="brak"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="mt-4 rounded-(--radius-control) border border-data-amber/40 bg-data-amber-wash px-3 py-2.5 text-xs text-data-amber-ink"
              >
                {podpowiedzBrak ?? "Nie da się domknąć tego kompletu. Zmień parametry."}
              </motion.p>
            ) : (
              <KuponKarta
                key="kupon"
                k={podglad}
                nauka={nauka}
                stawka={stawka}
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
      )}
    </div>
  );
}

function KuponKarta({
  k,
  nauka,
  stawka,
  tylkoValue,
  przypieteKeys,
  onOdrzuc,
  onNauka,
  onPrzypnij,
  onUsun,
}: {
  k: KuponWynik;
  nauka: "idle" | "wysylanie" | "ok" | "blad";
  stawka: number;
  tylkoValue: boolean;
  przypieteKeys: ReadonlyMap<string, LegPool>;
  onOdrzuc: () => void;
  onNauka: () => void;
  onPrzypnij: (l: LegPool) => void;
  onUsun: (l: LegPool) => void;
}) {
  const zwrot = (stawka * k.kurs_laczny).toFixed(0);
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
            {" · "}z {stawka} zł robi się{" "}
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
