"use client";

import { Lnk } from "../linki";
import { motion } from "framer-motion";
import { useMemo, useState } from "react";

import { fmtLinia } from "@/lib/format";

import { dzienTs, etykietaDnia } from "../../_dane/formatCzasu";
import type { DrabinkaV } from "../../_dane/elementy";
import type { DzienV, TypLekki } from "../../_dane/przygotuj";
import type { DaneStron, KartaStrony } from "../../_dane/strony";
import { FiltryV3 } from "../atomy2/filtry3";
import { odm } from "../atomy2/filtry2";
import { DniD, KafelekD, KratkiD, kursTypu } from "../atomy2/podstawowe";
import { ScenaDrabinki } from "../elementy/drabinka";
import { IkonaRynku } from "../elementy/ikonyRynkow";
import { KartaA, Powody } from "../elementy/karta";
import { useTeraz } from "../czas";
import { Herb } from "../Herb";

/*
 * Etap 5 – strona główna (Zawodnicy) w trzech układach. Zamiast hero:
 * „tablica dnia” z prawdziwych danych – najmocniejszy typ, kupon dnia
 * i uczciwe podsumowanie ostatnich 7 dni.
 */

type Rodzaj = "zawodnicy" | "druzyny";
const liczba = (v: number | null) => (v === null ? "–" : v.toFixed(1).replace(".", ","));
const strona = (s: string) => (s === "ponizej" ? "poniżej" : "powyżej");
const proc = (p: number) => `${Math.round(p * 100)}%`;
const kursTxt = (k: number) => k.toFixed(2).replace(".", ",");
const rynekKrotko = (r: string) => r.replace(/\s*drużyny\s*/, " ").trim();
const DNI_TYG = ["nd", "pn", "wt", "śr", "cz", "pt", "sb"];
// wejście kart i słupków w CSS (strony.css: .st-wejscie, .st-slupek-slup): rusza przy
// pierwszym malowaniu, bez czekania na JavaScript – treść z serwera nigdy nie jest ukryta
const wejscie = (i: number) => ({ className: "st-wejscie", style: { "--i": i } as React.CSSProperties });

/* szalik: pasek w barwach drużyny zamiast ozdobnego gradientu */
function Szalik({ t }: { t: KartaStrony }) {
  return (
    <span
      className="st-szalik"
      aria-hidden
      style={{ backgroundImage: `repeating-linear-gradient(-45deg, ${t.druzyna.c1} 0 9px, ${t.druzyna.c2} 9px 18px)` }}
    />
  );
}

/* ---- typ dnia --------------------------------------------------------- */

export function TypDnia({ t, uklad = "duzy" }: { t: KartaStrony; uklad?: "duzy" | "boczny" | "maly"; }) {
  const maly = uklad === "maly";
  return (
    <article className="st-typ-dnia" data-uklad={uklad} style={{ "--barwa": t.druzyna.c1 } as React.CSSProperties}>
      <Szalik t={t} />
      <div className="st-td-glowa">
        <span className="st-kicker">{maly ? "Mocny typ" : "Typ dnia"}</span>
        {uklad !== "duzy" && (
          <span className="st-td-mecz">
            {t.gosp} – {t.gosc} · {t.dzien.toLowerCase()} {t.godzina}
          </span>
        )}
      </div>
      <div className="st-td-kto">
        <Herb d={t.druzyna} tryb="prawdziwy" rozmiar={maly ? 26 : 34} />
        <div style={{ minWidth: 0 }}>
          <div className="st-td-nazwisko p-n">{t.podmiotId ? <Lnk href={`/zawodnik/${t.podmiotId}`}>{t.kto}</Lnk> : t.kto}</div>
          <div className="st-td-pod">
            {t.pozycja ? `${t.pozycja} · ` : ""}
            {t.druzyna.nazwa}
          </div>
        </div>
      </div>
      <div className="st-td-zaklad">
        <IkonaRynku rynek={t.rynek} rozmiar={maly ? 16 : 20} />
        <b>{rynekKrotko(t.rynek)}</b>
        <span>{strona(t.strona)}</span>
        <strong>{fmtLinia(t.linia)}</strong>
      </div>
      <div className="st-td-liczby">
        <div className="st-td-szansa">
          <span className="p-n">{proc(t.szansa)}</span>
          <small>szansy według nas</small>
        </div>
        <KafelekD k={kursTypu(t)} />
      </div>
      {!maly && (
        <div className="st-td-historia">
          <KratkiD t={t} />
        </div>
      )}
      {uklad === "duzy" && t.powody.length > 0 && (
        <div className="st-td-powody">
          <Powody powody={t.powody} ile={3} />
        </div>
      )}
      {uklad === "duzy" && (
        <div className="st-td-spotkanie">
          <span className="st-td-strona">
            <b>{t.gosp}</b>
            <Herb d={t.gospD} tryb="prawdziwy" rozmiar={30} />
          </span>
          <span className="st-td-kiedy">
            <small>{t.dzien.toLowerCase()}</small>
            {t.godzina}
          </span>
          <span className="st-td-strona">
            <Herb d={t.goscD} tryb="prawdziwy" rozmiar={30} />
            <b>{t.gosc}</b>
          </span>
        </div>
      )}
    </article>
  );
}

