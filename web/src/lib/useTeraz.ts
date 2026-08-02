"use client";

import { useEffect, useState } from "react";

/**
 * Aktualny czas (sekundy) – z zegara PRZEGLĄDARKI, ale dopiero po hydracji.
 *
 * PO CO TO ISTNIEJE (zgłoszenie usera 2026-08-02: „mecze się odbyły, a nadal
 * wiszą"). Strony produktu są budowane z wyprzedzeniem i odświeżane co 60 s,
 * ale Next oddaje wersję Z CACHE i dopiero W TLE buduje nową. Przy jednym
 * użytkowniku pierwsze wejście danego dnia pokazuje HTML z poprzedniej wizyty –
 * a odcięcie „mecz się zaczął, zdejmij typ" (lib/data.tylkoNadchodzace)
 * wykonało się WTEDY, nie teraz. Efekt: rozegrane mecze na liście, dopóki nie
 * odświeżysz drugi raz.
 *
 * Serwerowego odcięcia NIE zastępujemy – ono nadal chroni payload i kolejność.
 * To jest druga linia: przeglądarka zna prawdziwą godzinę i chowa to, czego
 * i tak nie da się już obstawić.
 *
 * HYDRACJA. Pierwszy render MUSI dać dokładnie to, co serwer, inaczej React
 * zgłosi rozjazd i przerysuje drzewo. Dlatego startujemy od znacznika
 * serwerowego i przechodzimy na zegar klienta dopiero w efekcie.
 *
 * @param serwerowy znacznik z serwera (lib/data.terazTs) – wartość startowa
 * @param krokMs    co ile odświeżać; domyślnie minuta, bo chodzi o gwizdki,
 *                  nie o sekundnik
 */
export function useTeraz(serwerowy: number, krokMs = 60_000): number {
  const [teraz, setTeraz] = useState(serwerowy);
  useEffect(() => {
    const tik = () => setTeraz(Math.floor(Date.now() / 1000));
    tik();
    const id = setInterval(tik, krokMs);
    return () => clearInterval(id);
  }, [krokMs]);
  // gdyby zegar klienta był cofnięty (zła data w systemie), trzymamy się
  // serwerowego – lepiej pokazać typ o minutę za długo niż schować wszystko
  return Math.max(teraz, serwerowy);
}
