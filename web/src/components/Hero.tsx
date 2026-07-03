"use client";

import {
  animate,
  motion,
  useMotionValue,
  useReducedMotion,
  useTransform,
} from "framer-motion";
import Link from "next/link";
import { useEffect } from "react";

import { fmtKurs, fmtProc } from "@/lib/format";
import type { ValueBet } from "@/lib/types";

/** Licznik animowany od 0 do wartości (szanuje reduced-motion). */
function CountUp({
  value,
  suffix = "",
  decimals = 0,
}: {
  value: number;
  suffix?: string;
  decimals?: number;
}) {
  const reduced = useReducedMotion();
  const mv = useMotionValue(reduced ? value : 0);
  const text = useTransform(mv, (v) =>
    `${v.toFixed(decimals).replace(".", ",")}${suffix}`,
  );
  useEffect(() => {
    if (reduced) {
      mv.set(value);
      return;
    }
    const ctrl = animate(mv, value, { duration: 1.1, ease: [0.22, 1, 0.36, 1] });
    return () => ctrl.stop();
  }, [value, mv, reduced]);
  return <motion.span>{text}</motion.span>;
}

const wejscie = {
  hidden: { opacity: 0, y: 18 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: 0.08 * i, duration: 0.55, ease: [0.22, 1, 0.36, 1] as const },
  }),
};