/* ---- C: karta „najmocniejsze” ----------------------------------------- */

/* passa: 10 kresek od najnowszego meczu – najmocniejszy argument w jednym rzędzie */
function Passa({ t }: { t: KartaStrony }) {
  const mecze = t.historia.map((v, i) => ({ v, min: t.minuty[i] ?? 90 })).reverse();
  const trafil = (v: number) => (t.strona === "ponizej" ? v < t.linia : v > t.linia);
  const zagrane = mecze.filter((m) => m.min > 0);
  const ok = zagrane.filter((m) => trafil(m.v)).length;
  return (
    <div className="st-passa">
      <span className="st-passa-kreski" aria-hidden>
        {mecze.map((m, i) => (
          <i key={i} data-s={m.min <= 0 ? "nz" : trafil(m.v) ? "ok" : "nie"} />
        ))}
      </span>
      <span>
        weszło w{" "}
        <b>
          {ok} z {zagrane.length}
        </b>{" "}
        ostatnich meczów
      </span>
    </div>
  );
}

function KartaMocna({ t }: { t: KartaStrony }) {
  return (
    <article className="st-mocna" style={{ "--barwa": t.druzyna.c1 } as React.CSSProperties}>
      <div className="st-mocna-mecz">
        <span>
          {t.gosp} – {t.gosc}
        </span>
        <time>
          {t.dzien.toLowerCase()} {t.godzina}
        </time>
      </div>
      <div className="st-td-kto">
        <Herb d={t.druzyna} tryb="prawdziwy" rozmiar={28} />
        <div style={{ minWidth: 0 }}>
          <div className="st-td-nazwisko p-n">{t.podmiotId ? <Lnk href={`/zawodnik/${t.podmiotId}`}>{t.kto}</Lnk> : t.kto}</div>
          <div className="st-td-pod">
            {t.podmiotTyp === "druzyna" ? `przeciw ${t.rywal.nazwa}` : `${t.pozycja ? `${t.pozycja} · ` : ""}${t.druzyna.nazwa}`}
          </div>
        </div>
      </div>
      <div className="st-td-zaklad">
        <IkonaRynku rynek={t.rynek} rozmiar={16} />
        <b>{rynekKrotko(t.rynek)}</b>
        <span>{strona(t.strona)}</span>
        <strong>{fmtLinia(t.linia)}</strong>
      </div>
      {t.historia.length > 0 && <Passa t={t} />}
      <div className="st-td-liczby">
        <div className="st-td-szansa">
          <span className="p-n">{proc(t.szansa)}</span>
          <small>szansy</small>
        </div>
        <KafelekD k={kursTypu(t)} />
      </div>
    </article>
  );
}

/* ---- kupon dnia ------------------------------------------------------- */

export function KuponDniaMini({ k, pasek = false }: { k: DaneStron["kuponDnia"]; pasek?: boolean }) {
  if (!k) return null;
  if (pasek) {
    return (
      <Lnk href="/kupony" className="st-pasek-poz">
        <span className="st-kicker">Kupon dnia</span>
        <b className="p-n">×{kursTxt(k.kurs)}</b>
        <span className="p-t3">
          {k.nogi.length} {odm(k.nogi.length)} z różnych meczów
        </span>
        <span className="st-strzalka" aria-hidden>
          →
        </span>
      </Lnk>
    );
  }
  return (
    <section className="st-blok st-kupon">
      <div className="st-blok-glowa">
        <span className="st-kicker">Kupon dnia</span>
        <b className="p-n st-kupon-kurs">×{kursTxt(k.kurs)}</b>
      </div>
      <ol className="st-kupon-nogi">
        {k.nogi.map((n) => (
          <li key={n.kto + n.opis}>
            <time>
              <small>{n.dzien.toLowerCase()}</small>
              {n.godzina}
            </time>
            <span>
              <b>{n.kto}</b>
              <small>{n.opis}</small>
            </span>
            <em>{kursTxt(n.kurs)}</em>
          </li>
        ))}
      </ol>
      <a className="a-guzik st-kupon-guzik" data-t="drugi" data-r="s">
        Dopasuj w Kuponach
      </a>
    </section>
  );
}

