import type { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  Archivo,
  Barlow,
  Barlow_Condensed,
  Barlow_Semi_Condensed,
  Schibsted_Grotesk,
} from "next/font/google";

import "./projekt.css";

/*
 * Warsztat redesignu. Na produkcji (Vercel) nie istnieje: 404, chyba że ktoś
 * świadomie ustawi POKAZ_PROJEKT=1 (np. `npm run zrzuty` na lokalnym buildzie).
 * Fonty kandydatów ładują się TYLKO tutaj – reszta aplikacji ich nie pobiera.
 */

const archivo = Archivo({
  subsets: ["latin", "latin-ext"],
  variable: "--pf-archivo",
  axes: ["wdth"],
});

const barlow = Barlow({
  subsets: ["latin", "latin-ext"],
  variable: "--pf-barlow",
  weight: ["400", "500", "600", "700"],
});

const barlowC = Barlow_Condensed({
  subsets: ["latin", "latin-ext"],
  variable: "--pf-barlow-c",
  weight: ["600", "700"],
});

const barlowSc = Barlow_Semi_Condensed({
  subsets: ["latin", "latin-ext"],
  variable: "--pf-barlow-sc",
  weight: ["600", "700"],
});

const schibsted = Schibsted_Grotesk({
  subsets: ["latin", "latin-ext"],
  variable: "--pf-schibsted",
});

export const metadata: Metadata = { title: "Warsztat redesignu – FootStats" };

export default function ProjektLayout({ children }: { children: React.ReactNode }) {
  if (process.env.NODE_ENV === "production" && process.env.POKAZ_PROJEKT !== "1") {
    notFound();
  }
  return (
    <div
      className={`${archivo.variable} ${barlow.variable} ${barlowSc.variable} ${barlowC.variable} ${schibsted.variable} min-h-screen`}
      style={{ background: "#0d0f10" }}
    >
      {children}
    </div>
  );
}
