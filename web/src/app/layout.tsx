import { MotionConfig } from "framer-motion";
import type { Metadata } from "next";
import { Barlow } from "next/font/google";
import "./globals.css";
import "./nowy.css";

// redesign (etap 7): Barlow pełnej szerokości – nagłówki 700, tekst 400–600.
const barlow = Barlow({
  subsets: ["latin", "latin-ext"],
  variable: "--pf-barlow",
  weight: ["400", "500", "600", "700"],
});

// motyw: zapis usera z localStorage, bez zapisu – preferencja systemowa.
// Skrypt inline w <head> działa PRZED pierwszym malowaniem (zero mignięcia
// jasnym tłem przy wejściu w ciemny motyw). Przełącznik: SzkieletAplikacji.
const SKRYPT_MOTYWU = `(function(){try{var m=localStorage.getItem("footstats-motyw");if(m!=="dark"&&m!=="light"){m=window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.dataset.theme=m}catch(e){}})()`;

export const metadata: Metadata = {
  title: "FootStats – typy na mecze ze statystyk",
  description:
    "Typy na statystyki zawodników i drużyn: codziennie sprawdzamy tysiące zakładów i zostawiamy te, które wchodzą najczęściej.",
  // BEZ pola `icons` – ikony biorą się z konwencji plikowej app/ (favicon.ico
  // + icon.png). Ręcznie dopisany link nie NADPISYWAŁ tego, co Next generuje
  // z plików, tylko się dokładał: w <head> lądowały dwie ikony naraz, a
  // przeglądarka brała tę pierwszą – czyli domyślny favicon.ico Next.js.
  // narzędzie prywatne za hasłem – nie indeksować
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="pl"
      className={`${barlow.variable} h-full`}
      // data-theme ustawia skrypt przed hydracją – React ma tego nie zgłaszać
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: SKRYPT_MOTYWU }} />
      </head>
      <body className="flex min-h-full flex-col">
        {/* reducedMotion="user": framer sam wyłącza animacje transform u osób
            z ograniczeniem ruchu. Dzięki temu komponenty NIE rozgałęziają
            initial po useReducedMotion (SSR nie zna preferencji → hydration
            mismatch #418, który potrafił skasować data-theme) */}
        <MotionConfig reducedMotion="user">{children}</MotionConfig>
      </body>
    </html>
  );
}