/* ---- ostatnie 7 dni --------------------------------------------------- */

export function WynikiMini({ wyniki, suma, pasek = false }: { wyniki: DaneStron["wyniki"]; suma: DaneStron["sumaWynikow"]; pasek?: boolean }) {
  const [wskazany, setWskazany] = useState<number | null>(null);
  const dzien = (klucz: string) => {
    const d = new Date(`${klucz}T12:00:00Z`);
    return { tyg: DNI_TYG[d.getUTCDay()], data: `${d.getUTCDate()}.${String(d.getUTCMonth() + 1).padStart(2, "0")}` };
  };
  const w = wskazany !== null ? wyniki[wskazany] : null;

  // w pasku cały element jest linkiem do Wyników – słupki to sama grafika
  // (przycisk w linku to niepoprawny HTML, a na telefonie 10-pikselowy cel)
  const slupki = pasek ? (
    <div className="st-slupki" aria-hidden>
      {wyniki.map((d, i) => (
        <span key={d.dzien} className="st-slupek">
          <span className="st-slupek-slup" style={{ height: "100%", "--i": i } as React.CSSProperties}>
            <i className="st-slupek-nie" style={{ flexGrow: d.n - d.ok }} />
            <i className="st-slupek-ok" style={{ flexGrow: d.ok }} />
          </span>
        </span>
      ))}
    </div>
  ) : (
    <div className="st-slupki" onMouseLeave={() => setWskazany(null)}>
      {wyniki.map((d, i) => (
        <button
          key={d.dzien}
          type="button"
          className="st-slupek"
          aria-label={`${dzien(d.dzien).tyg} ${dzien(d.dzien).data}: ${d.ok} z ${d.n} weszło`}
          onMouseEnter={() => setWskazany(i)}
          onFocus={() => setWskazany(i)}
          onClick={() => setWskazany(i)}
          data-wskazany={wskazany === i || undefined}
        >
          <span className="st-slupek-slup" style={{ height: "100%", "--i": i } as React.CSSProperties}>
            <i className="st-slupek-nie" style={{ flexGrow: d.n - d.ok }} />
            <i className="st-slupek-ok" style={{ flexGrow: d.ok }} />
          </span>
          {!pasek && <small>{dzien(d.dzien).tyg}</small>}
        </button>
      ))}
    </div>
  );

  if (pasek) {
    return (
      <Lnk href="/model" className="st-pasek-poz">
        <span className="st-kicker">Ostatnie 7 dni</span>
        <b className="p-n">
          {suma.ok} z {suma.n}
        </b>
        <span className="p-t3">weszło</span>
        {slupki}
      </Lnk>
    );
  }

  return (
    <section className="st-blok st-wyniki">
      <div className="st-blok-glowa">
        <span className="st-kicker">Ostatnie 7 dni</span>
        <Lnk href="/model" className="st-link">Każdy wynik</Lnk>
      </div>
      <div className="st-wyniki-liczba">
        <b className="p-n">
          {w ? w.ok : suma.ok} z {w ? w.n : suma.n}
        </b>
        <span>{w ? `weszło ${dzien(w.dzien).tyg} ${dzien(w.dzien).data}` : "typów weszło"}</span>
      </div>
      {slupki}
      <p className="st-wyniki-stopka">Każdy typ zostaje w historii – także te, które nie weszły.</p>
    </section>
  );
}

/* ---- wspólne ---------------------------------------------------------- */

function Naglowek({ rodzaj = "zawodnicy" }: { rodzaj?: Rodzaj }) {
  return (
    <div className="st-naglowek">
      <h1 className="p-n">{rodzaj === "druzyny" ? "Drużyny" : "Zawodnicy"}</h1>
      {/* każde zdanie w swojej linii – bez sierotki na końcu */}
      {rodzaj === "druzyny" ? (
        <p>
          <span>Gole, rożne i kartki całych drużyn.</span> <span>Tylko z lig, które znamy najlepiej.</span>
        </p>
      ) : (
        <p>
          <span>Codziennie sprawdzamy ponad 1600 zakładów.</span> <span>Zostawiamy te, które wchodzą najczęściej.</span>
        </p>
      )}
    </div>
  );
}

