"use client";

import { useId, useState } from "react";

import { fmtKurs } from "@/lib/format";

import type { HistoriaKuponow as Dane, KuponHistorii } from "../../_dane/kuponyHistoria";
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
  const stan =
    k.wynik === "w_grze"
      ? `w grze · weszło ${weszlo}, czeka ${k.nogi.length - rozstrzygniete}`
      : k.wynik === "anulowany"
        ? "anulowany – zmieniły się składy"
        : `weszło ${weszlo} z ${k.nogi.length}`;
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

export function HistoriaKuponow({ dane }: { dane: Dane }) {
  const [wszystkie, setWszystkie] = useState(false);
  const widoczne = wszystkie ? dane.kupony : dane.kupony.slice(0, NA_START);
  return (
    <section className="hk" aria-labelledby="hk-tytul">
      <div className="st-h2-z-opisem">
        <h2 id="hk-tytul" className="st-h2 p-n">
          Kupony od modelu
        </h2>
        <p>Model co dzień sam składa kilka kuponów z typów z listy. Każdy zostaje w historii – także te, które nie weszły.</p>
      </div>
      {dane.bilans.length > 0 && (
        <div className="hk-bilans">
          {dane.bilans.map((b) => (
            <div key={b.nazwa} className="sk-kafel">
              <small>{b.nazwa}</small>
              <b>
                {b.wygrane} z {b.n}
              </b>
              <span>{Math.round((b.wygrane / b.n) * 100)}% weszło</span>
            </div>
          ))}
        </div>
      )}
      <div className="sk-lista hk-lista">
        {widoczne.map((k) => (
          <Kupon key={k.klucz} k={k} />
        ))}
      </div>
      <div className="hk-stopka">
        {dane.kupony.length > NA_START && (
          <button type="button" className="a-guzik" data-t="drugi" data-r="m" onClick={() => setWszystkie((w) => !w)}>
            {wszystkie ? "Pokaż mniej" : `Pokaż wszystkie z 3 tygodni (${dane.kupony.length})`}
          </button>
        )}
        <Lnk href="/model" className="hk-link">
          Pojedyncze typy dzień po dniu – w Wynikach <span className="d-strzalka">→</span>
        </Lnk>
      </div>
    </section>
  );
}
