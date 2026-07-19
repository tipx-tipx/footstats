"use client";

import { useEffect, useState } from "react";

const KEY = "footstats.stawka";

/**
 * Globalna stawka użytkownika (zł) — jedno źródło dla „z X zł robi się",
 * zapisu zagranych kuponów i podglądu generatora. Trzymana lokalnie,
 * domyślnie 10 zł.
 */
export function useStawka(): [number, (n: number) => void] {
  const [stawka, setStawka] = useState(10);
  useEffect(() => {
    const v = Number(localStorage.getItem(KEY));
    if (Number.isFinite(v) && v > 0) setStawka(v);
  }, []);
  const ustaw = (n: number) => {
    const v = Number.isFinite(n) && n > 0 ? Math.min(Math.round(n), 100000) : 10;
    setStawka(v);
    localStorage.setItem(KEY, String(v));
  };
  return [stawka, ustaw];
}
