"use client";

import { usePathname, useRouter } from "next/navigation";
import { startTransition, useEffect, useState } from "react";

import "../../atomy.css";
import "../../atomy2.css";
import "../../elementy.css";
import "../../strony.css";
import "../../systemowe.css";

import type { MeczE } from "../../_dane/elementy";
import type { MeczZakonczony } from "../../_dane/zakonczony";
import { fmtLinia } from "@/lib/format";

import { CzasProvider } from "../czas";
import { WierszA } from "../elementy/mecz";
import { Lnk, LinkiAplikacji } from "../linki";
import { IkonaSzukaj } from "../szkielet/ikonyNav";
import { Komunikat, ZnakRysowany } from "./Logowanie";
import { UkladSys } from "./Systemowe";

/*
 * Etap 7 – strony systemowe w aplikacji (zatwierdzone S.2–S.4 z warsztatu):
 * 404 z prawdziwym adresem i wyszukiwarką, błąd z „Spróbuj ponownie”
 * i identyfikatorem, pasek braku internetu nad treścią.
 */

/** szukanie z treści strony – paletę trzyma szkielet aplikacji */
export const otworzSzukaj = (q = "") => window.dispatchEvent(new CustomEvent("footstats:szukaj", { detail: q }));

const dataDnia = (k: string) => {
  const d = new Date(`${k}T12:00:00Z`);
  return `${["nd", "pn", "wt", "śr", "cz", "pt", "sb"][d.getUTCDay()]} ${d.getUTCDate()}.${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
};

/** słowo do szukania z adresu: /zawodnik/lewandowski-r → „lewandowski r”; same cyfry nic nie mówią */
function slowoZAdresu(sciezka: string): string {
  const ost = decodeURIComponent(sciezka.split("/").filter(Boolean).at(-1) ?? "");
  const slowo = ost.replace(/[-_+.]+/g, " ").trim();
  return slowo.length >= 3 && !/^\d+$/.test(slowo) ? slowo.slice(0, 40) : "";
}

export function NieMaAplikacji({
  najblizsze,
  teraz,
  wariant = "strona",
  bezSzukania = false,
  zakonczony = null,
}: {
  najblizsze: MeczE[];
  teraz: number;
  wariant?: "strona" | "mecz";
  /** rozegrany mecz z naszymi typami (7B) – zamiast najbliższych meczów */
  zakonczony?: MeczZakonczony | null;
  /** poza menu aplikacji nie ma palety – przycisk szukania by nic nie robił */
  bezSzukania?: boolean;
}) {
  const sciezka = usePathname();
  const router = useRouter();
  const slowo = slowoZAdresu(sciezka);
  const mecz = wariant === "mecz";
  const z = mecz ? zakonczony : null;
  const ok = z ? z.typy.filter((t) => t.wynik === "wygrany").length : 0;
  const n = z ? z.typy.filter((t) => t.wynik !== "zwrot").length : 0;
  return (
    <LinkiAplikacji>
      <CzasProvider teraz={teraz}>
        <div className="ap-sys">
          <UkladSys
            znak={<ZnakRysowany koniec={z ? "pelny" : "brak"} className="sy-znak-ilu" />}
            dol={
              z ? (
                <section className="sy-mecz-wyniki" aria-label={`Typy z meczu ${z.mecz}`}>
                  <header>
                    <b>{z.mecz}</b>
                    <span>{dataDnia(z.dzien)}</span>
                    <em>{n > 0 ? `weszło ${ok} z ${n}` : "same zwroty"}</em>
                  </header>
                  {z.typy.map((t, i) => (
                    <div key={i} className="sy-mecz-typ" data-wynik={t.wynik}>
                      <span className="sy-mecz-znak" aria-label={t.wynik === "wygrany" ? "weszło" : t.wynik === "przegrany" ? "nie weszło" : "zwrot"}>
                        {t.wynik === "wygrany" ? "✓" : t.wynik === "przegrany" ? "✕" : "↺"}
                      </span>
                      <span className="sy-mecz-opis">
                        <small>{t.kto}</small>
                        <span>
                          <b>{t.rynek.replace(/\s*drużyny\s*/, " ").trim()}</b> {t.strona === "ponizej" ? "poniżej" : "powyżej"} <strong>{fmtLinia(t.linia)}</strong>
                        </span>
                      </span>
                      <span className="sy-mecz-bylo">
                        <small>było</small>
                        <b>{t.faktyczna ?? "–"}</b>
                      </span>
                    </div>
                  ))}
                </section>
              ) : najblizsze.length > 0 && (
                <section className="sy-najblizsze el-liga" aria-label="Najbliższe mecze z typami">
                  <div className="sy-najblizsze-glowa">
                    <b>Najbliższe mecze z typami</b>
                    <span>wejdź w mecz albo przejdź do całej listy</span>
                  </div>
                  {najblizsze.map((m) => (
                    <WierszA key={m.id} m={m} wybierz={() => router.push(`/mecze/${m.id}`)} />
                  ))}
                </section>
              )
            }
          >
            <p className="sy-adres">
              <span>adres</span> {sciezka}
            </p>
            <h1 className="p-n">{z ? "Ten mecz już się skończył" : mecz ? "Tego meczu nie ma już w ofercie" : "Nie ma takiej strony"}</h1>
            <p className="sy-lead">
              {z ? (
                <>
                  <span>Strona meczu znika po ostatnim gwizdku.</span> <span>Nasze typy z tego meczu zostają w Wynikach.</span>
                </>
              ) : mecz ? (
                <>
                  <span>Strona meczu znika po ostatnim gwizdku albo gdy bukmacherzy zdejmą mecz z oferty.</span> <span>Nasze typy z rozegranych meczów zostają w Wynikach.</span>
                </>
              ) : (
                <>
                  <span>Adres mógł się zmienić albo w linku jest literówka.</span> <span>Poszukaj od razu albo wróć do typów na dziś.</span>
                </>
              )}
            </p>
            {!mecz && !bezSzukania && (
              <button type="button" className="sy-szukaj" onClick={() => otworzSzukaj(slowo)}>
                <IkonaSzukaj r={18} />
                {slowo && <span className="sy-szukaj-slowo">{slowo}</span>}
                <span className="sy-szukaj-podpowiedz">szukaj zawodnika, drużyny, meczu</span>
                <kbd>Ctrl K</kbd>
              </button>
            )}
            <div className="sy-akcje">
              {mecz ? (
                <>
                  <Lnk href={z ? `/model?dzien=${z.dzien}` : "/model"} className="a-guzik" data-t="glowny" data-r="l">
                    {z ? `Wyniki z ${dataDnia(z.dzien)}` : "Wyniki"} <span className="d-strzalka">→</span>
                  </Lnk>
                  <Lnk href="/mecze" className="a-guzik" data-t="drugi" data-r="l">
                    Wszystkie mecze
                  </Lnk>
                </>
              ) : (
                <>
                  <Lnk href="/" className="a-guzik" data-t="glowny" data-r="l">
                    Typy na dziś <span className="d-strzalka">→</span>
                  </Lnk>
                  <Lnk href="/mecze" className="a-guzik" data-t="drugi" data-r="l">
                    Wszystkie mecze
                  </Lnk>
                </>
              )}
            </div>
          </UkladSys>
        </div>
      </CzasProvider>
    </LinkiAplikacji>
  );
}

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
