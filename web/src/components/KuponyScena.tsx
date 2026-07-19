"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";

import { KuponBilet } from "./KuponBilet";
import { akcjaKuponu, ProfilKuponow, ZastosujZamiane } from "./PominKupon";
import { useStawka } from "./useStawka";
import { fmtKurs, fmtLinia, fmtProc, STRONA_LABEL } from "@/lib/format";
import {
  addKuponZagrany,
  isKuponZagrany,
  removeKuponZagranyPoKluczu,
} from "@/lib/kuponyTracker";
import type { Kupon } from "@/lib/types";

/**
 * Scena kuponów: zamiast katalogu 10 biletów naraz — decyzja w trzech
 * krokach. 1) zakres (na dziś / na kilka dni / value), 2) cel na osi
 * ryzyka (kurs + szansa pod każdym punktem), 3) JEDEN bilet na scenie
 * z werdyktem po ludzku i akcjami. Mechanika slotów pipeline'u zostaje
 * pod maską: pusty przedział to wygaszony punkt osi, nie martwa karta.
 */

type Zakres = "dzienny" | "dlugoterminowy" | "value";

const ZAKRESY: { kod: Zakres; label: string; opis: string }[] = [
  {
    kod: "dzienny",
    label: "Na dziś",
    opis: "Mecze z dzisiaj (a gdy gra mało drużyn, także z jutra).",
  },
  {
    kod: "dlugoterminowy",
    label: "Na kilka dni",
    opis: "Typy rozłożone na 1–4 dni: model wybiera z pełnej puli, więc jakość typów jest najwyższa.",
  },
  {
    kod: "value",
    label: "Value",
    opis: "Tylko typy, za które bukmacher płaci ponad ich uczciwy kurs. Trafia rzadziej, ale przy serii matematyka gra dla Ciebie.",
  },
];

const PRZEDZIALY: Record<Zakres, string[]> = {
  dzienny: ["5–10", "10–15", "15–20", "20–25"],
  dlugoterminowy: ["10–15", "15–20", "20–25", "25–35"],
  value: ["4–8", "8–16"],
};

const POWODY = ["nie zagrałem", "słaby zestaw", "za niski kurs"] as const;

function celKuponu(k: Kupon): string {
  return k.cel_label ?? String(k.cel);
}

/** „~1 na N prób" z szansy kuponu. */
function razNa(p: number): number {
  return Math.max(2, Math.round(1 / Math.max(p, 1e-9)));
}

/**
 * Werdykt jako odczyt instrumentu: rubryki z etykietami zamiast ściany
 * akapitów. Liczby wyciągnięte do przodu (font-data), ostrzeżenia w
 * bursztynie danych, reszta spokojnym tekstem.
 */
