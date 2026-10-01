"use client";

import { MotionConfig } from "framer-motion";
import { useEffect, useState } from "react";

import "../../atomy.css";
import "../../atomy2.css";
import "../../elementy.css";
import "../../szkielet.css";
import "../../strony.css";
import "../../systemowe.css";

import type { DaneSystemowe } from "../../_dane/systemowe";
import type { StanLogowania } from "./Logowanie";
import { Logowanie } from "./LogowanieWarsztat";

/*
 * Podgląd logowania na całym ekranie – bez ramki warsztatu, żeby oceniać
 * proporcje i ruch jak na prawdziwej stronie. ?m=ciemny|jasny &s=stan
 */
export function LogowaniePelne({ dane, start }: { dane: DaneSystemowe; start: Record<string, string | undefined> }) {
  const [motyw, setMotyw] = useState<"ciemny" | "jasny">(start.m === "jasny" ? "jasny" : "ciemny");
  const [telefon, setTelefon] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 640px)");
    const ustaw = () => setTelefon(mq.matches);
    ustaw();
    mq.addEventListener("change", ustaw);
    return () => mq.removeEventListener("change", ustaw);
  }, []);
  return (
    <MotionConfig reducedMotion="user">
      <div
        className="p-ekran sy-pelny"
        data-p-motyw={motyw}
        data-p-paleta={motyw === "ciemny" ? "b1" : "p3"}
        data-p-font="2c"
        style={{ minHeight: "100dvh", padding: 0, containerType: "inline-size" }}
      >
        <Logowanie
          key={String(telefon)}
          telefon={telefon}
          autoFokus={!telefon}
          jasneLogo={motyw === "ciemny"}
          stan={(start.s as StanLogowania) ?? "zwykly"}
          motyw={motyw}
          zmienMotyw={() => setMotyw((m) => (m === "ciemny" ? "jasny" : "ciemny"))}
          dane={dane}
        />
      </div>
    </MotionConfig>
  );
}
