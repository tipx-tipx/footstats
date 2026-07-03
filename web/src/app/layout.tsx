import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Sora } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { SiteFooter } from "@/components/SiteFooter";
import { getMeta } from "@/lib/data";

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
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const meta = await getMeta();
  const aktualizacja = new Intl.DateTimeFormat("pl-PL", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  }).format(new Date(meta.wygenerowano_ts * 1000));
  return (
    <html
      lang="pl"
      className={`${sora.variable} ${plexSans.variable} ${plexMono.variable} h-full`}
    >
      <body className="flex min-h-full flex-col">
        <Nav />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-24 sm:px-6">
          {children}
        </main>
        <SiteFooter
          zrodlo={meta.zrodlo}
          liga={meta.liga}
          sezon={meta.sezon}
          meczow={meta.meczow_w_bazie}
          aktualizacja={aktualizacja}
        />
      </body>
    </html>
  );
}