function useStrona(dane: DaneStron, rodzaj: Rodzaj = "zawodnicy") {
  const TERAZ = useTeraz();
  return useMemo(() => {
    const karty = dane.kartyStrony.filter((k) => k.podmiotTyp === (rodzaj === "druzyny" ? "druzyna" : "zawodnik"));
    const poId = new Map(karty.map((k) => [k.id, k]));
    // najbliższy dzień, w którym są typy – „typ dnia” to typ z TEGO dnia
    const przyszle = karty.filter((k) => k.ts > TERAZ);
    const dzien = przyszle.map((k) => dzienTs(k.ts)).sort()[0];
    const etykietaDnia = przyszle.find((k) => dzienTs(k.ts) === dzien)?.dzien ?? "Dziś";
    // na wierzch tylko typ, który w historii faktycznie wchodził (min. 7 z 10)
    const historiaOk = (k: KartaStrony) => {
      const zagrane = k.historia.filter((_, i) => (k.minuty[i] ?? 90) > 0);
      const weszlo = zagrane.filter((v) => (k.strona === "ponizej" ? v < k.linia : v > k.linia)).length;
      return zagrane.length >= 5 && weszlo / zagrane.length >= 0.7;
    };
    const nadchodzace = przyszle
      .filter((k) => dzienTs(k.ts) === dzien && k.polka === "wysoka_szansa")
      .sort((a, b) => Number(historiaOk(b)) - Number(historiaOk(a)) || b.szansa - a.szansa || a.ts - b.ts);
    const typDnia = nadchodzace[0];
    // trzy najmocniejsze – każdy z innego meczu; najpierw najbliższy dzień,
    // a gdy w nim mniej niż 3 mecze – kolejne dni
    const kandydaci = przyszle
      .filter((k) => k.polka === "wysoka_szansa")
      .sort(
        (a, b) =>
          dzienTs(a.ts).localeCompare(dzienTs(b.ts)) ||
          Number(historiaOk(b)) - Number(historiaOk(a)) ||
          b.szansa - a.szansa ||
          a.ts - b.ts,
      );
    // na wierzch tylko typy z mocną historią; słabsze dopiero, gdy mocnych brakuje
    const top: KartaStrony[] = [];
    for (const k of [...kandydaci.filter(historiaOk), ...kandydaci.filter((x) => !historiaOk(x))]) {
      if (top.length === 3) break;
      if (!top.some((x) => x.meczId === k.meczId)) top.push(k);
    }
    top.sort((a, b) => a.ts - b.ts);
    const jedenDzien = top.every((k) => dzienTs(k.ts) === dzien);
    const lista = dane.wszystkie.filter((t) => (rodzaj === "druzyny" ? t.druzynowy : !t.druzynowy));
    return { poId, typDnia, top, lista, etykietaDnia, jedenDzien };
  }, [dane, rodzaj, TERAZ]);
}

function naJakiDzien(etykieta: string, jedenDzien: boolean) {
  if (!jedenDzien) return "na najbliższe dni";
  return etykieta === "Dziś" || etykieta === "Jutro" ? `na ${etykieta.toLowerCase()}` : `– ${etykieta}`;
}

type Uklad = { dane: DaneStron; telefon: boolean; otworz?: (id: number) => void };

/**
 * Wybór dnia na liście typów (01.10): dni, w których MAMY typy na tej stronie,
 * z liczbą typów (u zawodników razem z drabinkami) – nie liczba meczów
 * w ofercie. Domyślnie dziś, a gdy dziś nic – najbliższy dzień z typami.
 */
const BRAK_DRABINEK: DrabinkaV[] = [];

function useWyborDnia(lista: TypLekki[], drabinki: DrabinkaV[]) {
  const TERAZ = useTeraz();
  const dzis = dzienTs(TERAZ);
  const dni = useMemo<DzienV[]>(() => {
    const ile = new Map<string, number>();
    for (const t of lista) {
      const k = dzienTs(t.ts);
      ile.set(k, (ile.get(k) ?? 0) + 1);
    }
    for (const d of drabinki) {
      if (!d.ts) continue;
      const k = dzienTs(d.ts);
      ile.set(k, (ile.get(k) ?? 0) + 1);
    }
    return [...ile.entries()]
      .filter(([k]) => k >= dzis)
      .sort(([a], [b]) => (a < b ? -1 : 1))
      .map(([klucz, n]) => ({ klucz, etykieta: etykietaDnia(klucz, dzis), ile: n }));
  }, [lista, drabinki, dzis]);
  const [wybrany, setWybrany] = useState<string | null>(null);
  const dzien = (wybrany && dni.some((d) => d.klucz === wybrany) ? wybrany : (dni.find((d) => d.klucz === dzis) ?? dni[0])?.klucz) ?? dzis;
  return { dni, dzien, dzis, setDzien: setWybrany };
}

