"use client";

import { useState } from "react";

import { fmtKurs, fmtLinia } from "@/lib/format";
import { silaTypu } from "@/lib/slownik";

import type { TypV } from "../../_dane/przygotuj";
import { LogoBuk, procent, Ptaszek, ZnakBuk } from "./wspolne";

/* ======================================================================
   2.1 KAFELEK KURSU
   ====================================================================== */

export type StanKursu = {
  kurs: number | null;
  bukmacher: string;
  wybrany?: boolean;
  zmiana?: "gora" | "dol";
};

function Strzalka({ kier }: { kier?: "gora" | "dol" }) {
  if (!kier) return null;
  return (
    <span className="a-kurs-zmiana" data-kier={kier} aria-label={kier === "gora" ? "kurs wzrósł" : "kurs spadł"}>
      {kier === "gora" ? "▲" : "▼"}
    </span>
  );
}

export function KafelekKursu({
  wariant,
  s,
  onClick,
}: {
  wariant: string;
  s: StanKursu;
  onClick?: () => void;
}) {
  const liczba = s.kurs ? fmtKurs(s.kurs) : "–";
  const wspolne = {
    type: "button" as const,
    "data-wybrany": s.wybrany ? "true" : undefined,
    "data-brak": s.kurs ? undefined : "true",
    onClick,
    "aria-pressed": !!s.wybrany,
    title: s.kurs ? `${s.bukmacher} · kurs ${liczba}` : "brak kursu",
  };
  const ptaszek = s.wybrany && (
    <span className="a-kurs-ptaszek">
      <Ptaszek rozmiar={9} />
    </span>
  );

  if (wariant === "a") {
    return (
      <button className="a-kurs a-kurs-a" {...wspolne}>
        <LogoBuk nazwa={s.bukmacher} wysokosc={14} />
        <span className="a-kurs-liczba">
          {liczba}
          <Strzalka kier={s.zmiana} />
        </span>
        {ptaszek}
      </button>
    );
  }
  if (wariant === "c") {
    return (
      <button className="a-kurs a-kurs-c" {...wspolne}>
        <ZnakBuk nazwa={s.bukmacher} />
        <span className="a-kurs-liczba">{liczba}</span>
        <Strzalka kier={s.zmiana} />
        {ptaszek}
      </button>
    );
  }
  return (
    <button className="a-kurs a-kurs-b" {...wspolne}>
      <LogoBuk nazwa={s.bukmacher} wysokosc={15} />
      <span className="a-kurs-liczba">
        <Strzalka kier={s.zmiana} />
        {liczba}
      </span>
      {ptaszek}
    </button>
  );
}

