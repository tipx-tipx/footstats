"use client";

import { useTeraz } from "../czas";
import { LayoutGroup, motion } from "framer-motion";
import { useId, useMemo, useState } from "react";

import type { MeczE } from "../../_dane/elementy";
import type { DaneLinii } from "../../_dane/linie";
import { dzienTs } from "../../_dane/formatCzasu";
import type { DzienV } from "../../_dane/przygotuj";
import type { DaneStron } from "../../_dane/strony";
import { DniD } from "../atomy2/podstawowe";
import { GlowaLigi, WierszA } from "../elementy/mecz";
import { FlagaLigi } from "../Herb";
import { NajlepszeLinie, odmLinia } from "./NajlepszeLinie";

/*
 * Etap 5.3 – lista meczów jako wejście do narzędzia pokryć (decyzja 01.10):
 * w wierszu to, co znajdziesz w środku – ilu zawodników ma kurs i ile naszych
 * typów jest już na liście. Żadnych „najmocniejszy X%”.
 * Na liście WYŁĄCZNIE mecze z kursami na zawodników (właściciel 05.10: „bez
 * kursów na zawodników niech tu nie będzie”) – mecz bez propsów to pusta strona
 * narzędzia. Pojawi się sam, gdy bukmacher wystawi ofertę. Mecze z samymi
 * typami drużynowymi zostają w Drużynach.
 */

const zKursami = (dane: DaneStron, id: number) => (dane.infoMeczow[id]?.zawodnicy ?? 0) > 0;

const odmZaw = (n: number) => (n === 1 ? "zawodnik" : "zawodników");
const odmMocne = (n: number) => {
  const l = odmLinia(n);
  return l === "linia" ? "mocna linia" : l === "linie" ? "mocne linie" : "mocnych linii";
};
const odmRynek = (n: number) => (n === 1 ? "rynek" : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? "rynki" : "rynków");

type Uklad = {
  dane: DaneStron;
  telefon: boolean;
  /** `gdzie` – z „Najlepszych linii”: strona meczu otwiera się na tym rynku i linii */
  otworz?: (id: number, gdzie?: { rynek: string; linia: number }) => void;
  /** Najlepsze linie (15.10); bez nich lista meczów jak dotąd */
  linie?: { dane: DaneLinii | null; mocne: Record<number, number>; widok?: string };
};

