"use client";

import { useStawka } from "./useStawka";
import { fmtU } from "@/lib/format";

/**
 * Jak pisać bilans — jedna decyzja na całą Skuteczność.
 *
 * Admin czyta w jednostkach stawki („−46,62u"), bo porównuje produkty
 * i okresy, a jednostka jest niezależna od tego, ile kto stawia. Klient czyta
 * w złotówkach, bo „u" nie znaczy dla niego nic.
 *
 * Powód istnienia tego pliku: przez chwilę werdykt i chipy pokazywały
 * złotówki, a krzywa i kalendarz obok — jednostki. Dwie różne liczby o tej
 * samej rzeczy na jednym ekranie to najprostszy sposób, żeby ktoś przestał
 * ufać stronie. Wszystko, co pokazuje bilans, bierze formatowanie stąd.
 *
 * `krotki` = wersja do ciasnych miejsc (kafelek kalendarza ma ~40 px):
 * sama liczba, bez „zł". Jednostkę tłumaczy wtedy podpis obok siatki.
 */
export function useBilans(pelnyWglad: boolean) {
  const [stawka] = useStawka();

  function bilans(jednostki: number, krotki = false): string {
    if (pelnyWglad) return fmtU(jednostki);
    const zl = Math.round(jednostki * stawka);
    const znak = zl > 0 ? "+" : zl < 0 ? "−" : "";
    return `${znak}${Math.abs(zl)}${krotki ? "" : " zł"}`;
  }

  return { bilans, stawka };
}
