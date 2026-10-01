"use client";

import type { DaneSystemowe } from "../../_dane/systemowe";
import { StronaGlowna } from "../strony/StronaGlowna";
import { LogowanieNadAplikacja, type StanLogowania } from "./Logowanie";

/** warsztat: logowanie N z prawdziwą stroną główną migawki pod spodem (aplikacja: `LogowanieAplikacji`, szkielet) */
export function Logowanie({
  telefon,
  jasneLogo,
  stan,
  motyw,
  zmienMotyw,
  dane,
  autoFokus = false,
}: {
  telefon: boolean;
  jasneLogo: boolean;
  stan: StanLogowania;
  motyw: "ciemny" | "jasny";
  zmienMotyw: () => void;
  dane: DaneSystemowe;
  /** kursor w polu od razu – tylko na pełnym ekranie komputera */
  autoFokus?: boolean;
}) {
  const liczby = { zawodnicy: dane.strony.wszystkie.filter((t) => !t.druzynowy).length, druzyny: dane.strony.wszystkie.filter((t) => t.druzynowy).length };
  return (
    <LogowanieNadAplikacja
      telefon={telefon}
      jasneLogo={jasneLogo}
      stan={stan}
      motyw={motyw}
      zmienMotyw={zmienMotyw}
      autoFokus={autoFokus}
      liczbyMenu={liczby}
      powrot="Mecze › Ireland – Austria"
      tlo={<StronaGlowna wariant="c" dane={dane.strony} telefon={telefon} />}
    />
  );
}