function useMecze(dane: DaneStron) {
  const TERAZ = useTeraz();
  const mecze = useMemo(() => dane.meczeWszystkie.filter((m) => m.ts > TERAZ && zKursami(dane, m.id)), [dane, TERAZ]);
  const dni: DzienV[] = useMemo(() => {
    const m = new Map<string, { etykieta: string; ile: number }>();
    for (const x of mecze) {
      const k = dzienTs(x.ts);
      const w = m.get(k) ?? { etykieta: x.dzien, ile: 0 };
      w.ile += 1;
      m.set(k, w);
    }
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([klucz, w]) => ({ klucz, ...w }));
  }, [mecze]);
  const [dzien, setDzien] = useState(dni[0]?.klucz ?? "");
  const [liga, setLiga] = useState("");
  const zDnia = mecze.filter((m) => dzienTs(m.ts) === dzien);
  const ligi = useMemo(() => {
    const w = new Map<string, MeczE[]>();
    for (const m of zDnia) w.set(m.liga, [...(w.get(m.liga) ?? []), m]);
    return [...w.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [zDnia]);
  const aktywnaLiga = ligi.some(([l]) => l === liga) ? liga : "";
  const widoczne = aktywnaLiga ? zDnia.filter((m) => m.liga === aktywnaLiga) : zDnia;
  const zmienDzien = (k: string) => {
    setDzien(k);
    setLiga("");
  };
  return { dni, dzien, zmienDzien, liga: aktywnaLiga, setLiga, ligi, widoczne, zDnia, wszystkieDnia: zDnia.length };
}

/* chipy rozgrywek z flagą – lżejsze niż dni, żeby nie udawały drugiego kalendarza */
function ChipyLig({ ligi, liga, setLiga, wszystkie }: { ligi: [string, MeczE[]][]; liga: string; setLiga: (l: string) => void; wszystkie: number }) {
  if (ligi.length < 2) return null;
  return (
    <div className="sm-ligi" role="group" aria-label="Rozgrywki">
      <button type="button" className="sm-liga" aria-pressed={!liga} onClick={() => setLiga("")}>
        Wszystkie <small>{wszystkie}</small>
      </button>
      {ligi.map(([nazwa, lista]) => {
        const l = lista[0];
        return (
          <button key={nazwa} type="button" className="sm-liga" aria-pressed={liga === nazwa} onClick={() => setLiga(liga === nazwa ? "" : nazwa)}>
            <FlagaLigi flaga={l.ligaFlaga} id={l.ligaId} c1={l.ligaC1} c2={l.ligaC2} tryb="prawdziwy" />
            {nazwa}
            <small>{lista.length}</small>
          </button>
        );
      })}
    </div>
  );
}

/* prawa kolumna wiersza: co jest w środku meczu – tylko zawodnicy (właściciel
   15.10: w zakładce Mecze nic drużynowego, więc bez „N typów na liście”) */
function CoWSrodku({ info, mocne = 0 }: { info: DaneStron["infoMeczow"][number] | undefined; mocne?: number }) {
  const z = info?.zawodnicy ?? 0;
  return (
    <div className="el-typy-meczu sm-co">
      {z > 0 ? (
        <b>
          {z} {odmZaw(z)}
          <span className="sm-co-dl"> z kursem</span>
        </b>
      ) : (
        <b className="sm-co-brak">
          bez kursów<span className="sm-co-dl"> na zawodników</span>
        </b>
      )}
      {mocne > 0 ? (
        <span className="sm-co-mocne" title="Pokrycie od 80% w ostatnich 10 meczach i kurs od 1,40">
          {mocne} {odmMocne(mocne)}
        </span>
      ) : (
        z > 0 && (
          <span>
            {info?.rynki} {odmRynek(info?.rynki ?? 0)}
          </span>
        )
      )}
    </div>
  );
}

type Widok = "mecze" | "linie";

export function StronaMecze({ dane, otworz, telefon, linie }: Uklad & { wariant?: string }) {
  const s = useMecze(dane);
  const [widok, setWidok] = useState<Widok>(linie?.widok === "linie" ? "linie" : "mecze");
  const idWidoku = useId();
  const zmienWidok = (w: Widok) => {
    setWidok(w);
    // powrót ze strony meczu wraca do tego samego widoku
    const u = new URL(window.location.href);
    if (w === "linie") u.searchParams.set("widok", "linie");
    else u.searchParams.delete("widok");
    window.history.replaceState(window.history.state, "", u);
  };
  const mocneDnia = linie ? s.zDnia.reduce((a, m) => a + (linie.mocne[m.id] ?? 0), 0) : 0;
  const grupy = useMemo(() => {
    const w = new Map<string, MeczE[]>();
    for (const m of s.widoczne) w.set(m.liga, [...(w.get(m.liga) ?? []), m]);
    return [...w.entries()];
  }, [s.widoczne]);

  return (
    <main className="st-strona sm">
      <div className="st-naglowek">
        <h1 className="p-n">Mecze</h1>
        <p>
          <span>Kursy i statystyki zawodników na każdy mecz.</span> <span>Wejdź w mecz i sprawdź, kto ostatnio przebijał linie.</span>
        </p>
      </div>
      <div className="sm-filtry">
        {linie ? (
          <div className="f-rzad-polek">
            <DniD dni={s.dni} wybrany={s.dzien} zmien={s.zmienDzien} />
            <LayoutGroup id={idWidoku}>
              <div className="a-karty-zakladek sm-widoki" role="tablist" aria-label="Widok" data-kompakt="">
                {(
                  [
                    ["mecze", "Mecze", s.wszystkieDnia],
                    ["linie", "Najlepsze linie", mocneDnia],
                  ] as [Widok, string, number][]
                ).map(([k, nazwa, n]) => (
                  <button key={k} type="button" role="tab" className="a-karta-zakladki" aria-selected={widok === k} onClick={() => zmienWidok(k)}>
                    {widok === k && <motion.span layoutId="sm-kreska-widoku" className="a-podkreslenie" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
                    <b>
                      {nazwa} <span>{n}</span>
                    </b>
                  </button>
                ))}
              </div>
            </LayoutGroup>
          </div>
        ) : (
          <DniD dni={s.dni} wybrany={s.dzien} zmien={s.zmienDzien} />
        )}
        {widok === "mecze" && <ChipyLig ligi={s.ligi} liga={s.liga} setLiga={s.setLiga} wszystkie={s.wszystkieDnia} />}
      </div>
      {widok === "linie" && linie ? (
        <NajlepszeLinie key={s.dzien} dane={linie.dane} mecze={s.zDnia} telefon={telefon} otworz={otworz} />
      ) : (
      <div className="sm-lista">
        {!grupy.length && (
          <div className="d-pusty">
            <div className="p-n" style={{ fontSize: 17 }}>
              Na razie żaden mecz nie ma kursów na zawodników
            </div>
            <p>Mecz pojawi się tu sam, gdy bukmacher wystawi kursy na zawodników.</p>
          </div>
        )}
        {grupy.map(([liga, lista]) => (
          <section key={liga} className="el-liga">
            <GlowaLigi mecze={lista} />
            {lista.map((m) => (
              <div key={m.id} className="sm-wiersz">
                <WierszA m={m} wybierz={otworz ? () => otworz(m.id) : undefined} prawa={<CoWSrodku info={dane.infoMeczow[m.id]} mocne={linie?.mocne[m.id]} />} />
              </div>
            ))}
          </section>
        ))}
      </div>
      )}
    </main>
  );
}
