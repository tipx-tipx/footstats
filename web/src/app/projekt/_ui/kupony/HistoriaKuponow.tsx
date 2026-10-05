"use client";

import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { fmtKurs, odmien } from "@/lib/format";

import type { HistoriaKuponow as Dane, KuponHistorii, RodzajKuponu } from "../../_dane/kuponyHistoria";
import { Ptaszek } from "../atomy/wspolne";
import { PrzewijanyRzad } from "../atomy2/PrzewijanyRzad";
import { Chevron, Rozwin } from "../elementy/karta";
import { Lnk } from "../linki";

/*
 * Kupony od modelu – historia pod kreatorem (01.10). Ten sam słownik co Wyniki:
 * kafle bilansu, lista w ramce, znak ✓ ✕ ↺ po lewej, kurs po prawej; kreski
 * nóg jak w Kontroli. Wiersz rozwija nogi – każda z własnym wynikiem.
 */

const odm = (n: number) => (n === 1 ? "typ" : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? "typy" : "typów");
const NA_START = 8;

const ZNAK: Record<KuponHistorii["wynik"], string> = { wygrany: "✓", przegrany: "✕", anulowany: "↺", zwrot: "↺", w_grze: "" };
const OPIS: Record<KuponHistorii["wynik"], string> = { wygrany: "wszedł", przegrany: "nie wszedł", anulowany: "anulowany", zwrot: "zwrot", w_grze: "w grze" };

function Kupon({ k }: { k: KuponHistorii }) {
  const [otwarty, setOtwarty] = useState(false);
  const id = useId();
  const weszlo = k.nogi.filter((n) => n.wynik === "wygrany").length;
  const rozstrzygniete = k.nogi.filter((n) => n.wynik !== "czeka").length;
  const zwroty = k.nogi.filter((n) => n.wynik === "zwrot").length;
  const stan =
    k.wynik === "w_grze"
      ? `w grze · weszło ${weszlo}, czeka ${k.nogi.length - rozstrzygniete}`
      : k.wynik === "anulowany"
        ? "anulowany – zmieniły się składy"
        : `weszło ${weszlo} z ${k.nogi.length}${zwroty ? `, ${zwroty} ${odmien(zwroty, "zwrot", "zwroty", "zwrotów")}` : ""}`;
  return (
    <div className="hk-kupon" data-wynik={k.wynik}>
      <button type="button" className="hk-wiersz" aria-expanded={otwarty} aria-controls={id} onClick={() => setOtwarty((o) => !o)}>
        <span className="sk-znak hk-znak" aria-label={OPIS[k.wynik]}>
          {ZNAK[k.wynik]}
        </span>
        <span className="hk-tekst">
          <small>
            {k.dzien}
            {k.horyzont && ` · ${k.horyzont}`}
          </small>
          <span>
            <b>
              {k.nogi.length} {odm(k.nogi.length)}
            </b>
            <span className="hk-nogi" aria-hidden>
              {k.nogi.map((n, i) => (
                <i key={i} data-w={n.wynik} />
              ))}
            </span>
            <em>{stan}</em>
          </span>
        </span>
        <span className="hk-kurs">×{fmtKurs(k.kurs)}</span>
        <Chevron />
      </button>
      <Rozwin otwarty={otwarty}>
        <div className="hk-rozwin" id={id}>
          {k.nogi.map((n, i) => (
            <div key={i} className="hk-noga" data-wynik={n.wynik}>
              <span className="hk-noga-znak" aria-label={n.wynik === "wygrany" ? "weszło" : n.wynik === "przegrany" ? "nie weszło" : n.wynik === "zwrot" ? "zwrot" : "przed rozstrzygnięciem"}>
                {n.wynik === "wygrany" ? "✓" : n.wynik === "przegrany" ? "✕" : n.wynik === "zwrot" ? "↺" : ""}
              </span>
              <span className="sk-typ-tekst">
                <small>{n.kto}</small>
                <span>
                  <b>{n.rynek}</b> {n.strona} <strong>{n.linia}</strong>
                </span>
              </span>
              <span className="hk-noga-kurs">{fmtKurs(n.kurs)}</span>
            </div>
          ))}
        </div>
      </Rozwin>
    </div>
  );
}

type Status = "wszystkie" | "wygrany" | "przegrany" | "w_grze";
const STATUSY: [Status, string][] = [
  ["wszystkie", "Wszystkie"],
  ["wygrany", "Weszły"],
  ["przegrany", "Nie weszły"],
  ["w_grze", "W grze"],
];
type Sort = "najnowsze" | "kurs_w" | "kurs_n" | "nogi";
const SORTY: [Sort, string][] = [
  ["najnowsze", "Najnowsze"],
  ["kurs_w", "Najwyższy kurs"],
  ["kurs_n", "Najniższy kurs"],
  ["nogi", "Najwięcej typów"],
];
const SORTUJ: Record<Sort, (a: KuponHistorii, b: KuponHistorii) => number> = {
  najnowsze: (a, b) => a.nr - b.nr,
  kurs_w: (a, b) => b.kurs - a.kurs || a.nr - b.nr,
  kurs_n: (a, b) => a.kurs - b.kurs || a.nr - b.nr,
  nogi: (a, b) => b.nogi.length - a.nogi.length || a.nr - b.nr,
};

