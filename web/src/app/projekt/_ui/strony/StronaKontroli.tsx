"use client";

import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useEffect, useId, useRef, useState } from "react";

import type { DaneKontroli, Status } from "../../_dane/kontrola";
import type { DaneSkutecznosci } from "../../_dane/skutecznosc";
import { StronaSkutecznosci } from "./StronaSkutecznosci";

/*
 * Etap 5.6 – Wyniki dla admina: przełącznik Wyniki | Kontrola zamiast
 * dawnego „pokaż jak widzi klient” (Wyniki = dokładnie widok klienta).
 * Kontrola = dziewięć pytań właściciela, każde z werdyktem policzonym
 * z liczb. Wspólny obraz: POPRZECZKA – pasek to, ile weszło, pionowa kreska
 * to, ile obiecywał model albo ile zakładał kurs.
 */

type Pytanie = DaneKontroli["pytania"][number];
const SLOWO: Record<Status, string> = { ok: "w porządku", uwaga: "do obserwacji", zle: "do naprawy" };

/* ---- atomy ---------------------------------------------------------------- */

function Kropka({ s }: { s: Status }) {
  return <i className="kt-kropka" data-s={s} aria-label={SLOWO[s]} />;
}

/** pasek „weszło” z kreską „obiecywał / kurs zakładał”; kolor = jak daleko od obietnicy */
function Poprzeczka({ weszlo, cel, celPodpis, wyszarz = false, wymusTon }: { weszlo: number; cel?: number | null; celPodpis?: string; wyszarz?: boolean; wymusTon?: string }) {
  const roznica = cel == null ? 0 : weszlo - cel;
  const ton = wymusTon ?? (wyszarz ? "szary" : cel == null ? "neutralny" : roznica >= -3 ? "ok" : roznica > -10 ? "uwaga" : "zle");
  return (
    <span className="kt-poprzeczka" data-ton={ton} title={cel == null ? `weszło ${weszlo}%` : `weszło ${weszlo}%, ${celPodpis ?? "obiecywał"} ${cel}%`}>
      <motion.i className="kt-pop-pasek" initial={{ width: 0 }} whileInView={{ width: `${weszlo}%` }} viewport={{ once: true }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }} />
      {cel != null && <i className="kt-pop-cel" style={{ left: `${cel}%` }} />}
    </span>
  );
}

function Roznica({ pp, wyszarz = false }: { pp: number; wyszarz?: boolean }) {
  const ton = wyszarz ? "szary" : pp >= -3 ? "ok" : pp > -10 ? "uwaga" : "zle";
  return (
    <b className="kt-roznica" data-ton={ton}>
      {pp > 0 ? "+" : pp < 0 ? "−" : "±"}
      {Math.abs(pp)} pp
    </b>
  );
}

function Rozwin({ ile, co, children }: { ile: number; co: string; children: React.ReactNode }) {
  const [otwarte, setOtwarte] = useState(false);
  return (
    <>
      <AnimatePresence initial={false}>
        {otwarte && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} style={{ overflow: "hidden" }}>
            {children}
          </motion.div>
        )}
      </AnimatePresence>
      <button type="button" className="kt-rozwin" aria-expanded={otwarte} onClick={() => setOtwarte((o) => !o)}>
        {otwarte ? "Zwiń" : `Pokaż ${ile} ${co}`}
      </button>
    </>
  );
}

/* ---- szczegóły pytań ------------------------------------------------------- */

