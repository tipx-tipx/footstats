"use client";

import { startTransition, useEffect, useState } from "react";

import "../../atomy.css";
import "../../atomy2.css";
import "../../systemowe.css";

import { Lnk, LinkiAplikacji } from "../linki";
import { Komunikat } from "./Komunikat";
import { UkladSys } from "./UkladSys";
import { ZnakRysowany } from "./znak";

/*
 * Błąd strony – osobny plik, bo granica błędu ładuje się na KAŻDEJ stronie
 * (zabezpieczenie), więc nie może ciągnąć listy meczów ani warsztatu.
 */

/* ---- błąd ----------------------------------------------------------------- */

// po „Spróbuj ponownie” granica dostaje NOWY błąd (albo montuje się od nowa) –
// wtedy mówimy wprost, że błąd się powtarza. Po udanej próbie granica znika
// i znacznik się zeruje.
let poProbie = false;

/** `ponow` = unstable_retry granicy błędu: pobiera stronę od nowa i renderuje ją zamiast błędu */
export function BladAplikacji({ blad, digest, ponow: ponowStrone }: { blad: Error; digest?: string; ponow: () => void }) {
  const [trwa, setTrwa] = useState(false);
  const [powtarza, setPowtarza] = useState(() => poProbie);
  const [poprzedni, setPoprzedni] = useState(blad);
  if (blad !== poprzedni) {
    setPoprzedni(blad);
    setTrwa(false);
    if (poProbie) setPowtarza(true);
  }
  useEffect(
    () => () => {
      poProbie = false;
    },
    [],
  );
  const [skopiowano, setSkopiowano] = useState(false);
  useEffect(() => {
    if (!skopiowano) return;
    const t = setTimeout(() => setSkopiowano(false), 1600);
    return () => clearTimeout(t);
  }, [skopiowano]);

  const ponow = () => {
    poProbie = true;
    setTrwa(true);
    startTransition(() => ponowStrone());
  };
  const kopiuj = async () => {
    try {
      await navigator.clipboard.writeText(digest ?? "");
      setSkopiowano(true);
    } catch {
      /* brak uprawnień do schowka – identyfikator widać, da się go przepisać */
    }
  };

  return (
    <LinkiAplikacji>
      <div className="ap-sys">
        <UkladSys znak={<ZnakRysowany koniec="blad" className="sy-znak-ilu" />}>
          <h1 className="p-n">Nie udało się wczytać strony</h1>
          <p className="sy-lead">
            <span>Wystąpił błąd po naszej stronie.</span> <span>Spróbuj ponownie – zwykle to wystarcza.</span>
          </p>
          {powtarza && (
            <div className="sy-blad-kom">
              <Komunikat rodzaj="uwaga" tytul="Błąd się powtarza">
                Spróbuj ponownie za kilka minut. {digest ? "Jeśli problem nie zniknie, przekaż nam identyfikator błędu." : "Jeśli problem nie zniknie, daj nam znać."}
              </Komunikat>
            </div>
          )}
          <div className="sy-akcje">
            <button type="button" className="a-guzik" data-t="glowny" data-r="l" aria-busy={trwa} disabled={trwa} onClick={ponow}>
              {trwa ? (
                <>
                  <span className="d-krecik" aria-hidden /> Wczytuję ponownie
                </>
              ) : (
                "Spróbuj ponownie"
              )}
            </button>
            <Lnk href="/" className="a-guzik" data-t="drugi" data-r="l">
              Przejdź do typów
            </Lnk>
          </div>
          {digest && (
            <div className="sy-kod">
              <span className="sy-kod-etykieta">Identyfikator błędu</span>
              <code>{digest}</code>
              <button type="button" onClick={kopiuj} aria-live="polite">
                {skopiowano ? "✓ Skopiowano" : "Kopiuj"}
              </button>
            </div>
          )}
        </UkladSys>
      </div>
    </LinkiAplikacji>
  );
}