/** to samo menu co „Polecane” na liście typów */
function MenuSortu({ sort, ustaw }: { sort: Sort; ustaw: (s: Sort) => void }) {
  const [otwarte, setOtwarte] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!otwarte) return;
    const klik = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOtwarte(false);
    };
    const klaw = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOtwarte(false);
    };
    document.addEventListener("click", klik);
    document.addEventListener("keydown", klaw);
    return () => {
      document.removeEventListener("click", klik);
      document.removeEventListener("keydown", klaw);
    };
  }, [otwarte]);
  const etykieta = SORTY.find(([k]) => k === sort)?.[1];
  return (
    <span ref={ref} className="hk-sort">
      <button type="button" className="e-menu-guzik d-dotyk" aria-haspopup="menu" aria-expanded={otwarte} aria-label={`Sortuj: ${etykieta}`} onClick={() => setOtwarte((o) => !o)}>
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
          <path d="M4 2.5v9M1.8 9.3 4 11.5l2.2-2.2M10 11.5v-9M7.8 4.7 10 2.5l2.2 2.2" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="e-etykieta-sortu">{etykieta}</span>
      </button>
      <AnimatePresence>
        {otwarte && (
          <motion.div className="d-menu" role="menu" initial={{ opacity: 0, y: -4, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -4, scale: 0.98 }} transition={{ duration: 0.14 }}>
            {SORTY.map(([k, e]) => (
              <button
                key={k}
                type="button"
                role="menuitemradio"
                aria-checked={k === sort}
                onClick={() => {
                  ustaw(k);
                  setOtwarte(false);
                }}
              >
                {e}
                {k === sort && <Ptaszek rozmiar={11} />}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </span>
  );
}

export function HistoriaKuponow({ dane }: { dane: Dane }) {
  const [wszystkie, setWszystkie] = useState(false);
  const [rodzaj, setRodzaj] = useState<RodzajKuponu | "wszystkie">("wszystkie");
  const [status, setStatus] = useState<Status>("wszystkie");
  const [sort, setSort] = useState<Sort>("najnowsze");
  const idZakladek = useId();

  const zRodzaju = useMemo(() => dane.kupony.filter((k) => rodzaj === "wszystkie" || k.rodzaj === rodzaj), [dane, rodzaj]);
  const ile = useMemo(() => {
    const w: Record<Status, number> = { wszystkie: zRodzaju.length, wygrany: 0, przegrany: 0, w_grze: 0 };
    for (const k of zRodzaju) if (k.wynik === "wygrany" || k.wynik === "przegrany" || k.wynik === "w_grze") w[k.wynik]++;
    return w;
  }, [zRodzaju]);
  const lista = useMemo(() => zRodzaju.filter((k) => status === "wszystkie" || k.wynik === status).sort(SORTUJ[sort]), [zRodzaju, status, sort]);
  const widoczne = wszystkie ? lista : lista.slice(0, NA_START);

  return (
    <section className="hk" aria-labelledby="hk-tytul">
      <div className="st-h2-z-opisem">
        <h2 id="hk-tytul" className="st-h2 p-n">
          Kupony od modelu
        </h2>
        <p>Model co dzień sam składa kilka kuponów z typów z listy. Każdy zostaje w historii – także te, które nie weszły.</p>
      </div>
      {dane.bilans.length > 0 && (
        <div className="hk-bilans" role="group" aria-label="Rodzaj kuponów">
          {dane.bilans.map((b) => (
            <button
              key={b.klucz}
              type="button"
              className="sk-kafel hk-kafel"
              aria-pressed={rodzaj === b.klucz}
              onClick={() => {
                setRodzaj(b.klucz);
                setWszystkie(false);
              }}
            >
              <small>{b.nazwa}</small>
              <b>
                {b.wygrane} z {b.n}
              </b>
              <span>{Math.round((b.wygrane / b.n) * 100)}% weszło</span>
            </button>
          ))}
        </div>
      )}
      <div className="hk-pasek">
        <LayoutGroup id={idZakladek}>
          <PrzewijanyRzad className="f-rynki hk-statusy" role="tablist" ariaLabel="Wynik kuponu">
            {STATUSY.map(([k, e]) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={k === status}
                className="f-rynek"
                disabled={k !== "wszystkie" && ile[k] === 0}
                onClick={() => {
                  setStatus(k);
                  setWszystkie(false);
                }}
              >
                {e}
                <sup>{ile[k]}</sup>
                {k === status && <motion.span layoutId="kreska-hk" className="a-podkreslenie" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
              </button>
            ))}
          </PrzewijanyRzad>
        </LayoutGroup>
        <MenuSortu
          sort={sort}
          ustaw={(s) => {
            setSort(s);
            setWszystkie(false);
          }}
        />
      </div>
      {lista.length ? (
        <div className="sk-lista hk-lista">
          {widoczne.map((k) => (
            <Kupon key={k.klucz} k={k} />
          ))}
        </div>
      ) : (
        <div className="d-pusty">
          <div className="p-n" style={{ fontSize: 17 }}>
            Nic tu nie pasuje
          </div>
          <p>W tym widoku nie ma kuponów z ostatnich 3 tygodni.</p>
        </div>
      )}
      <div className="hk-stopka">
        {lista.length > NA_START && (
          <button type="button" className="a-guzik" data-t="drugi" data-r="m" onClick={() => setWszystkie((w) => !w)}>
            {wszystkie ? "Pokaż mniej" : `Pokaż wszystkie (${lista.length})`}
          </button>
        )}
        <Lnk href="/model" className="hk-link">
          Pojedyncze typy dzień po dniu – w Wynikach <span className="d-strzalka">→</span>
        </Lnk>
      </div>
    </section>
  );
}
