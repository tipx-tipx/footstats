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
    >
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
