"use client";

import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent as KE } from "react";

import type { DruzynaV } from "../../_dane/przygotuj";
import { Herb } from "../Herb";
import { IkonaNav, IkonaSzukaj } from "./ikonyNav";

/*
 * Szukaj z każdego miejsca (Ctrl+K) – zatwierdzona paleta z etapu 4 na
 * żywym indeksie: zawodnicy z typami, drużyny, mecze. Wybór prowadzi dalej
 * (zawodnik → jego strona, mecz → strona meczu, drużyna → Drużyny).
 * Od 3 liter dochodzą zawodnicy z całej oferty (`/api/szukaj`, 7B) – ci bez
 * typu, ale z kursem, też mają swoją stronę.
 */

export type IndeksSzukania = {
  zawodnicy: { id: number; nazwa: string; druzyna: DruzynaV | null; typy: number }[];
  druzyny: { nazwa: string; herb: DruzynaV; typy: number }[];
  mecze: { id: number; gosp: DruzynaV; gosc: DruzynaV; opis: string }[];
};

const norm = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l");
const odmTyp = (n: number) => `${n} ${n === 1 ? "typ" : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? "typy" : "typów"}`;

type Wynik = { grupa: string; klucz: string; nazwa: string; opis: string; href: string; herb?: DruzynaV | null; herby?: [DruzynaV, DruzynaV] };
type ZawodnikZOferty = { id: number; nazwa: string; druzyna: DruzynaV | null; opis: string };

/** zawodnicy z całej oferty – po chwili bez pisania, ostatnie zapytanie wygrywa */
function useZawodnicyZOferty(q: string): ZawodnikZOferty[] {
  const [wynik, setWynik] = useState<{ q: string; lista: ZawodnikZOferty[] }>({ q: "", lista: [] });
  useEffect(() => {
    const zapytanie = q.trim();
    if (zapytanie.length < 3) return;
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      fetch(`/api/szukaj?q=${encodeURIComponent(zapytanie)}`, { signal: ctrl.signal })
        .then((r) => (r.ok ? r.json() : { zawodnicy: [] }))
        .then((d: { zawodnicy?: ZawodnikZOferty[] }) => setWynik({ q: zapytanie, lista: d.zawodnicy ?? [] }))
        .catch(() => undefined);
    }, 180);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [q]);
  return wynik.q === q.trim() ? wynik.lista : [];
}

export function PaletaAplikacji({ indeks, zamknij, start = "" }: { indeks: IndeksSzukania; zamknij: () => void; start?: string }) {
  const router = useRouter();
  const [q, setQ] = useState(start);
  const [i, setI] = useState(0);
  const pole = useRef<HTMLInputElement>(null);
  useEffect(() => {
    pole.current?.focus();
    pole.current?.select();
  }, []);
  const zOferty = useZawodnicyZOferty(q);

  const wyniki = useMemo((): Wynik[] => {
    const n = norm(q.trim());
    const pasuje = (s: string) => !n || norm(s).includes(n);
    const lokalni = indeks.zawodnicy
      .filter((x) => pasuje(x.nazwa))
      .map((x): Wynik => ({ grupa: "Zawodnicy", klucz: `z${x.id}`, nazwa: x.nazwa, opis: odmTyp(x.typy), href: `/zawodnik/${x.id}`, herb: x.druzyna }));
    const znani = new Set(lokalni.map((w) => w.klucz));
    const dalsi = zOferty
      .filter((x) => !znani.has(`z${x.id}`))
      .map((x): Wynik => ({ grupa: "Zawodnicy", klucz: `z${x.id}`, nazwa: x.nazwa, opis: x.opis, href: `/zawodnik/${x.id}`, herb: x.druzyna }));
    const z = [...lokalni, ...dalsi].slice(0, 6);
    const d = indeks.druzyny
      .filter((x) => n && pasuje(x.nazwa))
      .slice(0, 3)
      .map((x): Wynik => ({ grupa: "Drużyny", klucz: `d${x.nazwa}`, nazwa: x.nazwa, opis: x.typy ? odmTyp(x.typy) : "mecz w ofercie", href: "/druzyny", herb: x.herb }));
    const m = indeks.mecze
      .filter((x) => pasuje(`${x.gosp.nazwa} ${x.gosc.nazwa}`))
      .slice(0, 4)
      .map((x): Wynik => ({ grupa: "Mecze", klucz: `m${x.id}`, nazwa: `${x.gosp.nazwa} – ${x.gosc.nazwa}`, opis: x.opis, href: `/mecze/${x.id}`, herby: [x.gosp, x.gosc] }));
    return [...z, ...d, ...m];
  }, [q, indeks, zOferty]);

  const otworz = (w: Wynik | undefined) => {
    if (!w) return;
    zamknij();
    router.push(w.href);
  };

  const klawisze = (e: KE) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setI((x) => Math.min(x + 1, wyniki.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setI((x) => Math.max(x - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      otworz(wyniki[i]);
    } else if (e.key === "Escape") zamknij();
  };

  return (
    <motion.div className="s-paleta-tlo ap-paleta-tlo" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={zamknij}>
      <motion.div
        className="s-paleta"
        role="dialog"
        aria-label="Szukaj"
        initial={{ y: -10, scale: 0.98 }}
        animate={{ y: 0, scale: 1 }}
        exit={{ y: -10, scale: 0.98 }}
        transition={{ duration: 0.16 }}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={klawisze}
      >
        <div className="s-paleta-pole">
          <IkonaSzukaj r={18} />
          <input
            ref={pole}
            value={q}
            placeholder="Zawodnik, drużyna, mecz…"
            aria-label="Szukaj"
            onChange={(e) => {
              setQ(e.target.value);
              setI(0);
            }}
          />
        </div>
        <div className="s-paleta-wyniki" role="listbox">
          {wyniki.length === 0 && <div className="s-paleta-grupa">Nic nie znaleźliśmy – spróbuj nazwiska albo nazwy drużyny</div>}
          {wyniki.map((w, j) => (
            <div key={w.klucz}>
              {(j === 0 || wyniki[j - 1].grupa !== w.grupa) && <div className="s-paleta-grupa">{w.grupa}</div>}
              <button type="button" role="option" aria-selected={j === i} className="s-paleta-poz" onMouseEnter={() => setI(j)} onClick={() => otworz(w)}>
                {w.herby ? (
                  <span style={{ display: "inline-flex", gap: 3 }}>
                    <Herb d={w.herby[0]} tryb="prawdziwy" rozmiar={16} />
                    <Herb d={w.herby[1]} tryb="prawdziwy" rozmiar={16} />
                  </span>
                ) : w.herb ? (
                  <Herb d={w.herb} tryb="prawdziwy" rozmiar={16} />
                ) : (
                  <IkonaNav klucz="zawodnicy" rozmiar={16} />
                )}
                {w.nazwa}
                <small>{w.opis}</small>
              </button>
            </div>
          ))}
        </div>
        <div className="s-paleta-stopka">
          <span>
            <kbd>↑↓</kbd>wybierz
          </span>
          <span>
            <kbd>Enter</kbd>otwórz
          </span>
          <span>
            <kbd>Esc</kbd>zamknij
          </span>
        </div>
      </motion.div>
    </motion.div>
  );
}
