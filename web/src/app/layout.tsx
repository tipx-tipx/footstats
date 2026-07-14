import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Sora } from "next/font/google";
import "./globals.css";

const sora = Sora({
  subsets: ["latin", "latin-ext"],
  variable: "--font-sora",
  weight: ["400", "600", "700"],
});

const plexSans = IBM_Plex_Sans({
  subsets: ["latin", "latin-ext"],
  variable: "--font-plex-sans",
  weight: ["400", "500", "600"],
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin", "latin-ext"],
  variable: "--font-plex-mono",
  weight: ["400", "500", "600"],
});

// motyw: zapis usera z localStorage, bez zapisu — preferencja systemowa.
// Skrypt inline w <head> działa PRZED pierwszym malowaniem (zero mignięcia
// jasnym tłem przy wejściu w ciemny motyw). Lustro logiki ThemeToggle.
const SKRYPT_MOTYWU = `(function(){try{var m=localStorage.getItem("footstats-motyw");if(m!=="dark"&&m!=="light"){m=window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.dataset.theme=m}catch(e){}})()`;

export const metadata: Metadata = {
  title: "FootStats — okazje na statystyki piłkarskie",
  description:
    "Osobisty silnik decyzyjny: model matematyczny szacuje prawdopodobieństwa statystyk zawodników i drużyn, porównuje je z kursami bukmacherów i pokazuje, gdzie kurs jest zawyżony.",
  icons: { icon: "/favicon.png" },
  // narzędzie prywatne za hasłem — nie indeksować
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="pl"
      className={`${sora.variable} ${plexSans.variable} ${plexMono.variable} h-full`}
      // data-theme ustawia skrypt przed hydracją — React ma tego nie zgłaszać
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: SKRYPT_MOTYWU }} />
      </head>
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