export function Hero({
  liga,
  sezon,
  aktualizacja,
  okazje,
  wysokaPewnosc,
  najlepszaEv,
  mecze,
  topBet,
  liczbaSugestii,
}: {
  liga: string;
  sezon: string;
  aktualizacja: string;
  okazje: number;
  wysokaPewnosc: number;
  najlepszaEv: number | null;
  mecze: number;
  topBet: ValueBet | null;
  liczbaSugestii: number;
}) {
  const reduced = useReducedMotion();

  const kafelki = [
    { label: "okazje z kursem", value: okazje, suffix: "", green: false },
    { label: "z wysoką pewnością", value: wysokaPewnosc, suffix: "", green: false },
    ...(najlepszaEv != null
      ? [{ label: "najlepsza wartość", value: najlepszaEv, suffix: "%", green: true, plus: true, decimals: 1 }]
      : [{ label: "sugestie STS", value: liczbaSugestii, suffix: "", green: false }]),
    { label: "meczów w analizie", value: mecze, suffix: "", green: false },
  ];

  return (
    <section className="pitch-grid relative -mx-4 mb-8 overflow-hidden border-b border-hairline bg-card px-4 pb-10 pt-12 sm:-mx-6 sm:px-6">
      {/* miękka zielona poświata za nagłówkiem */}
      <div
        aria-hidden
        className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full opacity-50"
        style={{
          background:
            "radial-gradient(closest-side, rgb(22 88 63 / 0.10), transparent)",
        }}
      />

      <div className="relative mx-auto grid max-w-6xl items-center gap-10 lg:grid-cols-[1.25fr_1fr]">
        {/* lewa: przekaz */}
        <div>
          <motion.div
            variants={wejscie}
            initial={reduced ? false : "hidden"}
            animate="show"
            custom={0}
            className="flex flex-wrap items-center gap-3"
          >
            <p className="text-xs font-semibold uppercase tracking-widest text-brand">
              Skan rynków · {liga} {sezon}
            </p>
            <span
              className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-paper px-2.5 py-1 text-[11px] text-muted"
              title="Cykl w chmurze pobiera statystyki i kursy, przelicza model i odświeża tę stronę"
            >
              <span aria-hidden className="live-dot h-1.5 w-1.5 rounded-full bg-data-green" />
              żywe dane · aktualizacja{" "}
              <span className="font-data font-medium text-ink-soft">{aktualizacja}</span>
            </span>
          </motion.div>

          <motion.h1
            variants={wejscie}
            initial={reduced ? false : "hidden"}
            animate="show"
            custom={1}
            className="mt-4 max-w-xl text-4xl font-bold leading-[1.08] tracking-tight sm:text-5xl"
          >
            Gdzie kurs płaci{" "}
            <span className="relative inline-block text-brand">
              więcej, niż powinien
              <motion.span
                aria-hidden
                initial={reduced ? { scaleX: 1 } : { scaleX: 0 }}
                animate={{ scaleX: 1 }}
                transition={{ delay: 0.7, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
                className="absolute -bottom-1 left-0 h-[3px] w-full origin-left rounded-full bg-data-green/60"
              />
            </span>
          </motion.h1>

          <motion.p
            variants={wejscie}
            initial={reduced ? false : "hidden"}
            animate="show"
            custom={2}
            className="mt-4 max-w-xl text-[15px] leading-relaxed text-muted"
          >
            Model liczy prawdziwe szanse na strzały, faule czy odbiory — z
            historii zawodnika, przewidywanych składów, rywala i stron boiska.
            Potem porównuje je z kursami i zostawia tylko zakłady, w których
            bukmacher się przelicza.{" "}
            <Link
              href="/jak-to-dziala"
              className="font-medium text-brand underline-offset-2 hover:underline"
            >
              Jak to działa? →
            </Link>
          </motion.p>

          <motion.dl
            variants={wejscie}
            initial={reduced ? false : "hidden"}
            animate="show"
            custom={3}
            className="mt-7 grid max-w-xl grid-cols-2 gap-2.5 sm:grid-cols-4"
          >
            {kafelki.map((s) => (
              <div
                key={s.label}
                className="rounded-xl border border-hairline bg-card/80 px-3.5 py-3 shadow-(--shadow-card) backdrop-blur-sm transition-transform hover:-translate-y-0.5"
              >
                <dd
                  className={`font-data text-2xl font-semibold ${
                    s.green ? "text-data-green" : "text-ink"
                  }`}
                >
                  {"plus" in s && s.plus ? "+" : ""}
                  <CountUp value={s.value} suffix={s.suffix} decimals={("decimals" in s ? s.decimals : 0) as number} />
                </dd>
                <dt className="mt-0.5 text-[11px] leading-tight text-faint">{s.label}</dt>
              </div>
            ))}
          </motion.dl>
        </div>

        {/* prawa: spotlight — najciekawsza pozycja teraz */}
        <motion.div
          variants={wejscie}
          initial={reduced ? false : "hidden"}
          animate="show"
          custom={4}
        >
          {topBet ? (
            <Link
              href={topBet.sugestia ? "/?rodzaj=sugestie" : "/"}
              className="group block rounded-2xl border border-brand/25 bg-gradient-to-br from-brand-wash to-card p-6 shadow-(--shadow-card) transition-all hover:-translate-y-1 hover:shadow-(--shadow-card-hover)"
            >
              <p className="text-[11px] font-semibold uppercase tracking-widest text-brand">
                {topBet.sugestia ? "najmocniejsza sugestia STS" : "najlepsza okazja teraz"}
              </p>
              <p className="mt-3 text-xl font-bold leading-snug">
                {topBet.podmiot}
              </p>
              <p className="mt-0.5 text-sm text-muted">
                {topBet.rynek.toLowerCase()} powyżej{" "}
                {topBet.linia.toFixed(1).replace(".", ",")} · {topBet.mecz}
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2">
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-faint">szansa modelu</p>
                  <p className="font-data text-2xl font-semibold text-ink">
                    {fmtProc(topBet.p_model)}
                  </p>
                </div>
                {topBet.kurs != null ? (
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-faint">
                      kurs ({topBet.bukmacher})
                    </p>
                    <p className="font-data text-2xl font-semibold text-ink">
                      {fmtKurs(topBet.kurs)}
                    </p>
                  </div>
                ) : (
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-faint">
                      opłaca się od kursu
                    </p>
                    <p className="font-data text-2xl font-semibold text-ink">
                      ~{fmtKurs(topBet.fair_kurs * 1.05)}
                    </p>
                  </div>
                )}
                {topBet.ev_pct != null && (
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-faint">wartość</p>
                    <p className="font-data text-2xl font-semibold text-data-green">
                      +{topBet.ev_pct.toFixed(1).replace(".", ",")}%
                    </p>
                  </div>
                )}
              </div>
              <p className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-brand transition-transform group-hover:translate-x-0.5">
                zobacz szczegóły niżej →
              </p>
            </Link>
          ) : (
            <div className="rounded-2xl border border-hairline bg-card p-6 text-center shadow-(--shadow-card)">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-faint">
                stan rynku
              </p>
              <p className="mt-3 text-lg font-bold">Rynek wycenia blisko modelu</p>
              <p className="mx-auto mt-1.5 max-w-xs text-sm leading-relaxed text-muted">
                W tej chwili bukmacher nie przepłaca za żadne zdarzenie. Skan
                trwa — nowe kursy co ok. 30 minut.
              </p>
            </div>
          )}
        </motion.div>
      </div>
    </section>
  );
}
