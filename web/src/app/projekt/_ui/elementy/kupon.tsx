"use client";

import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useState } from "react";

import { fmtKurs } from "@/lib/format";

import type { KuponV } from "../../_dane/elementy";
import type { TypLekki } from "../../_dane/przygotuj";
import { Krzyzyk } from "../atomy/wspolne";
import { Blysk } from "../atomy/wyniki-ruch";
import { KafelekD, SzansaD } from "../atomy2/podstawowe";

type W = "ok" | "nie" | "czeka" | null;

const zl = (v: number) => `${v.toFixed(2).replace(".", ",")} zł`;
const odm = (n: number) => (n === 1 ? "typ" : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? "typy" : "typów");
const horyzont = (h: string) => (h === "dzienny" ? "na dziś" : "na kilka dni");

/** przykładowe rozliczenie do podglądu stanów: pierwsze nogi weszły, reszta czeka */
function statusy(k: KuponV, rozlicz: boolean): W[] {
  if (!rozlicz) return k.nogi.map(() => null);
  return k.nogi.map((_, i) => (i < Math.ceil(k.nogi.length / 2) ? "ok" : "czeka"));
}

/* A · bilet */
function Bilet({ k, rozlicz }: { k: KuponV; rozlicz: boolean }) {
  const st = statusy(k, rozlicz);
  return (
    <article className="el-bilet">
      <div className="el-bilet-glowa">
        <div className="el-bilet-cel">
          <b>×{fmtKurs(k.kurs)}</b>
          <span>
            kupon {horyzont(k.horyzont)}
            <br />
            {k.nogi.length} {odm(k.nogi.length)}
          </span>
        </div>
        <div className="el-pasek-szansy" role="img" aria-label={`szansa ${Math.round(k.p * 100)}%`}>
          <i style={{ width: `${k.p * 100}%` }} />
        </div>
        <div className="el-bilet-wyplata">
          <span>szansa {Math.round(k.p * 100)}%</span>
          <span>
            10 zł → <b>{zl(10 * k.kurs)}</b>
          </span>
        </div>
      </div>
      <div className="el-perforacja" aria-hidden />
      <div className="el-nogi">
        {k.nogi.map((n, i) => (
          <div key={i} className="el-noga">
            <span className="el-status" data-w={st[i] ?? undefined} aria-label={st[i] ?? "przed meczem"} />
            <div style={{ minWidth: 0 }}>
              <div className="el-noga-kto">
                {n.kto}
                {i === k.najslabszy && <span className="el-najslabszy">najsłabsze ogniwo</span>}
              </div>
              <div className="el-noga-co">{n.opis}</div>
            </div>
            <div className="el-noga-kurs">
              {fmtKurs(n.kurs)}
              <small>
                {n.dzien} {n.godzina}
              </small>
            </div>
          </div>
        ))}
      </div>
      <div className="el-bilet-info">
        <span>
          składy {k.sklady}/{k.mecze}
        </span>
        <span>kursy Superbet</span>
      </div>
      <div className="el-bilet-stopka">
        <button type="button" className="a-guzik" data-t="glowny" data-r="m">
          Gram ten kupon
        </button>
        <button type="button" className="a-guzik" data-t="drugi" data-r="m">
          Zmień
        </button>
      </div>
    </article>
  );
}

/* B · oś meczów: kupon rozpisany w czasie – widać, kiedy gra każda noga */
function Os({ k, rozlicz }: { k: KuponV; rozlicz: boolean }) {
  const st = statusy(k, rozlicz);
  return (
    <article className="el-karta el-os">
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10 }}>
        <div>
          <div className="el-bilet-cel">
            <b style={{ font: "700 28px/1 var(--f-n)" }}>×{fmtKurs(k.kurs)}</b>
          </div>
          <div className="a-typ-co" style={{ marginTop: 4 }}>
            kupon {horyzont(k.horyzont)} · szansa {Math.round(k.p * 100)}%
          </div>
        </div>
        <div style={{ textAlign: "right", fontSize: 13, color: "var(--t2)" }}>
          10 zł →<br />
          <b style={{ color: "var(--t1)", fontSize: 16 }}>{zl(10 * k.kurs)}</b>
        </div>
      </div>
      <div className="el-os-linia">
        {k.nogi.map((n, i) => (
          <motion.div
            key={i}
            className="el-os-punkt"
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.06, duration: 0.3 }}
          >
            <span className="el-os-godz">
              {n.godzina}
              <small>{n.dzien}</small>
            </span>
            <span className="el-os-kropka" data-w={st[i] ?? undefined} />
            <div className="el-os-noga">
              <div style={{ minWidth: 0 }}>
                <div className="el-noga-kto">{n.kto}</div>
                <div className="el-noga-co">{n.opis}</div>
              </div>
              <span className="el-noga-kurs">{fmtKurs(n.kurs)}</span>
            </div>
          </motion.div>
        ))}
      </div>
      <button type="button" className="a-guzik" data-t="glowny" data-r="m">
        Gram ten kupon
      </button>
    </article>
  );
}