type Grupy = { klucz: (t: TypLekki, k?: KartaStrony) => string; naglowek: (t: TypLekki, k: KartaStrony | undefined, ile: number) => React.ReactNode };

function Lista({
  dane,
  telefon,
  grupy = false,
  ile = 8,
  obokPolek,
  rodzaj = "zawodnicy",
  wlasneGrupy,
  bezMeczu,
  zDniami = false,
}: Uklad & { grupy?: boolean; ile?: number; obokPolek?: React.ReactNode; rodzaj?: Rodzaj; wlasneGrupy?: Grupy; bezMeczu?: boolean; zDniami?: boolean }) {
  const { poId, lista } = useStrona(dane, rodzaj);
  const wszystkieDrabinki = rodzaj === "druzyny" ? BRAK_DRABINEK : dane.drabinkiLista;
  const wybor = useWyborDnia(lista, wszystkieDrabinki);
  // bez paska dni (układy warsztatu) – wszystkie dni jak dotąd
  const listaDnia = zDniami ? lista.filter((t) => dzienTs(t.ts) === wybor.dzien) : lista;
  const drabinkiDnia = zDniami ? wszystkieDrabinki.filter((d) => d.ts && dzienTs(d.ts) === wybor.dzien) : wszystkieDrabinki;
  const nastepnyZDrabinka = wybor.dni.find((d) => d.klucz > wybor.dzien && wszystkieDrabinki.some((x) => x.ts && dzienTs(x.ts) === d.klucz));
  const etykietaWybranego = wybor.dni.find((d) => d.klucz === wybor.dzien)?.etykieta ?? etykietaDnia(wybor.dzien, wybor.dzis);
  const grupuj = useMemo(
    () =>
      wlasneGrupy
        ? {
            klucz: (t: TypLekki) => wlasneGrupy.klucz(t, poId.get(t.id)),
            naglowek: (t: TypLekki, ile: number) => wlasneGrupy.naglowek(t, poId.get(t.id), ile),
          }
        : grupy
        ? {
            klucz: (t: TypLekki) => String(poId.get(t.id)?.meczId ?? t.mecz),
            naglowek: (t: TypLekki, ile: number) => {
              const k = poId.get(t.id);
              return (
                <div className="st-grupa">
                  {k && <Herb d={k.gospD} tryb="prawdziwy" rozmiar={18} />}
                  <b>{k?.gosp ?? t.mecz}</b>
                  {k && (
                    <>
                      <span className="p-t4">–</span>
                      <b>{k.gosc}</b>
                      <Herb d={k.goscD} tryb="prawdziwy" rozmiar={18} />
                    </>
                  )}
                  <span className="st-grupa-meta">
                    {k && <time>{k.godzina}</time>}
                    <span>
                      {ile} {odm(ile)}
                    </span>
                  </span>
                </div>
              );
            },
          }
        : undefined,
    [grupy, poId, wlasneGrupy],
  );
  return (
    <FiltryV3
      wszystkie={listaDnia}
      ligi={dane.ligiTypow}
      drabinki={drabinkiDnia.length}
      telefon={telefon}
      ile={ile}
      grupuj={grupuj}
      obokPolek={zDniami ? <DniD dni={wybor.dni} wybrany={wybor.dzien} zmien={wybor.setDzien} /> : obokPolek}
      bezDrabinek={rodzaj === "druzyny"}
      wiersz={(t) => {
        const k = poId.get(t.id);
        return k ? <KartaA t={k} bezMeczu={bezMeczu ?? (grupy || !!wlasneGrupy)} /> : null;
      }}
      drabinkaTresc={
        drabinkiDnia.length ? (
          <div className="st-drabinki">
            {drabinkiDnia.map((d) => (
              <ScenaDrabinki key={d.klucz ?? d.kto} wariant="a" d={d} />
            ))}
          </div>
        ) : (
          <div className="d-pusty">
            <div className="p-n" style={{ fontSize: 17 }}>
              {etykietaWybranego === "Dziś" || etykietaWybranego === "Jutro" ? `Na ${etykietaWybranego.toLowerCase()}` : `Na ${etykietaWybranego}`} nie mamy drabinek
            </div>
            {nastepnyZDrabinka ? (
              <button type="button" className="a-guzik" data-t="drugi" data-r="m" onClick={() => wybor.setDzien(nastepnyZDrabinka.klucz)}>
                Najbliższe: {nastepnyZDrabinka.etykieta.toLowerCase()} <span className="d-strzalka">→</span>
              </button>
            ) : (
              <p>Drabinka pojawia się, gdy zawodnik przechodzi nasze sito – nie co dzień.</p>
            )}
          </div>
        )
      }
    />
  );
}

