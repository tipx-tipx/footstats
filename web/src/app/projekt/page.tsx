import Link from "next/link";

const ETAPY: { nr: number; nazwa: string; opis: string; href?: string }[] = [
  { nr: 1, nazwa: "Fundamenty", opis: "wybrane: paleta B, Barlow, herby prawdziwe", href: "/projekt/fundamenty" },
  { nr: 1.5, nazwa: "Dopracowanie", opis: "wybrane: ciemny Noc, jasny Gazeta, Barlow pełny", href: "/projekt/dopracowanie" },
  { nr: 2, nazwa: "Atomy", opis: "warianty A/B/C – wybrane", href: "/projekt/atomy" },
  { nr: 2.5, nazwa: "Atomy – dopracowanie", opis: "wybrane warianty dopracowane, z porównaniem", href: "/projekt/atomy-2" },
  { nr: 3, nazwa: "Główne elementy", opis: "wiersz meczu, karta typu, drabinka, kupon, Twój kupon", href: "/projekt/elementy" },
  { nr: 3.6, nazwa: "Strona Kupony – prototyp", opis: "cel na żywo, zamiana, kupon z meczu, link, karta", href: "/projekt/kupony" },
  { nr: 4, nazwa: "Szkielet i nawigacja", opis: "menu komputer i telefon, szukaj, świeżość, stopka", href: "/projekt/szkielet" },
  { nr: 5, nazwa: "Układy stron", opis: "Zawodnicy, Drużyny, Mecze zatwierdzone; Skuteczność – warianty", href: "/projekt/strony" },
  { nr: 5.9, nazwa: "Strony systemowe", opis: "logowanie, 404, błąd, brak internetu", href: "/projekt/systemowe" },
  { nr: 6, nazwa: "Ruch", opis: "charakter, scena w akcji, przejścia, słownik", href: "/projekt/ruch" },
  { nr: 7, nazwa: "Składanie", opis: "cała aplikacja w nowym wyglądzie" },
  { nr: 8, nazwa: "Kontrola i produkcja", opis: "telefon, role, kontrast, wdrożenie" },
  { nr: 9, nazwa: "Teksty – głos marki", opis: "zasady, słownik zamian, przed i po", href: "/projekt/teksty" },
];

export default function ProjektPage() {
  return (
    <main style={{ maxWidth: 720, margin: "0 auto", padding: "48px 20px", color: "#e8eaea", font: "15px/1.5 system-ui, sans-serif" }}>
      <h1 style={{ fontSize: 22, fontWeight: 600 }}>Warsztat redesignu</h1>
      <p style={{ color: "#8b9194", marginTop: 6 }}>
        Etap po etapie: warianty na prawdziwych danych, wybierasz, dopracowujemy, idziemy dalej.
      </p>
      <ol style={{ marginTop: 28, display: "grid", gap: 8 }}>
        {ETAPY.map((e) => {
          const tresc = (
            <>
              <span style={{ color: "#8b9194", width: 22, display: "inline-block" }}>{e.nr === 1.5 ? "1b" : e.nr === 2.5 ? "2b" : e.nr === 3.6 ? "3k" : e.nr === 5.9 ? "5s" : e.nr === 9 ? "T" : e.nr}</span>
              <b style={{ fontWeight: 600 }}>{e.nazwa}</b>
              <span style={{ color: "#8b9194" }}> – {e.opis}</span>
            </>
          );
          return (
            <li
              key={e.nr}
              style={{
                padding: "12px 14px",
                borderRadius: 8,
                background: e.href ? "#1b1f21" : "transparent",
                border: "1px solid #25292c",
                opacity: e.href ? 1 : 0.55,
              }}
            >
              {e.href ? <Link href={e.href}>{tresc} →</Link> : tresc}
            </li>
          );
        })}
      </ol>
    </main>
  );
}