function Werdykt({ kupon: k }: { kupon: Kupon }) {
  const meczeIds = [...new Set(k.legi.map((l) => l.mecz_id))];
  const jedenMecz = meczeIds.length === 1;
  const skladyPelne =
    k.mecze_ze_skladami != null &&
    k.mecze_lacznie != null &&
    k.mecze_ze_skladami >= k.mecze_lacznie;

  return (
    <dl className="divide-y divide-hairline border-y border-hairline">
      <div className="grid grid-cols-[68px_1fr] gap-3 py-3">
        <dt className="pt-0.5 text-[10px] font-semibold uppercase tracking-wide text-faint">
          zestaw
        </dt>
        <dd className="text-sm leading-relaxed text-muted">
          {k.styl === "value" ? (
            <>
              <strong className="font-semibold text-ink">Value</strong>: każdy
              typ płaci więcej, niż wynosi jego uczciwa cena.
              {jedenMecz ? "" : ` Typy z ${meczeIds.length} różnych meczów.`}
            </>
          ) : (
            <>
              <strong className="font-semibold text-ink">Pewniaki</strong>:
              najpewniejsze typy, które razem domykają kurs ×{celKuponu(k)}.{" "}
              {jedenMecz
                ? "Wszystkie z jednego meczu, szansa liczona z karą za wspólny mecz."
                : `Rozłożone na ${meczeIds.length} mecze.`}
            </>
          )}
        </dd>
      </div>

      <div className="grid grid-cols-[68px_1fr] gap-3 py-3">
        <dt className="pt-1 text-[10px] font-semibold uppercase tracking-wide text-faint">
          szansa
        </dt>
        <dd className="text-sm leading-relaxed text-muted">
          <span className="font-data text-xl font-bold leading-none text-ink">
            {fmtProc(k.p_model)}
          </span>{" "}
          na komplet, czyli ~1 trafienie na{" "}
          <strong className="font-data font-semibold text-ink">
            {razNa(k.p_model)}
          </strong>{" "}
          takich prób. Graj stawką, którą spokojnie postawisz wiele razy z
          rzędu.
        </dd>
      </div>

      {k.styl === "value" && k.ev_pct > 0 && (
        <div className="grid grid-cols-[68px_1fr] gap-3 py-3">
          <dt className="pt-0.5 text-[10px] font-semibold uppercase tracking-wide text-faint">
            przewaga
          </dt>
          <dd className="text-sm leading-relaxed text-muted">
            Uczciwa cena tego kompletu to{" "}
            <strong className="font-data font-semibold text-ink">
              ×{fmtKurs(k.fair_kurs)}
            </strong>
            , a bukmacher płaci{" "}
            <strong className="font-data font-semibold text-data-green">
              ×{fmtKurs(k.kurs_laczny)}
            </strong>
            . To jest cała przewaga tego kuponu.
          </dd>
        </div>
      )}

      {k.mecze_lacznie != null && k.mecze_ze_skladami != null && (
        <div className="grid grid-cols-[68px_1fr] gap-3 py-3">
          <dt className="pt-0.5 text-[10px] font-semibold uppercase tracking-wide text-faint">
            składy
          </dt>
          <dd className="text-sm leading-relaxed text-muted">
            <strong
              className={`font-data font-semibold ${
                skladyPelne ? "text-ink" : "text-data-amber-ink"
              }`}
            >
              {k.mecze_ze_skladami}/{k.mecze_lacznie}
            </strong>{" "}
            meczów z potwierdzonymi XI przy budowie.
            {!skladyPelne && (
              <span className="text-data-amber-ink">
                {" "}
                Typy z niepotwierdzonych składów mogą wylecieć po ogłoszeniu
                XI.
              </span>
            )}
          </dd>
        </div>
      )}
    </dl>
  );
}