/* ---- A · tablica na górze --------------------------------------------- */

function UkladA({ dane, telefon }: Uklad) {
  const { typDnia } = useStrona(dane);
  return (
    <main className="st-strona st-a">
      <motion.div {...wejscie(0)}>
        <Naglowek />
      </motion.div>
      <div className="st-tablica">
        {typDnia && (
          <motion.div {...wejscie(1)} className="st-tablica-glowny">
            <TypDnia t={typDnia} />
          </motion.div>
        )}
        <div className="st-tablica-bok st-tylko-szeroki">
          <motion.div {...wejscie(2)}>
            <KuponDniaMini k={dane.kuponDnia} />
          </motion.div>
          <motion.div {...wejscie(3)}>
            <WynikiMini wyniki={dane.wyniki} suma={dane.sumaWynikow} />
          </motion.div>
        </div>
        <div className="st-tablica-paski st-tylko-waski">
          <KuponDniaMini k={dane.kuponDnia} pasek />
          <WynikiMini wyniki={dane.wyniki} suma={dane.sumaWynikow} pasek />
        </div>
      </div>
      <h2 className="st-h2 p-n">Wszystkie typy</h2>
      <DniD dni={dane.dni} />
      <Lista dane={dane} telefon={telefon} />
    </main>
  );
}

/* ---- B · dwie kolumny ------------------------------------------------- */

function UkladB({ dane, telefon }: Uklad) {
  const { typDnia } = useStrona(dane);
  return (
    <main className="st-strona st-b">
      <div className="st-b-glowa">
        <Naglowek />
      </div>
      <div className="st-b-glowna">
        <DniD dni={dane.dni} />
        <Lista dane={dane} telefon={telefon} ile={10} />
      </div>
      <aside className="st-b-bok" aria-label="Na dziś">
        {typDnia && <TypDnia t={typDnia} uklad="boczny" />}
        <KuponDniaMini k={dane.kuponDnia} />
        <WynikiMini wyniki={dane.wyniki} suma={dane.sumaWynikow} />
      </aside>
    </main>
  );
}

/* ---- C · najpierw najlepsze ------------------------------------------- */

function UkladC({ dane, telefon }: Uklad) {
  const { top, etykietaDnia, jedenDzien } = useStrona(dane);
  const naDzien = naJakiDzien(etykietaDnia, jedenDzien);
  return (
    <main className="st-strona st-c">
      <Naglowek />
      <section aria-labelledby="st-c-top">
        <h2 id="st-c-top" className="st-h2 p-n">
          Najmocniejsze {naDzien}
        </h2>
        <div className="st-c-top">
          {top.map((t, i) => (
            <div key={t.id} {...wejscie(i)}>
              <KartaMocna t={t} />
            </div>
          ))}
        </div>
        <div className="st-c-skrot">
          <KuponDniaMini k={dane.kuponDnia} pasek />
          <WynikiMini wyniki={dane.wyniki} suma={dane.sumaWynikow} pasek />
        </div>
      </section>
      <section aria-labelledby="st-c-lista">
        <h2 id="st-c-lista" className="st-h2 p-n">
          Wszystkie typy
        </h2>
        <Lista dane={dane} telefon={telefon} grupy ile={12} zDniami />
      </section>
    </main>
  );
}

/* =======================================================================
   Etap 5.2 – DRUŻYNY
   ======================================================================= */

/* pojedynek: średnie obu drużyn w rynkach typów – jak statystyki meczu w Sofascore */
/** po której stronie meczu jest nasz typ w danym rynku (kod team_*) */
type StronyTypow = Record<string, { gosp: boolean; gosc: boolean }>;

export function stronyTypow(karty: KartaStrony[], meczId: number, polka?: string): StronyTypow {
  const w: StronyTypow = {};
  for (const k of karty) {
    // tylko typy z półki, którą właśnie widać na liście
    if (k.meczId !== meczId || k.podmiotTyp !== "druzyna" || (polka !== undefined && k.polka !== polka)) continue;
    const kod = RYNEK_NA_KOD[rynekKrotko(k.rynek).replace(/\s*w meczu$/, "")] ?? "";
    const s = (w[kod] ??= { gosp: false, gosc: false });
    if (k.kto === "Cały mecz") {
      s.gosp = true;
      s.gosc = true;
    } else if (k.kto === k.gosp) s.gosp = true;
    else s.gosc = true;
  }
  return w;
}
const RYNEK_NA_KOD: Record<string, string> = {
  "Rzuty rożne": "team_corners",
  Gole: "team_goals",
  Strzały: "team_shots",
  "Strzały celne": "team_sot",
  Kartki: "team_cards",
  Faule: "team_fouls",
};