/* C · kompakt – do list wielu kuponów */
function Kompakt({ k, rozlicz }: { k: KuponV; rozlicz: boolean }) {
  const st = statusy(k, rozlicz);
  return (
    <article className="el-karta el-kompakt">
      <div className="el-kompakt-glowa">
        <b>×{fmtKurs(k.kurs)}</b>
        <span>
          {k.nogi.length} {odm(k.nogi.length)} · szansa {Math.round(k.p * 100)}%
        </span>
        <button type="button" className="a-guzik" data-t="drugi" data-r="s">
          Gram
        </button>
      </div>
      <div className="el-kompakt-nogi">
        {k.nogi.map((n, i) => (
          <div key={i} className="el-kompakt-noga">
            <span className="el-status" data-w={st[i] ?? undefined} />
            <span>
              {n.kto} <small>{n.opis}</small>
            </span>
            <b>{fmtKurs(n.kurs)}</b>
          </div>
        ))}
      </div>
    </article>
  );
}

export function ScenaKuponu({ wariant, kupony }: { wariant: string; kupony: KuponV[] }) {
  const [rozlicz, setRozlicz] = useState(false);
  return (
    <div>
      <div className="el-kupony">
        {kupony.map((k, i) =>
          wariant === "b" ? <Os key={i} k={k} rozlicz={rozlicz} /> : wariant === "c" ? <Kompakt key={i} k={k} rozlicz={rozlicz} /> : <Bilet key={i} k={k} rozlicz={rozlicz} />,
        )}
      </div>
      <button type="button" className="a-demo-guzik" onClick={() => setRozlicz((r) => !r)}>
        {rozlicz ? "Przed meczami" : "Pokaż w trakcie (część rozliczona)"}
      </button>
    </div>
  );
}

/* ======================================================================
   3.5 TWÓJ KUPON – koszyk budowany kliknięciami w kursy
   ====================================================================== */

const KWOTY = [10, 20, 50, 100];