/** Zwijana strefa dopracowania: wymiana, inny wariant, dobicie kursu. */
function Dopracuj({ kupon: k }: { kupon: Kupon }) {
  const propozycje = [k.alternatywa, k.dolozenie, k.wariant_b].filter(
    Boolean,
  ).length;
  if (propozycje === 0) return null;
  return (
    <details className="group mt-4 overflow-hidden rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card)">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted transition-colors hover:text-ink [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-2">
          dopracuj ten kupon
          <span className="font-data rounded-full bg-brand-wash px-1.5 py-0.5 text-[10px] font-semibold tracking-normal text-brand-deep">
            {propozycje}
          </span>
        </span>
        <svg
          aria-hidden
          width="12"
          height="12"
          viewBox="0 0 14 14"
          className="shrink-0 transition-transform group-open:rotate-180"
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

      {k.alternatywa && (
        <div className="border-t border-dashed border-brand/30 bg-brand-wash/40 px-4 py-3.5">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-brand">
            mocniejsza wersja tego kuponu
          </p>
          <p className="mt-1.5 text-sm leading-relaxed">
            <span className="text-muted line-through decoration-data-red/50">
              {k.legi[k.alternatywa.zamiast_idx]?.podmiot}{" "}
              {k.legi[k.alternatywa.zamiast_idx]?.rynek.toLowerCase()}{" "}
              {fmtLinia(k.legi[k.alternatywa.zamiast_idx]?.linia ?? 0)}
            </span>{" "}
            → <strong>{k.alternatywa.podmiot}</strong>{" "}
            <span className="text-muted">
              {k.alternatywa.rynek.toLowerCase()}{" "}
              {STRONA_LABEL[k.alternatywa.strona]} {fmtLinia(k.alternatywa.linia)}
            </span>{" "}
            <span className="font-data font-semibold">
              @{fmtKurs(k.alternatywa.kurs)}
            </span>
          </p>
          <p className="font-data mt-1 text-xs text-muted">
            szansa {fmtProc(k.p_model)} →{" "}
            <strong className="text-brand-deep">
              {fmtProc(k.alternatywa.p_po)}
            </strong>{" "}
            · kurs {fmtKurs(k.kurs_laczny)} → {fmtKurs(k.alternatywa.kurs_po)}
          </p>
          <ZastosujZamiane klucz={k.klucz} />
        </div>
      )}

      {k.dolozenie && (
        <div className="border-t border-dashed border-hairline bg-card-soft/70 px-4 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted">
            dobij kurs pewnym typem
          </p>
          <p className="mt-1 text-sm leading-relaxed">
            <strong>{k.dolozenie.podmiot}</strong>{" "}
            <span className="text-muted">
              {k.dolozenie.rynek.toLowerCase()} {STRONA_LABEL[k.dolozenie.strona]}{" "}
              {fmtLinia(k.dolozenie.linia)}
            </span>{" "}
            <span className="font-data font-semibold">
              @{fmtKurs(k.dolozenie.kurs)}
            </span>
          </p>
          <p className="font-data mt-1 text-xs text-muted">
            kurs {fmtKurs(k.kurs_laczny)} → {fmtKurs(k.dolozenie.kurs_po)} ·
            szansa {fmtProc(k.p_model)} → {fmtProc(k.dolozenie.p_po)}
          </p>
        </div>
      )}

      {k.wariant_b && (
        <div className="border-t border-dashed border-hairline px-4 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted">
            inny wariant: kurs {fmtKurs(k.wariant_b.kurs_laczny)}, szansa{" "}
            {fmtProc(k.wariant_b.p_model)}
          </p>
          <div className="mt-1.5 space-y-1">
            {k.wariant_b.legi.map((l, wi) => (
              <p
                key={`${l.mecz_id}-${l.value_bet_id}-${wi}`}
                className="flex items-baseline justify-between gap-2 text-xs"
              >
                <span className="min-w-0 truncate">
                  <strong>{l.podmiot}</strong>{" "}
                  <span className="text-muted">
                    {l.rynek.toLowerCase()} {STRONA_LABEL[l.strona]}{" "}
                    {fmtLinia(l.linia)} · {l.mecz}
                  </span>
                </span>
                <span className="font-data shrink-0">{fmtKurs(l.kurs)}</span>
              </p>
            ))}
            <p className="pt-1 text-[10px] text-faint">
              wariant podglądowy. Jeśli wolisz ten zestaw, zagraj go ręcznie
              (miejsce zajmuje wariant główny)
            </p>
          </div>
        </div>
      )}
    </details>
  );
}

export function KuponyScena({
  kupony,
  jestGenerator = false,
}: {
  kupony: Kupon[];
  /** czy na stronie jest sekcja generatora (#generator) — cel mostu „zmień" */
  jestGenerator?: boolean;
}) {
  const reduced = useReducedMotion();
  const [stawka, setStawka] = useStawka();
  const [zakres, setZakres] = useState<Zakres>(() => {
    for (const z of ZAKRESY) if (kupony.some((k) => (k.horyzont ?? "value") === z.kod)) return z.kod;
    return "dzienny";
  });

  const grupa = useMemo(
    () => kupony.filter((k) => (k.horyzont ?? "value") === zakres),
    [kupony, zakres],
  );
  const przedzialy = PRZEDZIALY[zakres];
  const pierwszyZajety = przedzialy.find((p) =>
    grupa.some((k) => celKuponu(k) === p),
  );
  const [cel, setCel] = useState<string | undefined>(pierwszyZajety);

  // zmiana zakresu przestawia cel na pierwszy istniejący kupon (bez efektu)
  const [prevZakres, setPrevZakres] = useState(zakres);
  if (prevZakres !== zakres) {
    setPrevZakres(zakres);
    setCel(pierwszyZajety);
  }

  const kupon = grupa.find((k) => celKuponu(k) === cel);

  // stany akcji sceny (per klucz kuponu, trwałość jak w PominKupon)
  const [stan, setStan] = useState<
    "aktywny" | "wybor" | "wysylam" | "pominiety" | "blad"
  >("aktywny");
  const [przebudowa, setPrzebudowa] = useState(false);
  const [zagrany, setZagrany] = useState(false);
  // panel stawki po kliknięciu „gram ten kupon" (zapis do Moich zakładów)
  const [gramPanel, setGramPanel] = useState(false);
  const [gramStawka, setGramStawka] = useState<string>("");

  useEffect(() => {
    setStan("aktywny");
    setPrzebudowa(false);
    setGramPanel(false);
    setZagrany(isKuponZagrany(kupon?.klucz));
    if (!kupon?.klucz) return;
    if (localStorage.getItem(`kupon-pominiety:${kupon.klucz}`)) setStan("pominiety");
    if (localStorage.getItem(`kupon-przebudowa:${kupon.klucz}`)) setPrzebudowa(true);
  }, [kupon?.klucz]);

  const pomin = async (powod: string) => {
    if (!kupon?.klucz) return;
    setStan("wysylam");
    try {
      await akcjaKuponu({ klucz: kupon.klucz, powod });
      localStorage.setItem(`kupon-pominiety:${kupon.klucz}`, String(Date.now()));
      setStan("pominiety");
    } catch {
      setStan("blad");
    }
  };

  const przywroc = async () => {
    if (!kupon?.klucz) return;
    setStan("wysylam");
    try {
      await akcjaKuponu({ klucz: kupon.klucz, akcja: "przywroc" });
      localStorage.removeItem(`kupon-pominiety:${kupon.klucz}`);
      setStan("aktywny");
    } catch {
      setStan("pominiety");
    }
  };

  const zaplanujPrzebudowe = async () => {
    if (!kupon?.klucz) return;
    try {
      await akcjaKuponu({ klucz: kupon.klucz, akcja: "przebuduj" });
      localStorage.setItem(`kupon-przebudowa:${kupon.klucz}`, String(Date.now()));
      setPrzebudowa(true);
    } catch {
      /* przycisk zostaje — można spróbować ponownie */
    }
  };

  const zapiszZagrany = () => {
    if (!kupon) return;
    const v = Number(gramStawka);
    const s = Number.isFinite(v) && v > 0 ? Math.round(v) : stawka;
    setStawka(s);
    addKuponZagrany(kupon, s);
    setZagrany(true);
    setGramPanel(false);
  };

  const cofnijZagrany = () => {
    if (!kupon?.klucz) return;
    removeKuponZagranyPoKluczu(kupon.klucz);
    setZagrany(false);
  };

  // most do generatora: przypnij typy tego kuponu i ustaw cel na jego kurs.
  // Typy identyfikujemy pełnym opisem (mecz+zawodnik+rynek+linia+strona),
  // bo id w puli generatora nie pokrywa się z value_bet_id legów kuponu
  const zmienWGeneratorze = () => {
    if (!kupon) return;
    window.dispatchEvent(
      new CustomEvent("footstats:kupon-edytuj", {
        detail: {
          legi: kupon.legi.map((l) => ({
            mecz_id: l.mecz_id,
            podmiot: l.podmiot,
            rynek: l.rynek,
            linia: l.linia,
            strona: l.strona,
          })),
          cel: kupon.kurs_laczny,
        },
      }),
    );
    // scroll po tym, jak generator przerenderuje się z przypiętymi typami
    setTimeout(() => {
      document
        .getElementById("generator")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 80);
  };

  const opisZakresu = ZAKRESY.find((z) => z.kod === zakres)?.opis;

  return (
    <section aria-label="Wybór kuponu">
      {/* krok 1: zakres — taby tekstowe jak na tablicy okazji */}
      <div
        className="flex flex-wrap items-end gap-x-6 gap-y-1 border-b border-hairline"
        role="tablist"
        aria-label="Zakres kuponów"
      >
        {ZAKRESY.map((z) => {
          const n = kupony.filter((k) => (k.horyzont ?? "value") === z.kod).length;
          const active = zakres === z.kod;
          return (
            <button
              key={z.kod}
              role="tab"
              aria-selected={active}
              onClick={() => setZakres(z.kod)}
              className={`font-display relative -mb-px inline-flex items-baseline gap-1.5 px-0.5 pb-2.5 pt-1 text-xs font-semibold uppercase tracking-wide transition-colors ${
                active ? "text-brand-deep" : "text-muted hover:text-ink"
              }`}
            >
              {active && (
                <motion.span
                  layoutId="kupony-zakres"
                  aria-hidden
                  transition={
                    reduced
                      ? { duration: 0 }
                      : { type: "spring", stiffness: 520, damping: 42 }
                  }
                  className="absolute inset-x-0 bottom-0 h-0.5 bg-brand"
                />
              )}
              {z.label}
              <span
                className={`font-data text-[11px] ${active ? "" : "text-faint"}`}
              >
                {n}
              </span>
            </button>
          );
        })}
      </div>
      {opisZakresu && (
        <p className="mt-2.5 max-w-2xl text-xs leading-relaxed text-muted">
          {opisZakresu}
        </p>
      )}

      {/* krok 2: cel na torze ryzyka — wszystko wyrównane do LEWEJ jak
          reszta strony: mnożnik, przystanek i szansa zaczynają się przy
          lewej krawędzi kolumny, szyna biegnie od przystanku w prawo */}
      <div
        className="mt-7 flex"
        role="radiogroup"
        aria-label="Cel kuponu (mnożnik stawki)"
      >
        {przedzialy.map((p, i) => {
          const k = grupa.find((x) => celKuponu(x) === p);
          const active = cel === p && !!k;
          const activeIdx = Math.max(przedzialy.indexOf(cel ?? ""), 0);
          const ostatni = i === przedzialy.length - 1;
          return (
            <button
              key={p}
              role="radio"
              aria-checked={active}
              disabled={!k}
              onClick={() => setCel(p)}
              title={
                k
                  ? `Kupon ×${p}: szansa ${fmtProc(k.p_model)}`
                  : "Kupon w tych widełkach powstanie, gdy pula typów pozwoli domknąć kurs (zwykle bliżej meczów)"
              }
              className={`group flex flex-col items-start pb-0.5 pt-0.5 text-left disabled:cursor-default ${
                ostatni ? "w-auto" : "w-[86px] sm:w-28"
              }`}
            >
              <span
                className={`font-data origin-left text-base font-bold leading-6 tracking-tight transition-[color,transform] duration-300 sm:text-lg ${
                  active
                    ? "scale-110 text-brand-deep"
                    : k
                      ? "text-ink-soft group-hover:text-ink"
                      : "text-faint/70"
                }`}
              >
                ×{p}
              </span>

              {/* szyna: przystanek przy lewej + odcinek do następnej kolumny */}
              <span
                aria-hidden
                className="relative mb-1.5 mt-1 flex h-[18px] w-full items-center"
              >
                {!ostatni && (
                  <span
                    className={`absolute left-[7px] right-0 h-1.5 transition-colors duration-500 ${
                      cel && i < activeIdx ? "bg-brand" : "bg-hairline"
                    }`}
                  />
                )}
                {active ? (
                  <motion.span
                    layoutId="os-cel-krazek"
                    transition={
                      reduced
                        ? { duration: 0 }
                        : { type: "spring", stiffness: 420, damping: 34 }
                    }
                    className="relative z-10 -ml-px flex h-[18px] w-[18px] items-center justify-center rounded-full border-[3px] border-brand bg-card shadow-(--shadow-card)"
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-brand" />
                  </motion.span>
                ) : (
                  <span
                    className={`relative z-10 ml-[3px] h-[10px] w-[10px] rounded-full border-2 transition-all duration-200 ${
                      k
                        ? "border-brand/50 bg-card group-hover:scale-125 group-hover:border-brand"
                        : "border-hairline-strong bg-paper"
                    }`}
                  />
                )}
              </span>

              <span className="flex items-baseline gap-1">
                <span
                  className={`font-data text-xs font-semibold leading-tight transition-colors ${
                    active ? "text-brand-deep" : k ? "text-muted" : "text-faint"
                  }`}
                >
                  {k ? fmtProc(k.p_model) : "· · ·"}
                </span>
                <span className="text-[9px] uppercase tracking-wide text-faint">
                  {k ? "szansa" : "bliżej meczów"}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      <ProfilKuponow />

      {/* krok 3: scena — jeden bilet + werdykt */}
      <div className="mt-6">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={`${zakres}-${cel ?? "brak"}-${stan === "pominiety" ? "pominiety" : "ok"}`}
            initial={reduced ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduced ? undefined : { opacity: 0, y: -8 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          >
            {!kupon ? (
              <div className="rounded-(--radius-card) border border-dashed border-hairline bg-card-soft/50 px-6 py-12 text-center">
                <p className="text-sm font-medium text-ink">
                  {grupa.length === 0
                    ? "W tym zakresie nie ma teraz kuponu"
                    : "Ten przedział czeka na kupon"}
                </p>
                <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted">
                  Kupon powstanie, gdy pula typów pozwoli domknąć kurs w tych
                  widełkach. Zwykle dzieje się to bliżej meczów.
                </p>
              </div>
            ) : stan === "pominiety" ? (
              <div className="rounded-(--radius-card) border border-dashed border-hairline bg-card-soft/60 px-6 py-10 text-center">
                <p className="text-sm font-medium text-ink">Kupon pominięty</p>
                <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-muted">
                  Model i tak rozliczy go w tle (do nauki). Nowy kupon w tym
                  przedziale pojawi się w kilka minut, o ile pula ma inny
                  sensowny zestaw.
                </p>
                <button
                  onClick={przywroc}
                  className="mt-3 rounded-(--radius-control) border border-hairline bg-card px-3 py-1.5 text-xs font-medium text-ink-soft shadow-(--shadow-card) transition-colors hover:bg-card-soft"
                >
                  Cofnij i przywróć kupon
                </button>
              </div>
            ) : (
              <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:gap-8">
                {/* lewa: bilet + akcje (min-w-0: treść biletu nie może
                    rozpychać kolumny gridu na wąskich ekranach) */}
                <div className="min-w-0">
                  <KuponBilet kupon={kupon} stawka={stawka} />

                  {przebudowa && (
                    <p className="mt-2 rounded-(--radius-control) bg-data-amber-wash px-2.5 py-1.5 text-[11px] leading-relaxed text-data-amber-ink">
                      zaplanowano przebudowę: gdy składy wszystkich meczów będą
                      potwierdzone, model złoży ten kupon od nowa na pewnych XI
                    </p>
                  )}

                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {zagrany ? (
                      <span className="inline-flex flex-wrap items-center gap-x-2.5 gap-y-1 rounded-(--radius-control) border border-data-green/40 bg-data-green-wash px-3.5 py-2 text-xs font-semibold text-data-green-ink">
                        ✓ zagrany
                        <a
                          href="/zaklady"
                          className="font-medium underline decoration-data-green/40 underline-offset-2 transition-colors hover:decoration-data-green"
                        >
                          zobacz w Moich zakładach
                        </a>
                        <button
                          onClick={cofnijZagrany}
                          className="font-normal text-data-green-ink/70 transition-colors hover:text-data-green-ink"
                          title="Usuwa wpis z Moich zakładów"
                        >
                          cofnij
                        </button>
                      </span>
                    ) : gramPanel ? (
                      <span className="flex flex-wrap items-center gap-2 rounded-(--radius-control) border border-hairline bg-card px-2.5 py-1.5 shadow-(--shadow-card)">
                        <label className="flex items-center gap-1.5 text-xs text-muted">
                          stawka
                          <input
                            type="number"
                            min={1}
                            step={5}
                            autoFocus
                            value={gramStawka}
                            onChange={(e) => setGramStawka(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") zapiszZagrany();
                              if (e.key === "Escape") setGramPanel(false);
                            }}
                            className="font-data w-16 rounded-(--radius-control) border border-hairline bg-card-soft px-2 py-1 text-sm text-ink"
                          />
                          zł
                        </label>
                        <button
                          onClick={zapiszZagrany}
                          className="font-display rounded-(--radius-control) bg-brand px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-on-brand transition-colors hover:bg-brand-strong"
                        >
                          zapisz
                        </button>
                        <button
                          onClick={() => setGramPanel(false)}
                          className="px-1 text-xs text-faint transition-colors hover:text-muted"
                          aria-label="anuluj"
                        >
                          ✕
                        </button>
                      </span>
                    ) : (
                      <button
                        onClick={() => {
                          setGramStawka(String(stawka));
                          setGramPanel(true);
                        }}
                        className="font-display inline-flex items-center gap-2 rounded-(--radius-control) bg-brand px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-on-brand shadow-(--shadow-card) transition-colors hover:bg-brand-strong"
                        title="Zapisuje kupon ze stawką w Moich zakładach. Wynik rozliczy się sam po meczach"
                      >
                        gram ten kupon
                      </button>
                    )}

                    {stan === "wybor" ? (
                      <span className="flex flex-wrap items-center gap-1.5 rounded-(--radius-control) border border-hairline bg-card px-2 py-1.5 shadow-(--shadow-card)">
                        <span className="pl-1 text-xs text-faint">
                          dlaczego pomijasz?
                        </span>
                        {POWODY.map((p) => (
                          <button
                            key={p}
                            onClick={() => pomin(p)}
                            className="rounded-md bg-card-soft px-2.5 py-1 text-xs font-medium text-ink-soft transition-colors hover:bg-data-red-wash hover:text-data-red-ink"
                          >
                            {p}
                          </button>
                        ))}
                        <button
                          onClick={() => setStan("aktywny")}
                          className="px-1.5 text-xs text-faint transition-colors hover:text-muted"
                          aria-label="anuluj pomijanie"
                        >
                          ✕
                        </button>
                      </span>
                    ) : (
                      kupon.klucz && (
                        <button
                          onClick={() => setStan("wybor")}
                          disabled={stan === "wysylam"}
                          className="rounded-(--radius-control) border border-hairline bg-card px-3.5 py-2.5 text-xs font-medium text-muted shadow-(--shadow-card) transition-colors hover:border-data-red/40 hover:text-data-red-ink disabled:text-faint"
                          title="Kupon zniknie i zwolni miejsce na nowy zestaw; w tle i tak się rozliczy, żeby model się uczył"
                        >
                          {stan === "blad"
                            ? "nie udało się, spróbuj ponownie"
                            : stan === "wysylam"
                              ? "pomijam…"
                              : "pomiń, pokaż inny"}
                        </button>
                      )
                    )}

                    {jestGenerator && stan !== "wybor" && (
                      <button
                        onClick={zmienWGeneratorze}
                        className="rounded-(--radius-control) border border-hairline bg-card px-3.5 py-2.5 text-xs font-medium text-muted shadow-(--shadow-card) transition-colors hover:border-brand/40 hover:text-brand-deep"
                        title="Otwiera budowanie własnego kuponu z typami tego kuponu już przypiętymi. Kupon modelu zostaje bez zmian, edytujesz swoją kopię"
                      >
                        zmień coś w tym kuponie
                      </button>
                    )}

                    {kupon.klucz &&
                      kupon.horyzont === "dzienny" &&
                      !przebudowa &&
                      stan !== "wybor" && (
                        <button
                          onClick={zaplanujPrzebudowe}
                          className="px-1 text-xs text-faint transition-colors hover:text-data-amber-ink"
                          title="Kupon zostanie złożony od nowa dopiero, gdy składy WSZYSTKICH jego meczów będą potwierdzone. Mniej zwrotów i anulowań"
                        >
                          przebuduj po składach
                        </button>
                      )}
                  </div>
                </div>

                {/* prawa: werdykt po ludzku + strefa dopracowania */}
                <div className="min-w-0 lg:pt-1">
                  <p className="font-display flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-brand">
                    <span aria-hidden className="h-px w-5 bg-brand-bright" />
                    dlaczego ten kupon
                  </p>
                  <div className="mt-3">
                    <Werdykt kupon={kupon} />
                  </div>
                  <Dopracuj kupon={kupon} />
                </div>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </section>
  );
}
