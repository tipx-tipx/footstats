import Image from "next/image";

/**
 * Logo bukmachera przy kursie (2026-09-18, pliki od właściciela).
 *
 * PO CO. Siatka kursów bierze WYŻSZĄ cenę z Superbetu i Betclica, a od 18.09
 * Betclic ma pełny zasięg — kurs bez oznaczenia zmuszał do szukania zdania
 * „u Betclica" gdzieś niżej na karcie. Logo stoi przy samej liczbie.
 *
 * OPTYCZNA RÓWNOŚĆ, NIE PIKSELOWA. Betclic to napis w czerwonym prostokącie,
 * Superbet — sam napis bez tła. Przy tej samej wysokości Superbet wyglądał
 * na dwa razy większy, więc dostaje ~72% wysokości (SKALA). Oba kolory są
 * czerwone — rozróżnia je kształt i napis, dlatego zawsze logo z nazwą,
 * nigdy sama barwa.
 *
 * WYMIARY W HTML (ta sama lekcja co w `Logo.tsx`): szerokość liczona
 * z proporcji pliku, więc przeglądarka rezerwuje właściwe miejsce, zanim
 * obraz się doczyta — nic nie podskakuje na telefonie.
 *
 * Nieznany bukmacher (np. STS) = sam napis, bez zgadywania logo.
 */

const PLIKI: Record<string, { src: string; proporcja: number; skala: number }> = {
  // proporcje po przycięciu przezroczystych marginesów (public/bukmacherzy)
  Superbet: { src: "/bukmacherzy/superbet.png", proporcja: 271 / 48, skala: 0.72 },
  Betclic: { src: "/bukmacherzy/betclic.png", proporcja: 142 / 48, skala: 1 },
};

/** Backend zapisuje bukmachera tylko, gdy cena NIE jest z Superbetu. */
export function nazwaBukmachera(bukmacher?: string | null): string {
  if (!bukmacher) return "Superbet";
  const b = bukmacher.trim().toLowerCase();
  if (b === "superbet") return "Superbet";
  if (b === "betclic") return "Betclic";
  return bukmacher;
}

export function LogoBukmachera({
  bukmacher,
  wysokosc = 14,
  className = "",
}: {
  /** nazwa z danych; brak = Superbet (domyślny cennik) */
  bukmacher?: string | null;
  /** wysokość logo Betclica w px — Superbet dostaje optycznie równą */
  wysokosc?: number;
  className?: string;
}) {
  const nazwa = nazwaBukmachera(bukmacher);
  const plik = PLIKI[nazwa];
  if (!plik) {
    return (
      <span
        className={`inline-flex items-center text-[10px] font-semibold uppercase tracking-wide text-faint ${className}`}
      >
        {nazwa}
      </span>
    );
  }
  const h = Math.max(6, Math.round(wysokosc * plik.skala));
  const w = Math.round(h * plik.proporcja);
  return (
    <span
      className={`inline-flex shrink-0 items-center ${className}`}
      style={{ height: wysokosc }}
      title={`Kurs u ${nazwa === "Superbet" ? "Superbetu" : nazwa === "Betclic" ? "Betclica" : nazwa}`}
    >
      <Image
        src={plik.src}
        alt={nazwa}
        width={w}
        height={h}
        className="block"
        style={{ width: w, height: h }}
      />
    </span>
  );
}