export function ScenaKursu({ wariant, typy }: { wariant: string; typy: TypV[] }) {
  const [wybrane, setWybrane] = useState<Set<number>>(new Set([typy[0]?.id]));
  const przelacz = (id: number) =>
    setWybrane((w) => {
      const n = new Set(w);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const bazowy = typy[0];
  const stany: [string, StanKursu][] = [
    ["zwykły", { kurs: bazowy.kurs, bukmacher: "Superbet" }],
    ["w kuponie", { kurs: bazowy.kurs, bukmacher: "Superbet", wybrany: true }],
    ["Betclic płaci więcej", { kurs: bazowy.kurs + 0.06, bukmacher: "Betclic" }],
    ["kurs wzrósł", { kurs: bazowy.kurs + 0.04, bukmacher: "Superbet", zmiana: "gora" }],
    ["kurs spadł", { kurs: bazowy.kurs - 0.05, bukmacher: "Superbet", zmiana: "dol" }],
    ["brak kursu", { kurs: null, bukmacher: "Superbet" }],
  ];

  return (
    <>
      <div className="a-scena">
        <div className="a-podpis">w wierszu typu – kliknij kurs, żeby dodać do kuponu</div>
        {typy.map((t) => (
          <div key={t.id} className="a-typ">
            <div style={{ minWidth: 0 }}>
              <div className="a-typ-kto">{t.kto}</div>
              <div className="a-typ-co">
                {t.rynek.toLowerCase()} {t.strona === "ponizej" ? "poniżej" : "powyżej"} {fmtLinia(t.linia)}
              </div>
            </div>
            <KafelekKursu
              wariant={wariant}
              s={{ kurs: t.kurs, bukmacher: t.bukmacher, wybrany: wybrane.has(t.id) }}
              onClick={() => przelacz(t.id)}
            />
          </div>
        ))}
      </div>
      <div className="a-scena">
        <div className="a-podpis">wszystkie stany</div>
        <div className="a-rzad" style={{ alignItems: "flex-start" }}>
          {stany.map(([opis, s]) => (
            <div key={opis} style={{ display: "grid", gap: 8, justifyItems: "start" }}>
              <KafelekKursu wariant={wariant} s={s} />
              <span className="p-t3" style={{ fontSize: 11 }}>
                {opis}
              </span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

/* ======================================================================
   2.2 SZANSA
   ====================================================================== */

export function Szansa({
  wariant,
  p,
  kurs,
  duza = true,
}: {
  wariant: string;
  p: number;
  kurs: number;
  duza?: boolean;
}) {
  const rozmiar = duza ? 36 : 22;
  const sila = silaTypu(p);

  if (wariant === "b") {
    // cena bukmachera jako szansa (1/kurs, z marżą) – znacznik na torze
    const cena = Math.min(1 / kurs, 0.99);
    return (
      <div className="a-tor" style={{ width: duza ? 220 : 150 }}>
        <div className="a-szansa-liczba" style={{ fontSize: rozmiar }}>
          {procent(p)}
        </div>
        <div className="a-tor-pasek" role="img" aria-label={`nasza szansa ${procent(p)}, kurs zakłada ${procent(cena)}`}>
          <div className="a-tor-wypelnienie" style={{ width: `${p * 100}%` }} />
          <div className="a-tor-znacznik" style={{ left: `calc(${cena * 100}% - 1px)` }} />
        </div>
        {duza && (
          <div className="a-tor-opis">
            <span>nasza szansa</span>
            <span>
              kurs zakłada <b>{procent(cena)}</b>
            </span>
          </div>
        )}
      </div>
    );
  }

  if (wariant === "c") {
    const pelne = Math.round(p * 10);
    return (
      <div>
        <div className="a-szansa-liczba" style={{ fontSize: rozmiar }}>
          {procent(p)}
        </div>
        <div className="a-kreski" role="img" aria-label={`${pelne} na 10`}>
          {Array.from({ length: 10 }, (_, i) => (
            <i key={i} data-pelna={i < pelne ? "true" : undefined} />
          ))}
        </div>
        {duza && <div className="a-szansa-slowo">wchodzi ~{pelne} razy na 10</div>}
      </div>
    );
  }

  return (
    <div>
      <div className="a-szansa-liczba" style={{ fontSize: rozmiar }}>
        {procent(p)}
      </div>
      <div className="a-szansa-slowo">{sila.label}</div>
    </div>
  );
}

export function ScenaSzansy({ wariant, typy }: { wariant: string; typy: TypV[] }) {
  return (
    <>
      <div className="a-scena">
        <div className="a-podpis">duża – na karcie typu</div>
        <div className="a-rzad" style={{ gap: 36, alignItems: "flex-start" }}>
          {typy.map((t) => (
            <div key={t.id} style={{ display: "grid", gap: 10 }}>
              <Szansa wariant={wariant} p={t.szansa} kurs={t.kurs} />
              <span className="p-t3" style={{ fontSize: 12 }}>
                {t.kto} · {t.rynek.toLowerCase()}
              </span>
            </div>
          ))}
        </div>
      </div>
      <div className="a-scena">
        <div className="a-podpis">mała – w gęstym wierszu listy</div>
        {typy.map((t) => (
          <div key={t.id} className="a-typ">
            <div style={{ minWidth: 0 }}>
              <div className="a-typ-kto">{t.kto}</div>
              <div className="a-typ-co">
                {t.rynek.toLowerCase()} {t.strona === "ponizej" ? "poniżej" : "powyżej"} {fmtLinia(t.linia)}
              </div>
            </div>
            <Szansa wariant={wariant} p={t.szansa} kurs={t.kurs} duza={false} />
          </div>
        ))}
      </div>
    </>
  );
}
