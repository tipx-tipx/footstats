"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useId, useState } from "react";

import { fmtLinia } from "@/lib/format";

import type { KartaV, Powod } from "../../_dane/elementy";
import { KafelekD, KratkiD, SzansaD } from "../atomy2/podstawowe";
import { Herb } from "../Herb";
import { IkonaRynku } from "./ikonyRynkow";

const strona = (s: string) => (s === "ponizej" ? "poniżej" : "powyżej");

function Chevron() {
  return (
    <svg className="el-chevron" width="14" height="14" viewBox="0 0 14 14" aria-hidden>
      <path d="m3.5 5.5 3.5 3.5 3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IkonaPowodu({ kier }: { kier: Powod["kier"] }) {
  if (kier === "za") {
    return (
      <svg width="10" height="10" viewBox="0 0 12 12" aria-hidden>
        <path d="M6 9.5v-7M3 5.5l3-3 3 3" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (kier === "przeciw") {
    return (
      <svg width="10" height="10" viewBox="0 0 12 12" aria-hidden>
        <path d="M6 2.5v7M3 6.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  return (
    <svg width="10" height="10" viewBox="0 0 12 12" aria-hidden>
      <circle cx="6" cy="6" r="2.2" fill="currentColor" />
    </svg>
  );
}

export function Powody({ powody, ile }: { powody: Powod[]; ile?: number }) {
  const lista = ile ? powody.slice(0, ile) : powody;
  return (
    <div className="el-powody">
      {lista.map((p, i) => (
        <motion.div
          key={i}
          className="el-powod"
          data-kier={p.kier}
          initial={{ opacity: 0, x: -4 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.05 + i * 0.05, duration: 0.25 }}
        >
          <i>
            <IkonaPowodu kier={p.kier} />
          </i>
          <span>{p.tekst}</span>
        </motion.div>
      ))}
    </div>
  );
}

/** „Skąd ta liczba” – ten sam środek we wszystkich wariantach karty */
function SkadTaLiczba({ t }: { t: KartaV }) {
  const za = t.powody.filter((p) => p.kier === "za").length;
  const przeciw = t.powody.filter((p) => p.kier === "przeciw").length;
  return (
    <div style={{ display: "grid", gap: 14 }}>
      {t.historia.length > 0 && <KratkiD t={t} />}
      <div>
        <div className="el-podsumowanie-powodow" style={{ marginBottom: 8 }}>
          <span>
            za: <b className="za">{za}</b>
          </span>
          <span>
            przeciw: <b className="przeciw">{przeciw}</b>
          </span>
        </div>
        <Powody powody={t.powody} />
      </div>
    </div>
  );
}

function Meta({ t }: { t: KartaV }) {
  return (
    <div className="el-karta-meta">
      <Herb d={t.druzyna} tryb="prawdziwy" rozmiar={15} />
      <span>{t.mecz}</span>
      <time>
        {t.dzien}, {t.godzina}
      </time>
    </div>
  );
}

function Rozwin({ otwarty, children }: { otwarty: boolean; children: React.ReactNode }) {
  return (
    <AnimatePresence initial={false}>
      {otwarty && (
        <motion.div
          className="el-rozwin"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* A · wiersz rozwijany – gęsta lista, szczegóły po kliknięciu */
export function KartaA({ t, otwarta = false, bezMeczu = false }: { t: KartaV; otwarta?: boolean; bezMeczu?: boolean }) {
  const [otwarty, setOtwarty] = useState(otwarta);
  const id = useId();
  return (
    <article className="el-karta">
      <div
        className="el-wiersz"
        role="button"
        tabIndex={0}
        aria-expanded={otwarty}
        aria-controls={id}
        onClick={() => setOtwarty((o) => !o)}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setOtwarty((o) => !o))}
      >
        <Herb d={t.druzyna} tryb="prawdziwy" rozmiar={20} />
        {/* 01.10: rodzaj zakładu na pierwszym planie – ikona rynku, nazwa rynku
            i próg największe w wierszu; kto i kiedy – pomocniczo */}
        <div style={{ minWidth: 0 }}>
          <div className="a-typ-kto" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {t.kto}
          </div>
          <div className="el-zaklad-wiersz">
            <IkonaRynku rynek={t.rynek} />
            <b>{t.rynek.replace(/\s*drużyny\s*/, " ").trim()}</b>
            <span>{strona(t.strona)}</span>
            <strong>{fmtLinia(t.linia)}</strong>
          </div>
          {!bezMeczu && (
            <div className="el-wiersz-meta">
              {t.mecz} · {t.dzien} {t.godzina}
            </div>
          )}
        </div>
        <SzansaD p={t.szansa} mala />
        <span onClick={(e) => e.stopPropagation()}>
          <KafelekD k={{ kurs: t.kurs, bukmacher: t.bukmacher }} />
        </span>
        <Chevron />
      </div>
      <Rozwin otwarty={otwarty}>
        <div className="el-rozwin-wnetrze" id={id}>
          <SkadTaLiczba t={t} />
        </div>
      </Rozwin>
    </article>
  );
}

/* B · karta pełna – wszystko najważniejsze od razu, szczegóły pod spodem */
export function KartaB({ t }: { t: KartaV }) {
  const [otwarty, setOtwarty] = useState(false);
  const glowny = t.powody.find((p) => p.kier === "za");
  return (
    <article className="el-karta el-karta-b">
      <Meta t={t} />
      <div className="el-karta-b-glowa">
        <div style={{ minWidth: 0 }}>
          <h3 className="el-kto">{t.kto}</h3>
          <div className="el-kto-pod">
            {t.pozycja}
            {t.podmiotTyp === "zawodnik" ? ` · ${t.druzyna.nazwa}` : ""}
          </div>
        </div>
        <SzansaD p={t.szansa} />
      </div>
      <div className="el-karta-b-zaklad">
        <div className="el-zaklad">
          {t.rynek} <span>{strona(t.strona)}</span> {fmtLinia(t.linia)}
        </div>
        <KafelekD k={{ kurs: t.kurs, bukmacher: t.bukmacher }} />
      </div>
      <KratkiD t={t} />
      {glowny && (
        <div className="el-najwazniejsze">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
            <path d="M6 9.5v-7M3 5.5l3-3 3 3" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>{glowny.tekst}</span>
        </div>
      )}
      <button type="button" className="el-skad" aria-expanded={otwarty} onClick={() => setOtwarty((o) => !o)}>
        Skąd ta liczba
        <Chevron />
      </button>
      <Rozwin otwarty={otwarty}>
        <div style={{ paddingTop: 4 }}>
          <Powody powody={t.powody} />
        </div>
      </Rozwin>
    </article>
  );
}

/* C · powody na wierzchu – karta mówi „dlaczego”, zanim ktoś zapyta */
function KartaC({ t }: { t: KartaV }) {
  const [wszystkie, setWszystkie] = useState(false);
  const za = t.powody.filter((p) => p.kier !== "przeciw");
  const przeciw = t.powody.filter((p) => p.kier === "przeciw");
  const pokaz = wszystkie ? [...za, ...przeciw] : za.slice(0, 3);
  return (
    <article className="el-karta el-karta-c">
      <Meta t={t} />
      <div className="el-karta-c-glowa">
        <Herb d={t.druzyna} tryb="prawdziwy" rozmiar={28} />
        <div style={{ minWidth: 0 }}>
          <h3 className="el-kto" style={{ fontSize: 18 }}>
            {t.kto}
          </h3>
          <div className="a-typ-co">
            {t.rynek.toLowerCase()} {strona(t.strona)} {fmtLinia(t.linia)}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <SzansaD p={t.szansa} mala />
          <KafelekD k={{ kurs: t.kurs, bukmacher: t.bukmacher }} />
        </div>
      </div>
      <Powody powody={pokaz} />
      {(przeciw.length > 0 || za.length > 3) && (
        <button type="button" className="a-guzik" data-t="cichy" data-r="s" style={{ justifySelf: "start", marginLeft: -12 }} onClick={() => setWszystkie((w) => !w)}>
          {wszystkie ? "Mniej" : przeciw.length ? `Co przemawia przeciw (${przeciw.length})` : "Więcej powodów"}
          <span aria-expanded={wszystkie} style={{ display: "inline-flex" }}>
            <Chevron />
          </span>
        </button>
      )}
      <KratkiD t={t} />
    </article>
  );
}

export function ScenaKarty({ wariant, karty }: { wariant: string; karty: KartaV[] }) {
  return (
    <div>
      {karty.map((t, i) =>
        wariant === "b" ? <KartaB key={t.id} t={t} /> : wariant === "c" ? <KartaC key={t.id} t={t} /> : <KartaA key={t.id} t={t} otwarta={i === 0} />,
      )}
    </div>
  );
}