function Dziala({ k }: { k: DaneKontroli }) {
  const d = k.dzialanie;
  const lista = (rzeczy: { nazwa: string; ok: boolean; opis: string; krytyczna?: boolean }[]) => (
    <ul className="kt-lista">
      {rzeczy.map((r) => (
        <li key={r.nazwa} data-zle={!r.ok || undefined}>
          <Kropka s={r.ok ? "ok" : "zle"} />
          <span>
            <b>{r.nazwa}</b>
            {r.krytyczna && <em>bez niej nie publikujemy</em>}
            <small>{r.opis}</small>
          </span>
        </li>
      ))}
    </ul>
  );
  return (
    <div className="kt-dwie">
      <div>
        <h4 className="kt-h4">Sprawdzenia po każdym rozliczeniu</h4>
        {lista(d.sprawdzenia)}
      </div>
      <div>
        <h4 className="kt-h4">Warstwy uczenia w ostatnim cyklu</h4>
        {lista(d.warstwy.map((w) => ({ ...w, opis: w.opis.length > 90 ? `${w.opis.slice(0, 88)}…` : w.opis })))}
      </div>
    </div>
  );
}

function Pusto({ children }: { children: React.ReactNode }) {
  return <p className="kt-pusto">{children}</p>;
}

function Uczenie({ k }: { k: DaneKontroli }) {
  if (k.uczenie.length === 0) return <Pusto>Za mało rozliczeń, żeby policzyć choć jedną paczkę 40 typów. Pierwsza pojawi się sama.</Pusto>;
  return (
    <div className="kt-uczenie">
      {k.uczenie.map((u) => {
        const max = Math.max(20, ...u.paczki.map((p) => Math.abs(p.luka)));
        const H = 46;
        return (
          <div key={u.klucz} className="kt-ucz">
            <div className="kt-ucz-glowa">
              <b>{u.nazwa}</b>
              <em data-k={u.kierunek}>{u.kierunek === "lepiej" ? "poprawia się" : u.kierunek === "gorzej" ? "pogarsza się" : "stoi w miejscu"}</em>
              {u.start !== null && u.teraz !== null && (
                <span>
                  brakowało <b>{Math.abs(u.start)} pp</b> → {u.teraz < 0 ? <>brakuje <b>{Math.abs(u.teraz)} pp</b></> : <>nadwyżka <b>{u.teraz} pp</b></>}
                </span>
              )}
            </div>
            <div className="kt-ucz-wykres" role="img" aria-label={`${u.nazwa}: różnica między obietnicą a wynikiem w kolejnych paczkach po 40 typów`}>
              {u.paczki.map((p, i) => (
                <span key={i} className="kt-ucz-kol" title={`${p.od} – ${p.do}: weszło ${p.trafione} z ${p.n} (${p.hit}%), obiecywał ${p.obiecywal}%`}>
                  <motion.i
                    data-ton={p.luka >= -3 ? "ok" : p.luka > -10 ? "uwaga" : "zle"}
                    data-trwa={!p.pelna || undefined}
                    data-gora={p.luka > 0 || undefined}
                    initial={{ scaleY: 0 }}
                    whileInView={{ scaleY: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.4, delay: i * 0.04, ease: [0.22, 1, 0.36, 1] }}
                    style={{ height: `${(Math.abs(p.luka) / max) * H}px` }}
                  />
                </span>
              ))}
            </div>
            <div className="kt-ucz-os">
              <span>{u.paczki[0]?.od.slice(8)}.{u.paczki[0]?.od.slice(5, 7)}</span>
              <span>linia = obietnica · po 40 typów</span>
              <span>dziś</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function WierszPoprzeczki({ nazwa, dopisek, n, trafione, weszlo, cel, celPodpis, wyszarz }: { nazwa: string; dopisek?: string; n: number; trafione: number; weszlo: number; cel: number; celPodpis: string; wyszarz?: boolean }) {
  return (
    <div className="kt-wiersz" data-wyszarz={wyszarz || undefined}>
      <span className="kt-w-nazwa">
        <b>{nazwa}</b>
        <small>
          {trafione} z {n}
          {dopisek && ` · ${dopisek}`}
        </small>
      </span>
      <Poprzeczka weszlo={weszlo} cel={cel} celPodpis={celPodpis} wyszarz={wyszarz} />
      <span className="kt-w-liczby">
        <b>{weszlo}%</b>
        <small>
          {celPodpis} {cel}%
        </small>
      </span>
      <Roznica pp={weszlo - cel} wyszarz={wyszarz} />
    </div>
  );
}

function Legenda({ cel }: { cel: string }) {
  return (
    <p className="kt-legenda">
      <span>
        <i className="kt-leg-pasek" /> weszło
      </span>
      <span>
        <i className="kt-leg-cel" /> {cel}
      </span>
      <span>szare – mniej niż 10 rozliczeń, jeszcze nic nie znaczy</span>
    </p>
  );
}

function Rynki({ k }: { k: DaneKontroli }) {
  if (k.rynki.length === 0) return <Pusto>Żaden rynek nie ma jeszcze rozliczonych typów.</Pusto>;
  const istotne = k.rynki.filter((r) => !r.mala);
  const male = k.rynki.filter((r) => r.mala);
  const wiersz = (r: (typeof k.rynki)[number]) => <WierszPoprzeczki key={r.kod} nazwa={r.nazwa} n={r.n} trafione={r.trafione} weszlo={r.weszlo} cel={r.obiecywal} celPodpis="obiecywał" wyszarz={r.mala} />;
  return (
    <>
      <Legenda cel="obiecywał model" />
      {istotne.length ? <div className="kt-tabela">{istotne.map(wiersz)}</div> : <Pusto>Żaden rynek nie ma jeszcze 10 rozliczeń – poniżej wszystkie z małą próbą.</Pusto>}
      {male.length > 0 && (
        <Rozwin ile={male.length} co="rynków z małą próbą">
          <div className="kt-tabela kt-tabela-dalej">{male.map(wiersz)}</div>
        </Rozwin>
      )}
      <p className="kt-przypis">
        Test w tle (drużynowe „poniżej”, poza stroną): weszło {k.test.trafione} z {k.test.n} ({k.test.weszlo}%), model obiecywał {k.test.obiecywal}%{k.test.gotowy ? " – test zakończony" : ""}.
      </p>
    </>
  );
}

function Polki({ k }: { k: DaneKontroli }) {
  const produkty = [...new Set(k.polki.map((p) => p.produkt))];
  return (
    <>
      <Legenda cel="zakładał kurs" />
      {produkty.map((pr) => (
        <div key={pr} className="kt-grupa">
          <h4 className="kt-h4">{pr}</h4>
          <div className="kt-tabela">
            {k.polki
              .filter((p) => p.produkt === pr)
              .map((p) => (
                <WierszPoprzeczki
                  key={p.polka}
                  nazwa={p.polka}
                  dopisek={p.historyczna ? "do 21.09" : p.limit ? `limit ${p.limit} dziennie` : undefined}
                  n={p.n}
                  trafione={p.trafione}
                  weszlo={p.weszlo}
                  cel={p.cena}
                  celPodpis="kurs"
                  wyszarz={p.mala || p.historyczna}
                />
              ))}
          </div>
        </div>
      ))}
    </>
  );
}

function Drabinki({ k }: { k: DaneKontroli }) {
  const d = k.drabinki;
  const proc = (t: number, n: number) => (n ? Math.round((t / n) * 100) : 0);
  return (
    <>
      <div className="kt-sito">
        <div className="kt-sito-strona" data-ton="ok">
          <small>przeszły sito</small>
          <b className="p-n">{d.opublikowane.weszlo}%</b>
          <span>
            weszło {d.opublikowane.trafione} z {d.opublikowane.n} kart
          </span>
          <Poprzeczka weszlo={d.opublikowane.weszlo} wymusTon="ok" />
        </div>
        <div className="kt-sito-strona">
          <small>odrzucone przez sito</small>
          <b className="p-n">{d.odrzucone.weszlo}%</b>
          <span>
            weszłoby {d.odrzucone.trafione} z {d.odrzucone.n}
          </span>
          <Poprzeczka weszlo={d.odrzucone.weszlo} wyszarz />
        </div>
      </div>
      <p className="kt-przypis">Sito mierzymy na wszystkich kartach radaru, także niepokazanych – dlatego liczby są większe niż w Wynikach.</p>
      <div className="kt-dwie">
        <div>
          <h4 className="kt-h4">Klasy kart na stronie (1. szczebel)</h4>
          <div className="kt-tabela">
            {d.klasy.map((x) => (
              <div key={x.klasa} className="kt-wiersz kt-wiersz-prosty" data-wyszarz={x.n < 10 || undefined}>
                <span className="kt-w-nazwa">
                  <b>{x.klasa === "top" ? "TOP" : x.klasa === "mocny" ? "Mocna" : "Solidna"}</b>
                  <small>
                    {x.trafione} z {x.n}
                  </small>
                </span>
                <Poprzeczka weszlo={proc(x.trafione, x.n)} wyszarz={x.n < 10} />
                <span className="kt-w-liczby">
                  <b>{proc(x.trafione, x.n)}%</b>
                </span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <h4 className="kt-h4">Szczeble drabinki</h4>
          <div className="kt-tabela">
            {d.szczeble.map((x) => (
              <div key={x.nr} className="kt-wiersz kt-wiersz-prosty">
                <span className="kt-w-nazwa">
                  <b>{x.nr}. szczebel</b>
                  <small>
                    {x.trafione} z {x.n}
                  </small>
                </span>
                <Poprzeczka weszlo={proc(x.trafione, x.n)} />
                <span className="kt-w-liczby">
                  <b>{proc(x.trafione, x.n)}%</b>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

function Kurs({ k }: { k: DaneKontroli }) {
  if (k.kurs.segmenty.length === 0 && k.kurs.pasma.length === 0) return <Pusto>Cykl nie policzył porównania modelu z kursem. Wróci samo przy następnym przeliczeniu.</Pusto>;
  const najlepsze = k.kurs.segmenty.slice(0, 5);
  const najgorsze = k.kurs.segmenty.slice(-5).reverse();
  const max = Math.max(...k.kurs.segmenty.map((s) => Math.abs(s.przewaga)), ...k.kurs.pasma.map((p) => Math.abs(p.przewaga)));
  const wiersz = (nazwa: string, n: number, przewaga: number, pewne = true) => (
    <div key={nazwa} className="kt-wiersz kt-wiersz-kurs" data-wyszarz={!pewne || undefined}>
      <span className="kt-w-nazwa">
        <b>{nazwa}</b>
        <small>{n} prognoz</small>
      </span>
      <span className="kt-os" aria-hidden>
        <i className="kt-os-zero" />
        <motion.i
          className="kt-os-pasek"
          data-ton={przewaga >= 0 ? "ok" : "zle"}
          style={{ [przewaga >= 0 ? "left" : "right"]: "50%" } as React.CSSProperties}
          initial={{ width: 0 }}
          whileInView={{ width: `${(Math.abs(przewaga) / max) * 50}%` }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
        />
      </span>
      <b className="kt-roznica" data-ton={!pewne ? "szary" : przewaga >= 0 ? "ok" : "zle"}>
        {przewaga > 0 ? "+" : przewaga < 0 ? "−" : "±"}
        {Math.abs(przewaga).toFixed(1).replace(".", ",")}
      </b>
    </div>
  );
  return (
    <>
      <p className="kt-legenda">
        <span>na prawo – model celniejszy od kursu, na lewo – kurs wie więcej (różnica celności w punktach na 100 prognoz)</span>
      </p>
      <h4 className="kt-h4">Pasma kursów</h4>
      <div className="kt-tabela">{k.kurs.pasma.map((p) => wiersz(`kurs ${p.zakres}`, p.n, p.przewaga))}</div>
      <div className="kt-dwie">
        <div>
          <h4 className="kt-h4">Gdzie model bije kurs</h4>
          <div className="kt-tabela">{najlepsze.map((s) => wiersz(s.nazwa, s.n, s.przewaga, s.pewne))}</div>
        </div>
        <div>
          <h4 className="kt-h4">Gdzie kurs wie najwięcej</h4>
          <div className="kt-tabela">{najgorsze.map((s) => wiersz(s.nazwa, s.n, s.przewaga, s.pewne))}</div>
        </div>
      </div>
    </>
  );
}

function Kupony({ k }: { k: DaneKontroli }) {
  return (
    <>
      <Legenda cel="obiecywał budowniczy" />
      <div className="kt-tabela">
        {k.kupony.podsumowanie.map((x) => (
          <WierszPoprzeczki
            key={x.nazwa}
            nazwa={x.nazwa}
            dopisek={`bilans ${x.bilans >= 0 ? "+" : "−"}${Math.abs(x.bilans).toFixed(2).replace(".", ",")} j.`}
            n={x.n}
            trafione={x.wygrane}
            weszlo={x.weszlo ?? 0}
            cel={x.obiecywal ?? 0}
            celPodpis="obiecywał"
          />
        ))}
      </div>
      <h4 className="kt-h4">Ostatnie rozliczone</h4>
      <div className="kt-kupony">
        {k.kupony.ostatnie.map((x, i) => (
          <div key={i} className="kt-kupon" data-wynik={x.wynik}>
            <span className="kt-kupon-znak">{x.wynik === "wygrany" ? "✓" : "✕"}</span>
            <span>
              <b>{x.dzien.slice(8)}.{x.dzien.slice(5, 7)}</b> {x.horyzont}
            </span>
            <span className="kt-kupon-nogi" aria-label={`${x.trafione} z ${x.nogi} typów weszło`}>
              {Array.from({ length: x.nogi }, (_, j) => (
                <i key={j} data-ok={j < x.trafione || undefined} />
              ))}
            </span>
            {x.kurs && <b className="kt-kupon-kurs">×{x.kurs.toFixed(2).replace(".", ",")}</b>}
          </div>
        ))}
      </div>
      <p className="kt-przypis">Kronika trafień: {k.kupony.kronika} kuponów, które weszły, zostaje na stałe.</p>
    </>
  );
}

function Egzamin({ k }: { k: DaneKontroli }) {
  const S = 132;
  if (k.egzamin.rynki.length === 0) return <Pusto>Za mało rozegranych meczów spoza nauki, żeby zrobić egzamin.</Pusto>;
  return (
    <>
      <p className="kt-legenda">
        <span>kropka = grupa prognoz: na prawo – ile obiecywał, w górę – ile weszło; uczciwy model leży na przekątnej</span>
      </p>
      <div className="kt-egzamin">
        {k.egzamin.rynki.map((r) => (
          <figure key={r.nazwa} className="kt-egz">
            <svg viewBox={`0 0 ${S} ${S}`} role="img" aria-label={`${r.nazwa}: kalibracja`}>
              <rect x="0.5" y="0.5" width={S - 1} height={S - 1} rx="6" className="kt-egz-tlo" />
              <line x1="8" y1={S - 8} x2={S - 8} y2="8" className="kt-egz-przekatna" />
              {r.kubelki.map((b, i) => (
                <motion.circle
                  key={i}
                  cx={8 + (b.x / 100) * (S - 16)}
                  cy={S - 8 - (b.y / 100) * (S - 16)}
                  r={Math.max(2.5, Math.min(8, Math.sqrt(b.n) * 0.7))}
                  className="kt-egz-kropka"
                  initial={{ scale: 0 }}
                  whileInView={{ scale: 1 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.05, type: "spring", stiffness: 500, damping: 22 }}
                  style={{ transformBox: "fill-box", transformOrigin: "center" }}
                >
                  <title>{`obiecywał ${b.x}%, weszło ${b.y}% (${b.n} prognoz)`}</title>
                </motion.circle>
              ))}
            </svg>
            <figcaption>
              <b>{r.nazwa}</b>
              <small>Brier {r.brier.toFixed(3).replace(".", ",")}</small>
            </figcaption>
          </figure>
        ))}
      </div>
    </>
  );
}

function Sklady({ k }: { k: DaneKontroli }) {
  return (
    <div className="kt-tabela">
      {k.sklady.map((s) => (
        <div key={s.nazwa} className="kt-wiersz kt-wiersz-prosty">
          <span className="kt-w-nazwa">
            <b>{s.nazwa}</b>
            <small>{String(s.n).replace(/\B(?=(\d{3})+(?!\d))/g, " ")} prognoz</small>
          </span>
          <Poprzeczka weszlo={s.zagral} />
          <span className="kt-w-liczby">
            <b>{s.zagral}%</b>
            <small>zagrało</small>
          </span>
        </div>
      ))}
    </div>
  );
}

const SZCZEGOLY: Record<string, (p: { k: DaneKontroli }) => React.ReactNode> = {
  dziala: Dziala,
  uczenie: Uczenie,
  rynki: Rynki,
  polki: Polki,
  drabinki: Drabinki,
  kurs: Kurs,
  kupony: Kupony,
  egzamin: Egzamin,
  sklady: Sklady,
};

function Werdykt({ p }: { p: Pytanie }) {
  return (
    <p className="kt-werdykt" data-s={p.status}>
      <Kropka s={p.status} />
      <span>{p.werdykt}</span>
    </p>
  );
}

/* ---- A · raport: spis z boku, pytania jedno pod drugim -------------------- */

function Raport({ k, telefon }: { k: DaneKontroli; telefon: boolean }) {
  const [aktywne, setAktywne] = useState(k.pytania[0].id);
  const rama = useRef<HTMLDivElement>(null);
  const sekcja = (id: string) => rama.current?.querySelector<HTMLElement>(`[data-pytanie="${id}"]`);
  // spis podąża za czytaniem: aktywne jest pytanie przy górnej krawędzi
  // (szukamy w swoim kontenerze – w warsztacie strona jest dwa razy: komputer i telefon)
  useEffect(() => {
    const sekcje = [...(rama.current?.querySelectorAll<HTMLElement>("[data-pytanie]") ?? [])];
    // korzeń = najbliższy przewijany kontener (w warsztacie ramka podglądu; na stronie – okno)
    const root = sekcje[0]?.closest<HTMLElement>(".s-telefon, .s-okno") ?? null;
    const obs = new IntersectionObserver(
      (wpisy) => {
        const widoczne = wpisy.filter((w) => w.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (widoczne) setAktywne((widoczne.target as HTMLElement).dataset.pytanie!);
      },
      { root, rootMargin: "-15% 0px -70% 0px" },
    );
    sekcje.forEach((e) => obs.observe(e));
    return () => obs.disconnect();
  }, [k.pytania]);
  const idz = (id: string) => {
    setAktywne(id);
    sekcja(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  // pasek na telefonie przewija się sam do aktywnego pytania
  useEffect(() => {
    if (!telefon) return;
    const pas = rama.current?.querySelector<HTMLElement>(".kt-pas");
    const b = pas?.querySelector<HTMLElement>(`[data-cel="${aktywne}"]`);
    if (pas && b) pas.scrollTo({ left: b.offsetLeft - pas.clientWidth / 2 + b.clientWidth / 2, behavior: "smooth" });
  }, [aktywne, telefon]);
  return (
    <div className="kt-raport" ref={rama} data-telefon={telefon || undefined}>
      {telefon && (
        <nav className="kt-pas" aria-label="Pytania">
          {k.pytania.map((p) => (
            <button key={p.id} data-cel={p.id} type="button" aria-current={aktywne === p.id || undefined} onClick={() => idz(p.id)}>
              <Kropka s={p.status} />
              {p.krotko}
            </button>
          ))}
        </nav>
      )}
      {!telefon && (
        <nav className="kt-spis" aria-label="Pytania">
          {k.pytania.map((p) => (
            <a
              key={p.id}
              href={`#kt-${p.id}`}
              aria-current={aktywne === p.id || undefined}
              onClick={(e) => {
                e.preventDefault();
                idz(p.id);
              }}
            >
              <Kropka s={p.status} />
              <span>{p.krotko}</span>
              <b>{p.liczba}</b>
            </a>
          ))}
        </nav>
      )}
      <div className="kt-sekcje">
        {k.pytania.map((p) => {
          const Szczegol = SZCZEGOLY[p.id];
          return (
            <section key={p.id} data-pytanie={p.id} className="kt-sekcja">
              <h2 className="p-n">{p.pytanie}</h2>
              <Werdykt p={p} />
              <div className="kt-szczegol">
                {p.id === "dziala" && p.status === "ok" ? (
                  <Rozwin ile={k.dzialanie.sprawdzenia.length + k.dzialanie.warstwy.length} co="sprawdzeń i warstw">
                    <Szczegol k={k} />
                  </Rozwin>
                ) : (
                  <Szczegol k={k} />
                )}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

/* ---- strona ---------------------------------------------------------------- */

export function StronaWynikowAdmin({
  kontrola,
  skutecznosc,
  telefon,
  start = {},
}: {
  kontrola: DaneKontroli;
  skutecznosc: DaneSkutecznosci;
  telefon: boolean;
  /** z adresu: `?widok=wyniki|kontrola`, `?dzien=` (dzień w Wynikach) */
  start?: { widok?: string; dzien?: string };
}) {
  const [widok, setWidokStan] = useState<"wyniki" | "kontrola">(start.widok === "wyniki" || (start.dzien && start.widok !== "kontrola") ? "wyniki" : "kontrola");
  // na produkcji: ?widok=kontrola w adresie, żeby dało się wysłać link wprost do Kontroli
  const setWidok = (w: "wyniki" | "kontrola") => {
    setWidokStan(w);
    const u = new URL(window.location.href);
    u.searchParams.set("widok", w);
    window.history.replaceState(null, "", u);
  };
  const id = useId();
  const naglowek = (
    <div className="kt-naglowek">
      <div className="st-naglowek">
        <h1 className="p-n">Wyniki</h1>
        <p>
          {widok === "kontrola" ? (
            <>
              <span>Dziewięć pytań o to, czy produkt działa i czy się uczy.</span> <span>Stan na {kontrola.stan}, liczone tylko z rozliczeń.</span>
            </>
          ) : (
            <>
              <span>Każdy typ zostaje w historii – także te, które nie weszły.</span> <span>Tak samo widzi to klient.</span>
            </>
          )}
        </p>
      </div>
      <LayoutGroup id={id}>
        <div className="mz-seg kt-widok" role="radiogroup" aria-label="Widok">
          {(
            [
              ["wyniki", "Wyniki"],
              ["kontrola", "Kontrola"],
            ] as const
          ).map(([kl, nazwa]) => (
            <button key={kl} type="button" role="radio" aria-checked={widok === kl} onClick={() => setWidok(kl)}>
              {widok === kl && <motion.span layoutId="kt-widok-tlo" className="mz-seg-tlo" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
              <span className="mz-seg-tresc">
                {kl === "kontrola" && <i className="kt-kropka" data-s={kontrola.pytania.some((x) => x.status === "zle") ? "zle" : "ok"} aria-hidden />}
                {nazwa}
              </span>
            </button>
          ))}
        </div>
      </LayoutGroup>
    </div>
  );
  if (widok === "wyniki") return <StronaSkutecznosci wariant="a" dane={skutecznosc} telefon={telefon} naglowek={naglowek} dzienStart={start.dzien} />;
  return (
    <main className="st-strona kt">
      {naglowek}
      <Raport k={kontrola} telefon={telefon} />
    </main>
  );
}
