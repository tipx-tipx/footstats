"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import "../../atomy.css";
import "../../atomy2.css";
import "../../elementy.css";
import "../../szkielet.css";
import "../../strony.css";
import "../../systemowe.css";

import { przelaczMotyw, useCiemny } from "../motyw";
import { SzkieletStrony } from "./SzkieletStrony";
import { LogowanieNadAplikacja, type StanLogowania, type WynikLogowania } from "./Logowanie";

/*
 * Etap 7 – logowanie N „nad aplikacją” na prawdziwym haśle. Pod rozmytym
 * oknem leży szkielet strony, nie dzisiejsze typy: bez hasła nic z oferty
 * nie może trafić do HTML. Po wejściu – tam, skąd przekierowała bramka.
 */

async function zaloguj(haslo: string): Promise<WynikLogowania> {
  const res = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ haslo }),
  }).catch(() => null);
  if (!res) return "siec";
  if (res.ok) return "ok";
  if (res.status === 429) return "limit";
  if (res.status === 401) return "zle";
  return "siec";
}

/** „sesja wygasła”: dokąd wróci – z adresu, bez zgadywania nazw (meczu ani zawodnika strona logowania nie zna) */
function opisPowrotu(dalej: string): string | undefined {
  const sciezka = dalej.split("?")[0];
  if (sciezka === "/") return undefined;
  if (/^\/mecze\/\d+/.test(sciezka)) return "strona meczu";
  if (/^\/zawodnik\/\d+/.test(sciezka)) return "strona zawodnika";
  const MENU: Record<string, string> = { "/druzyny": "Drużyny", "/kupony": "Kupony", "/mecze": "Mecze", "/model": "Wyniki", "/jak-to-dziala": "Jak czytać typy" };
  return MENU[sciezka] ?? "strona, którą oglądałeś";
}

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

export function LogowanieAplikacji({ telefon: telefonStart, stan, dalej }: { telefon: boolean; stan: StanLogowania; dalej: string }) {
  const router = useRouter();
  const telefon = useTelefon(telefonStart);
  const ciemny = useCiemny();
  const poWejsciu = useCallback(() => {
    router.replace(dalej);
    router.refresh();
  }, [router, dalej]);

  return (
    <div className="nowa sy-pelny sy-aplikacja" style={{ containerType: "inline-size" }}>
      <LogowanieNadAplikacja
        key={String(telefon)}
        telefon={telefon}
        autoFokus={!telefon}
        jasneLogo={ciemny}
        stan={stan}
        motyw={ciemny ? "ciemny" : "jasny"}
        zmienMotyw={przelaczMotyw}
        tlo={<SzkieletStrony />}
        liczbyMenu={{}}
        zaloguj={zaloguj}
        poWejsciu={poWejsciu}
        powrot={stan === "sesja" ? opisPowrotu(dalej) : undefined}
      />
    </div>
  );
}
