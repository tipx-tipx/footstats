"use client";

import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";

import "../../atomy.css";
import "../../atomy2.css";
import "../../elementy.css";
import "../../strony.css";
import "../../systemowe.css";

import type { MeczE } from "../../_dane/elementy";
import type { MeczZakonczony } from "../../_dane/zakonczony";
import { fmtLinia } from "@/lib/format";

import { CzasProvider } from "../czas";
import { Lnk, LinkiAplikacji } from "../linki";
import { IkonaSzukaj } from "../szkielet/ikonyNav";
import { ZnakRysowany } from "./znak";
import { UkladSys } from "./UkladSys";

/*
 * Etap 7 – strony systemowe w aplikacji (zatwierdzone S.2–S.4 z warsztatu):
 * 404 z prawdziwym adresem i wyszukiwarką, błąd z „Spróbuj ponownie”
 * i identyfikatorem, pasek braku internetu nad treścią.
 */

// lista meczów (WierszA z odliczaniem) ładuje się dopiero, gdy jest co pokazać –
// globalne 404 jej nie pokazuje, a siedzi w paczce każdej strony
const Najblizsze = dynamic(() => import("./Najblizsze").then((m) => m.Najblizsze));

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
              ) : najblizsze.length > 0 && <Najblizsze najblizsze={najblizsze} />
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
