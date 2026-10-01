"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import "../../atomy.css";
import "../../atomy2.css";
import "../../elementy.css";
import "../../strony.css";
import "../../kupony.css";
import "../../kupony2.css";
import "../../kontrola.css";
import "../../jak.css";
import "../../zawodnik.css";

import type { LegPool } from "@/lib/types";

import type { MeczStrony } from "../../_dane/mecz";
import type { DaneKontroli } from "../../_dane/kontrola";
import type { DruzynaV } from "../../_dane/przygotuj";
import type { DaneSkutecznosci } from "../../_dane/skutecznosc";
import type { ZawodnikStrony } from "../../_dane/zawodnik";
import type { DaneStron } from "../../_dane/strony";
import { CzasProvider } from "../czas";
import { LinkiAplikacji } from "../linki";
import { StronaDruzyny, StronaGlowna } from "../strony/StronaGlowna";
import { StronaMecze } from "../strony/StronaMecze";
import { StronaMeczu } from "../strony/StronaMeczu";
import { KreatorV2 } from "../kupony/KreatorV2";
import { HistoriaKuponow } from "../kupony/HistoriaKuponow";
import type { HistoriaKuponow as HistoriaKuponowDane } from "../../_dane/kuponyHistoria";
import { StronaWynikowAdmin } from "../strony/StronaKontroli";
import { StronaSkutecznosci } from "../strony/StronaSkutecznosci";
import { StronaJakCzytac } from "../strony/StronaJakCzytac";
import { StronaZawodnika } from "../strony/StronaZawodnika";

/*
 * Etap 7 – most między serwerem aplikacji a stronami z warsztatu.
 * Serwer liczy dane (adaptery `_dane` na danych z Supabase) i zgaduje
 * telefon po przeglądarce; tu: „teraz” tyka co minutę (odliczania nie
 * starzeją się przez cache strony), a telefon doprecyzowuje szerokość ekranu.
 */

function useTelefon(start: boolean) {
  const [telefon, setTelefon] = useState(start);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 760px)");
    const ustaw = () => setTelefon(mq.matches);
    ustaw();
    mq.addEventListener("change", ustaw);
    return () => mq.removeEventListener("change", ustaw);
  }, []);
  return telefon;
}

function useTykajacyCzas(start: number) {
  const [teraz, setTeraz] = useState(start);
  useEffect(() => {
    const t = () => setTeraz(Math.floor(Date.now() / 1000));
    t();
    const i = setInterval(t, 60_000);
    return () => clearInterval(i);
  }, []);
  return teraz;
}

export type RodzajStrony = "zawodnicy" | "druzyny" | "mecze" | "mecz" | "kupony" | "wyniki" | "jak" | "zawodnik";

export function StronaAplikacji({
  strona,
  dane,
  teraz,
  telefon: telefonStart,
  mecz,
  kupony,
  wyniki,
  zawodnik,
}: {
  strona: RodzajStrony;
  dane: DaneStron;
  teraz: number;
  telefon: boolean;
  /** strona meczu: mecz z pełnymi kadrami */
  mecz?: MeczStrony;
  /** strona Kupony: pula typów, herby, kupon z linku (`?k=`) */
  kupony?: { pula: LegPool[]; herby: Record<string, DruzynaV>; k?: string; historia?: HistoriaKuponowDane | null };
  /** Wyniki: dane klienta; `kontrola` TYLKO dla admina (rola sprawdzona na serwerze) */
  wyniki?: { skutecznosc: DaneSkutecznosci; kontrola?: DaneKontroli; start?: { widok?: string; dzien?: string } };
  /** strona zawodnika */
  zawodnik?: ZawodnikStrony;
}) {
  const telefon = useTelefon(telefonStart);
  const czas = useTykajacyCzas(teraz);
  const router = useRouter();
  const tresc =
    strona === "druzyny" ? (
      <StronaDruzyny wariant="ab" dane={dane} telefon={telefon} />
    ) : strona === "mecze" ? (
      <StronaMecze dane={dane} telefon={telefon} otworz={(id) => router.push(`/mecze/${id}`)} />
    ) : strona === "zawodnik" && zawodnik ? (
      <StronaZawodnika z={zawodnik} telefon={telefon} />
    ) : strona === "jak" ? (
      <StronaJakCzytac dane={dane} telefon={telefon} />
    ) : strona === "wyniki" && wyniki ? (
      wyniki.kontrola ? (
        <StronaWynikowAdmin kontrola={wyniki.kontrola} skutecznosc={wyniki.skutecznosc} telefon={telefon} start={wyniki.start} />
      ) : (
        <StronaSkutecznosci wariant="a" dane={wyniki.skutecznosc} telefon={telefon} dzienStart={wyniki.start?.dzien} />
      )
    ) : strona === "kupony" && kupony ? (
      <div className="ap-waska">
        <KreatorV2 pula={kupony.pula} herby={kupony.herby} telefon={telefon} start={{ k: kupony.k }} />
        {kupony.historia && <HistoriaKuponow dane={kupony.historia} />}
      </div>
    ) : strona === "mecz" && mecz ? (
      <StronaMeczu wariant="a" m={mecz} dane={dane} telefon={telefon} />
    ) : (
      <StronaGlowna wariant="c" dane={dane} telefon={telefon} />
    );
  return (
    <LinkiAplikacji>
      <CzasProvider teraz={czas}>{tresc}</CzasProvider>
    </LinkiAplikacji>
  );
}