export function Pojedynek({
  k,
  rynki,
  ile,
  podpis = true,
  strony,
}: {
  k: KartaStrony;
  rynki: DaneStron["pojedynki"][number];
  ile: number;
  podpis?: boolean;
  /** gdy podane – wyróżniona jest strona drużyny z naszym typem, a nie większa liczba */
  strony?: StronyTypow;
}) {
  return (
    <div className="st-poj">
      <div className="st-poj-meta">
        <span>{k.liga}</span>
        <span>
          {k.dzien} {k.godzina} · {ile} {odm(ile)}
        </span>
      </div>
      <div className="st-poj-druzyny">
        <span className="st-poj-d">
          <Herb d={k.gospD} tryb="prawdziwy" rozmiar={30} />
          <b className="p-n">{k.gosp}</b>
        </span>
        <span className="st-poj-d st-poj-prawa">
          <b className="p-n">{k.gosc}</b>
          <Herb d={k.goscD} tryb="prawdziwy" rozmiar={30} />
        </span>
      </div>
      {rynki.length > 0 && (
        <div className="st-poj-rynki">
          {rynki.filter((r) => !strony || strony[r.kod]).map((r) => {
            const suma = (r.gosp ?? 0) + (r.gosc ?? 0) || 1;
            const wiekszy = (r.gosp ?? 0) >= (r.gosc ?? 0) ? "gosp" : "gosc";
            const s = strony?.[r.kod];
            const wyrozniony = { gosp: s ? s.gosp : wiekszy === "gosp", gosc: s ? s.gosc : wiekszy === "gosc" };
            return (
              <div key={r.kod} className="st-poj-rynek">
                <b data-wiekszy={wyrozniony.gosp || undefined}>{liczba(r.gosp)}</b>
                <span className="st-poj-nazwa">{r.nazwa}</span>
                <b data-wiekszy={wyrozniony.gosc || undefined}>{liczba(r.gosc)}</b>
                <span className="st-poj-pasy" aria-hidden>
                  <span className="st-poj-pas st-poj-pas-l">
                    <motion.i
                      data-wiekszy={wyrozniony.gosp || undefined}
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
                      style={{ width: `${((r.gosp ?? 0) / suma) * 100}%` }}
                    />
                  </span>
                  <span className="st-poj-pas">
                    <motion.i
                      data-wiekszy={wyrozniony.gosc || undefined}
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
                      style={{ width: `${((r.gosc ?? 0) / suma) * 100}%` }}
                    />
                  </span>
                </span>
              </div>
            );
          })}
          {podpis && <small className="st-poj-pod">średnio na mecz, z {rynki[0].n} ostatnich meczów każdej drużyny</small>}
        </div>
      )}
    </div>
  );
}

function NajmocniejszeDruzyn({ dane }: { dane: DaneStron }) {
  const { top, etykietaDnia, jedenDzien } = useStrona(dane, "druzyny");
  if (!top.length) return null;
  return (
    <section aria-labelledby="st-d-top">
      <h2 id="st-d-top" className="st-h2 p-n">
        Najmocniejsze {naJakiDzien(etykietaDnia, jedenDzien)}
      </h2>
      <div className="st-c-top">
        {top.map((t, i) => (
          <div key={t.id} {...wejscie(i)}>
            <KartaMocna t={t} />
          </div>
        ))}
      </div>
    </section>
  );
}

/* A · tak samo jak Zawodnicy – jedna logika na obu stronach */
function DruzynyA({ dane, telefon }: Uklad) {
  return (
    <main className="st-strona st-c">
      <Naglowek rodzaj="druzyny" />
      <NajmocniejszeDruzyn dane={dane} />
      <div className="st-c-skrot">
        <KuponDniaMini k={dane.kuponDnia} pasek />
        <WynikiMini wyniki={dane.wyniki} suma={dane.sumaWynikow} pasek />
      </div>
      <section aria-labelledby="st-d-lista">
        <h2 id="st-d-lista" className="st-h2 p-n">
          Wszystkie typy
        </h2>
        <Lista dane={dane} telefon={telefon} grupy ile={12} rodzaj="druzyny" zDniami />
      </section>
    </main>
  );
}

