"use client";

import { useTeraz } from "../czas";
import { motion } from "framer-motion";

import type { MeczE } from "../../_dane/elementy";
import { KafelekD, SzansaD } from "../atomy2/podstawowe";
import { FlagaLigi, Herb } from "../Herb";

const odm = (n: number) => (n === 1 ? "typ" : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? "typy" : "typów");

function Strzalka() {
  return (
    <svg className="el-strzalka" width="12" height="12" viewBox="0 0 12 12" aria-hidden>
      <path d="M4.5 2.5 8 6 4.5 9.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** mecze pogrupowane po rozgrywkach, w kolejności pierwszego meczu */
function grupuj(mecze: MeczE[]) {
  const m = new Map<string, MeczE[]>();
  for (const x of mecze) m.set(x.liga, [...(m.get(x.liga) ?? []), x]);
  return [...m.entries()];
}

export function GlowaLigi({ mecze }: { mecze: MeczE[] }) {
  const l = mecze[0];
  return (
    <div className="el-liga-glowa">
      <FlagaLigi flaga={l.ligaFlaga} id={l.ligaId} c1={l.ligaC1} c2={l.ligaC2} tryb="prawdziwy" />
      <b>{l.liga}</b>
      <span>{l.kategoria}</span>
      <em>
        {mecze.length} {mecze.length === 1 ? "mecz" : "mecze"}
      </em>
    </div>
  );
}


export function Odliczanie({ ts }: { ts: number }) {
  const TERAZ = useTeraz();
  const min = Math.round((ts - TERAZ) / 60);
  if (min > 180 || min < 0) return null;
  const tekst = min < 60 ? `za ${min} min` : `za ${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")}`;
  return <small className="el-wkrotce">{tekst}</small>;
}

function Koszulka() {
  return (
    <svg width="13" height="13" viewBox="0 0 14 14" aria-hidden>
      <path d="M5 2 2 3.6 3 6.4l1.2-.5V12h5.6V5.9l1.2.5 1-2.8L9 2c-.3.9-1 1.4-2 1.4S5.3 2.9 5 2Z" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  );
}

/* A · lista (dopracowana 01.10): czas z odliczaniem | drużyny | szansa + kropki typów */
export function WierszA({ m, wybierz, wybrany, prawa }: { m: MeczE; wybierz?: () => void; wybrany?: boolean; prawa?: React.ReactNode }) {
  const TERAZ = useTeraz();
  const najwyzsza = Math.round(Math.max(...m.szanse, m.najlepszy?.p ?? 0) * 100);
  return (
    <div
      className="el-mecz-a"
      role="link"
      tabIndex={0}
      data-wybrany={wybrany || undefined}
      onClick={wybierz}
      onKeyDown={(e) => {
        if (wybierz && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          wybierz();
        }
      }}
      aria-label={`${m.gosp.nazwa} – ${m.gosc.nazwa}, ${m.godzina}, ${m.okazje} ${odm(m.okazje)}`}
    >
      <div className="el-czas">
        {m.godzina}
        <Odliczanie ts={m.ts} />
        {!(m.ts - TERAZ <= 10800 && m.ts > TERAZ) && <small>{m.dzien}</small>}
      </div>
      <div className="el-druzyny">
        <div className="el-druzyna">
          <Herb d={m.gosp} tryb="prawdziwy" />
          <span>{m.gosp.nazwa}</span>
        </div>
        <div className="el-druzyna">
          <Herb d={m.gosc} tryb="prawdziwy" />
          <span>{m.gosc.nazwa}</span>
        </div>
      </div>
      {/* 01.10: kropki były niejasne i dublowały liczbę – dwie rzeczy słowami:
          ile typów i jaki najmocniejszy */}
      {prawa ?? (
      <div className="el-typy-meczu">
        <b>
          {m.sklady && (
            <span className="el-sklady" title="Składy ogłoszone">
              <Koszulka />
            </span>
          )}
          {m.okazje} {odm(m.okazje)}
        </b>
        {najwyzsza > 0 ? (
          <span>
            najmocniejszy <strong>{najwyzsza}%</strong>
          </span>
        ) : (
          <span>zobacz typy</span>
        )}
      </div>
      )}
      <Strzalka />
    </div>
  );
}

/* B · z najmocniejszym typem na wierzchu – wiersz od razu „sprzedaje” mecz */
function WierszB({ m }: { m: MeczE }) {
  const n = m.najlepszy!;
  return (
    <div className="el-mecz-b">
      <div className="el-mecz-b-glowa">
        <Herb d={m.gosp} tryb="prawdziwy" rozmiar={16} />
        <span className="el-nazwa">{m.gosp.nazwa}</span>
        <span className="el-vs">–</span>
        <Herb d={m.gosc} tryb="prawdziwy" rozmiar={16} />
        <span className="el-nazwa">{m.gosc.nazwa}</span>
        <span className="el-godz">
          {m.dzien}, {m.godzina}
        </span>
      </div>
      <div className="el-mecz-b-typ">
        <div style={{ minWidth: 0 }}>
          <div className="a-typ-kto" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {n.kto}
          </div>
          <div className="a-typ-co" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {n.opis}
          </div>
        </div>
        <SzansaD p={n.p} mala />
        <KafelekD k={{ kurs: n.kurs, bukmacher: n.bukmacher }} />
      </div>
      {m.okazje > 1 && (
        <div className="el-mecz-b-stopka">
          <span>najmocniejszy z {m.okazje} typów w tym meczu</span>
          <b style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            wszystkie typy <Strzalka />
          </b>
        </div>
      )}
    </div>
  );
}

/* C · kafle: przegląd „co dziś gramy” */
function Kafel({ m, i }: { m: MeczE; i: number }) {
  const najwyzsza = Math.round(Math.max(...m.szanse) * 100);
  return (
    <motion.div
      className="el-kafel"
      role="link"
      tabIndex={0}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: i * 0.04, duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="el-kafel-glowa">
        <FlagaLigi flaga={m.ligaFlaga} id={m.ligaId} c1={m.ligaC1} c2={m.ligaC2} tryb="prawdziwy" />
        <span>{m.liga}</span>
        <b>
          {m.dzien}, {m.godzina}
        </b>
      </div>
      <div className="el-kafel-druzyny">
        <div className="el-kafel-druzyna">
          <Herb d={m.gosp} tryb="prawdziwy" rozmiar={34} />
          {m.gosp.nazwa}
        </div>
        <span className="el-kafel-vs">–</span>
        <div className="el-kafel-druzyna">
          <Herb d={m.gosc} tryb="prawdziwy" rozmiar={34} />
          {m.gosc.nazwa}
        </div>
      </div>
      <div className="el-kafel-stopka">
        <span>
          <b>{m.okazje}</b> {odm(m.okazje)} · do <b>{najwyzsza}%</b>
        </span>
        <span className="el-mini-szanse" aria-hidden>
          {m.szanse.slice(0, 6).map((p, j) => (
            // wysokość: 40% szansy = 3 px, 80% = pełne 18 px – różnice mają być widoczne
            <i key={j} style={{ height: `${Math.round(3 + Math.min(Math.max((p - 0.4) / 0.4, 0), 1) * 15)}px` }} data-mocny={p >= 0.7 ? "true" : undefined} />
          ))}
        </span>
      </div>
    </motion.div>
  );
}

export function ScenaMeczu({ wariant, mecze }: { wariant: string; mecze: MeczE[] }) {
  if (wariant === "c") {
    return (
      <div className="el-kafle">
        {mecze.map((m, i) => (
          <Kafel key={m.id} m={m} i={i} />
        ))}
      </div>
    );
  }
  return (
    <div>
      {grupuj(mecze).map(([liga, lista]) => (
        <section key={liga} className="el-liga">
          <GlowaLigi mecze={lista} />
          {lista.map((m) => (wariant === "b" ? <WierszB key={m.id} m={m} /> : <WierszA key={m.id} m={m} />))}
        </section>
      ))}
    </div>
  );
}