export function ScenaKoszyka({ typy, telefon }: { typy: TypLekki[]; telefon: boolean }) {
  const lista = typy.slice(0, 6);
  const [wybrane, setWybrane] = useState<number[]>([lista[0].id, lista[2].id]);
  const [stawka, setStawka] = useState(10);
  const [otwarty, setOtwarty] = useState(false);
  const w = lista.filter((t) => wybrane.includes(t.id));
  const kurs = w.reduce((k, t) => k * t.kurs, 1);
  const szansa = w.reduce((p, t) => p * t.p, 1);
  const [poprzedni, setPoprzedni] = useState(kurs);

  const przelacz = (id: number) => {
    setPoprzedni(kurs);
    setWybrane((x) => (x.includes(id) ? x.filter((y) => y !== id) : [...x, id]));
  };

  const zawartosc = (
    <>
      <div className="el-koszyk-glowa">
        <b className="p-n" style={{ fontSize: 17 }}>
          Twój kupon
        </b>
        {w.length > 0 && (
          <button type="button" className="a-guzik" data-t="cichy" data-r="s" onClick={() => setWybrane([])}>
            Wyczyść
          </button>
        )}
      </div>
      {w.length === 0 ? (
        <div className="el-koszyk-pusty">Kliknij kurs przy typie, żeby dodać go do kuponu.</div>
      ) : (
        <>
          <LayoutGroup>
            <AnimatePresence initial={false}>
              {w.map((t) => (
                <motion.div
                  key={t.id}
                  layout
                  className="el-koszyk-noga"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.22 }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div className="el-noga-kto">{t.kto}</div>
                    <div className="el-noga-co">{t.opis}</div>
                  </div>
                  <span className="el-noga-kurs">{fmtKurs(t.kurs)}</span>
                  <button type="button" className="el-usun" aria-label={`Usuń ${t.kto}`} onClick={() => przelacz(t.id)}>
                    <Krzyzyk rozmiar={9} />
                  </button>
                </motion.div>
              ))}
            </AnimatePresence>
          </LayoutGroup>
          <div className="el-stawka">
            <div className="el-stawka-wiersz">
              <span>kurs łączny</span>
              <b>
                <Blysk tekst={`×${fmtKurs(kurs)}`} kier={kurs === poprzedni ? null : kurs > poprzedni ? "gora" : "dol"} />
              </b>
            </div>
            <div className="el-stawka-wiersz">
              <span>szansa, że wejdzie cały</span>
              <span style={{ color: "var(--t1)", fontWeight: 600 }}>{Math.round(szansa * 100)}%</span>
            </div>
            <div className="el-kwoty" role="radiogroup" aria-label="Stawka">
              {KWOTY.map((k) => (
                <button key={k} type="button" className="el-kwota" aria-pressed={stawka === k} onClick={() => setStawka(k)}>
                  {k} zł
                </button>
              ))}
            </div>
            <div className="el-stawka-wiersz">
              <span>możliwa wygrana</span>
              <b>{zl(stawka * kurs)}</b>
            </div>
            <button type="button" className="a-guzik" data-t="glowny" data-r={telefon ? "l" : "m"} style={{ width: "100%" }}>
              Zapisz kupon
            </button>
            <p style={{ color: "var(--t3)", fontSize: 11, textAlign: "center" }}>Kupon stawiasz u bukmachera. My liczymy szanse.</p>
          </div>
        </>
      )}
    </>
  );

  return (
    <div className="el-koszyk-scena" style={telefon ? { gridTemplateColumns: "1fr" } : undefined}>
      <div className="el-koszyk-lista">
        {lista.map((t) => (
          <div key={t.id} className="e-wiersz">
            <div style={{ minWidth: 0 }}>
              <div className="a-typ-kto" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {t.kto}
              </div>
              <div className="a-typ-co" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {t.opis}
              </div>
            </div>
            <SzansaD p={t.p} mala />
            <KafelekD k={{ kurs: t.kurs, bukmacher: t.bukmacher }} wybrany={wybrane.includes(t.id)} onClick={() => przelacz(t.id)} />
          </div>
        ))}
        {telefon && <div style={{ height: 70 }} />}
      </div>

      {!telefon && <aside className="el-koszyk-panel">{zawartosc}</aside>}

      {telefon && (
        <>
          <AnimatePresence>
            {w.length > 0 && !otwarty && (
              <motion.button
                type="button"
                className="el-pastylka"
                onClick={() => setOtwarty(true)}
                initial={{ y: 80, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                exit={{ y: 80, opacity: 0 }}
                transition={{ type: "spring", stiffness: 380, damping: 32 }}
              >
                <motion.span key={w.length} className="el-pastylka-licznik" initial={{ scale: 1.4 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 500, damping: 18 }}>
                  {w.length}
                </motion.span>
                <b>×{fmtKurs(kurs)}</b>
                <span>{zl(stawka * kurs)}</span>
                <span className="el-pastylka-guzik">Kupon</span>
              </motion.button>
            )}
          </AnimatePresence>
          <AnimatePresence>
            {otwarty && (
              <>
                <motion.div key="tlo" className="d-panel-tlo" onClick={() => setOtwarty(false)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
                <motion.div
                  key="arkusz"
                  className="d-panel"
                  data-tryb="arkusz"
                  role="dialog"
                  aria-label="Twój kupon"
                  style={{ display: "block", overflowY: "auto" }}
                  initial={{ y: "100%" }}
                  animate={{ y: 0 }}
                  exit={{ y: "100%" }}
                  transition={{ type: "spring", stiffness: 380, damping: 38 }}
                  drag="y"
                  dragConstraints={{ top: 0, bottom: 0 }}
                  dragElastic={{ top: 0, bottom: 0.6 }}
                  onDragEnd={(_, info) => {
                    if (info.offset.y > 90) setOtwarty(false);
                  }}
                >
                  <div className="d-uchwyt" aria-hidden />
                  {zawartosc}
                </motion.div>
              </>
            )}
          </AnimatePresence>
        </>
      )}
      {!telefon && w.length > 0 && (
        <p className="p-t3" style={{ fontSize: 12, gridColumn: "1 / -1" }}>
          Na telefonie ten panel zamienia się w pastylkę przyklejoną do dołu ekranu (przełącz „Telefon” u góry).
        </p>
      )}
    </div>
  );
}