/* B · mecz jako pojedynek – nad typami średnie obu drużyn */
function DruzynyB({ dane, telefon }: Uklad) {
  const grupy = useMemo<Grupy>(
    () => ({
      klucz: (t, k) => String(k?.meczId ?? t.mecz),
      naglowek: (t, k, ile) =>
        k ? <Pojedynek k={k} rynki={dane.pojedynki[k.meczId] ?? []} ile={ile} /> : <div className="st-grupa">{t.mecz}</div>,
    }),
    [dane],
  );
  return (
    <main className="st-strona st-c">
      <Naglowek rodzaj="druzyny" />
      <section aria-labelledby="st-d-lista-b">
        <h2 id="st-d-lista-b" className="st-h2 p-n">
          Mecze z typami
        </h2>
        <Lista dane={dane} telefon={telefon} ile={12} rodzaj="druzyny" wlasneGrupy={grupy} zDniami />
      </section>
    </main>
  );
}

/* C · po rynkach – dla gracza, który gra jeden rodzaj zakładu */
function DruzynyC({ dane, telefon }: Uklad) {
  const grupy = useMemo<Grupy>(
    () => ({
      klucz: (t) => rynekKrotko(t.rynek),
      naglowek: (t, _k, ile) => (
        <div className="st-grupa st-grupa-rynek">
          <IkonaRynku rynek={t.rynek} rozmiar={18} />
          <b>{rynekKrotko(t.rynek)}</b>
          <span className="st-grupa-meta">
            <span>
              {ile} {odm(ile)}
            </span>
          </span>
        </div>
      ),
    }),
    [],
  );
  return (
    <main className="st-strona st-c">
      <Naglowek rodzaj="druzyny" />
      <NajmocniejszeDruzyn dane={dane} />
      <section aria-labelledby="st-d-lista-c">
        <h2 id="st-d-lista-c" className="st-h2 p-n">
          Wszystkie typy według rynku
        </h2>
        <Lista dane={dane} telefon={telefon} ile={12} rodzaj="druzyny" wlasneGrupy={grupy} bezMeczu={false} zDniami />
      </section>
    </main>
  );
}

/* A+B (wybór 01.10) · szkielet jak Zawodnicy, mecz jako pojedynek.
   Objaśnienie pasków raz nad listą, nie w każdej karcie. */
function DruzynyAB({ dane, telefon }: Uklad) {
  const grupy = useMemo<Grupy>(
    () => ({
      klucz: (t, k) => String(k?.meczId ?? t.mecz),
      naglowek: (t, k, ile) =>
        k ? (
          <Pojedynek k={k} rynki={dane.pojedynki[k.meczId] ?? []} ile={ile} podpis={false} strony={stronyTypow(dane.kartyStrony, k.meczId, t.polka)} />
        ) : (
          <div className="st-grupa">{t.mecz}</div>
        ),
    }),
    [dane],
  );
  return (
    <main className="st-strona st-c">
      <Naglowek rodzaj="druzyny" />
      <NajmocniejszeDruzyn dane={dane} />
      <div className="st-c-skrot">
        <KuponDniaMini k={dane.kuponDnia} pasek />
        <WynikiMini wyniki={dane.wyniki} suma={dane.sumaWynikow} pasek />
      </div>
      <section aria-labelledby="st-d-lista-ab">
        <div className="st-h2-z-opisem">
          <h2 id="st-d-lista-ab" className="st-h2 p-n">
            Wszystkie typy
          </h2>
          <p>Przy każdym meczu widzisz, ile średnio mają obie drużyny w 10 ostatnich meczach. Jaśniejszy pasek to drużyna z naszym typem.</p>
        </div>
        <Lista dane={dane} telefon={telefon} ile={12} rodzaj="druzyny" wlasneGrupy={grupy} zDniami />
      </section>
    </main>
  );
}

export function StronaDruzyny({ wariant, dane, telefon }: { wariant: string } & Uklad) {
  if (wariant === "ab") return <DruzynyAB dane={dane} telefon={telefon} />;
  if (wariant === "b") return <DruzynyB dane={dane} telefon={telefon} />;
  if (wariant === "c") return <DruzynyC dane={dane} telefon={telefon} />;
  return <DruzynyA dane={dane} telefon={telefon} />;
}

export function StronaGlowna({ wariant, dane, telefon }: { wariant: string } & Uklad) {
  if (wariant === "b") return <UkladB dane={dane} telefon={telefon} />;
  if (wariant === "c") return <UkladC dane={dane} telefon={telefon} />;
  return <UkladA dane={dane} telefon={telefon} />;
}
