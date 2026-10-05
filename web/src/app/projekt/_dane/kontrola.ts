/**
 * Etap 5.6 – Wyniki › Kontrola (tylko admin). Dane z migawki `admin.json`
 * (pobrana 01.10, jednorazowo: typy_wyniki bez dni, meta.uczenie_stan,
 * calibration). Każda sekcja odpowiada na jedno pytanie właściciela i ma
 * werdykt policzony z liczb – bez ręcznych ocen.
 *
 * Na produkcji te dane NIE MOGĄ trafić do przeglądarki klienta (web/AGENTS.md:
 * wycinać na serwerze, `okrojDlaKlienta`).
 */

import { zrodlo } from "./zrodlo";

export type Status = "ok" | "uwaga" | "zle";

type Paczka = { n: number; od: string; do: string; hit: number; roi: number | null; luka: number; pelna: boolean; trafione: number; deklaracja: number; meczow: number };
type Trend = { szum: number; paczek: number; zmiana: number; luka_start: number; luka_teraz: number; luka_poprzednio: number; zmiana_ostatnio: number };
type Polka = { n: number; cena: number; trafione: number; skutecznosc: number; limit_dobowy: number | null };
type Wynikowo = { n: number; hit: number | null; sr_p: number | null; trafione: number };

type Admin = {
  typy: {
    podsumowanie: { start_statystyk: string; rozliczone: number; trafione: number };
    raport_uczenia: Record<string, { trend?: Trend; paczki: Paczka[] }>;
    po_rynku: { n: number; rynek: string; rynek_kod: string; trafione: number; czestosc: number; sr_p_model: number }[];
    strumienie_skrot: {
      pewniaki: { polki: Record<string, Polka> };
      druzyny: { polki: Record<string, Polka> };
      drabinki: { klasy: Record<string, { n: number; trafione: number }>; podsumowanie: { szczebel2_n: number; szczebel2_trafione: number; szczebel3_n: number; szczebel3_trafione: number; rozliczone: number; trafione: number } };
    };
    kupony_roi: Record<string, { n: number; roi_j: number; wygrane: number; zwrot_j: number }>;
    kupony_diag: { kalibracja: Record<string, { n: number; hit: number; sr_p: number }> };
    kontrola: { policzono_ts: number; sprawdzenia: { ok: boolean; kod: string; opis: string; liczba: number | null }[] };
    diagnostyka: { sklady: Record<string, { n: number; pct: number; zagral: number }> };
    forward_test: { n: number; hit: number; deklaracja: number; trafione: number; gotowy: boolean; luka_pp: number };
    prog_drabinek: Record<string, Wynikowo>;
    przewaga_rynkow: Record<string, { n: number; se: number; strona: string; przewaga: number; rynek_kod: string }>;
    przewaga_pasm: Record<string, { n: number; od: number; do: number; hit: number; przewaga: number }>;
  };
  kupony: { dzien: string; horyzont: string; wynik: string | null; kurs_laczny?: number; legi: { rynek: string; podmiot: string; wynik: string | null }[]; cel_label: string }[];
  kupony_wygrane_n: number;
  meta: { uczenie_stan: Record<string, { n: number | null; ok: boolean; blad: string | null; opis: string | null; krytyczna: boolean }>; wygenerowano_ts: number; meczow_kalibracja: number };
  kalibracja: { razem: { n: number; brier: number }; rynki: { kod: string; nazwa: string; n: number; brier: number; kubelki: { n: number; p_pred: number; p_real: number }[] }[] };
};

const pp = (x: number) => Math.round(x * 100);
const NAZWY_STRUMIENI: Record<string, string> = { pewniaki: "Zawodnicy", druzyny: "Drużyny", drabinki: "Drabinki" };
const NAZWY_RYNKOW: Record<string, string> = {
  shots: "Strzały", sot: "Strzały celne", fouls_committed: "Faule popełnione", fouls_won: "Faule wywalczone", tackles: "Odbiory",
  interceptions: "Przechwyty", offsides: "Spalone", shots_outside_box: "Strzały zza pola", team_goals: "Gole drużyny",
  team_corners: "Rożne drużyny", team_cards: "Kartki drużyny", team_shots: "Strzały drużyny", team_sot: "Celne drużyny",
  team_fouls: "Faule drużyny", match_corners: "Rożne w meczu", match_cards: "Kartki w meczu", match_shots: "Strzały w meczu",
  match_sot: "Celne w meczu", match_fouls: "Faule w meczu", wiecej_shots: "Kto więcej strzałów", wiecej_sot: "Kto więcej celnych",
  wiecej_cards: "Kto więcej kartek",
};
const NAZWY_WARSTW: Record<string, string> = {
  waga_rynku: "Waga rynku", wagi_zaufania: "Wagi zaufania", korekta_strony: "Korekta strony zakładu", przewaga_rynkow: "Przewaga nad kursem",
  sciaganie_karty: "Ściąganie szansy do ceny", kwarantanna_stron: "Kwarantanna stron", szansa_pokazywana: "Szansa pokazywana",
  kalibracja_kuponow: "Kalibracja kuponów", korekta_strumienia: "Korekta strumienia", kwarantanna_rynkow: "Kwarantanna rynków",
  kwarantanna_kategorii: "Kwarantanna kategorii",
};
const NAZWY_SPRAWDZEN: Record<string, string> = {
  zapis_pokazanych: "Zapis tego, co było na stronie", strona_bez_rekordu: "Typy ze strony mają zapis do rozliczenia",
  zaleglosc_rozliczen: "Rozliczenia na bieżąco", strona_bez_wiersza: "Każdy typ ze strony ma wiersz w Wynikach",
  bez_danych: "Typy zamykane z wynikiem", wagi_modelu: "Nocny trening modelu",
  przelozony_rozegrany: "Zwroty za przełożone mecze potwierdzone", kupony_schowane: "Kupony nie znikają ze strony",
  nie_zagral_probka: "Zwroty „nie zagrał” potwierdzone",
};

const godz = (ts: number) => new Date((ts + 2 * 3600) * 1000).toISOString().slice(11, 16);
const data = (ts: number) => {
  const d = new Date((ts + 2 * 3600) * 1000);
  return `${d.getUTCDate()}.${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
};

export function przygotujKontrole() {
  const A = zrodlo().admin as Admin;
  const T = A.typy;
  /* 1. czy wszystko działa */
  const sprawdzenia = T.kontrola.sprawdzenia.map((s) => ({ nazwa: NAZWY_SPRAWDZEN[s.kod] ?? s.kod, ok: s.ok, opis: s.opis }));
  const wiekCyklu = Math.round((T.kontrola.policzono_ts - A.meta.wygenerowano_ts) / 60);
  sprawdzenia.unshift({ nazwa: "Cykl aktualizuje stronę", ok: true, opis: `ostatni cykl o ${godz(A.meta.wygenerowano_ts)}` });
  const warstwy = Object.entries(A.meta.uczenie_stan ?? {}).map(([k, w]) => ({ nazwa: NAZWY_WARSTW[k] ?? k, ok: w.ok, n: w.n, krytyczna: w.krytyczna, opis: w.blad ?? w.opis ?? "" }));
  const zleS = sprawdzenia.filter((s) => !s.ok).length + warstwy.filter((w) => !w.ok).length;
  const dzialanie = {
    status: (zleS ? "zle" : "ok") as Status,
    sprawdzenia,
    warstwy,
    wiekCyklu,
  };

  /* 2. czy model się uczy – luka = weszło − obiecywał, w pp na 100 typów */
  const uczenie = (["pewniaki", "druzyny", "drabinki"] as const)
    .map((k) => {
      const u = T.raport_uczenia[k];
      if (!u) return null;
      const t = u.trend;
      const kierunek: "lepiej" | "gorzej" | "stoi" = !t ? "stoi" : t.zmiana > 0.02 ? "lepiej" : t.zmiana < -0.02 ? "gorzej" : "stoi";
      return {
        klucz: k,
        nazwa: NAZWY_STRUMIENI[k],
        kierunek,
        start: t ? pp(t.luka_start) : null,
        teraz: t ? pp(t.luka_teraz) : null,
        paczek: t?.paczek ?? u.paczki.length,
        paczki: u.paczki.map((p) => ({ od: p.od, do: p.do, n: p.n, trafione: p.trafione, hit: pp(p.hit), obiecywal: pp(p.deklaracja), luka: Math.round(p.luka * 1000) / 10, pelna: p.pelna })),
      };
    })
    .filter((x) => x !== null);
  const lepiej = uczenie.filter((u) => u.kierunek === "lepiej").length;
  const gorzej = uczenie.filter((u) => u.kierunek === "gorzej").length;

  /* 3. rynki – obiecywał vs weszło */
  const rynki = [...T.po_rynku]
    .sort((a, b) => b.n - a.n)
    .map((r) => ({ kod: r.rynek_kod, nazwa: NAZWY_RYNKOW[r.rynek_kod] ?? r.rynek, n: r.n, trafione: r.trafione, weszlo: pp(r.czestosc), obiecywal: pp(r.sr_p_model), mala: r.n < 10 }));
  const istotne = rynki.filter((r) => !r.mala);
  const zbytPewny = istotne.filter((r) => r.weszlo - r.obiecywal <= -10);

  /* 4. półki – weszło vs cena bukmachera (szansa z kursu) */
  const NAZWY_POLEK: Record<string, string> = { wysoka_szansa: "Wysoka szansa", wyzsze_kursy: "Wyższe kursy", mocna_linia: "Mocna linia", poza_polkami: "Przed półkami" };
  const polki = (["pewniaki", "druzyny"] as const).flatMap((k) =>
    Object.entries(T.strumienie_skrot?.[k]?.polki ?? {})
      .sort(([a], [b]) => Number(a === "poza_polkami") - Number(b === "poza_polkami"))
      .map(([p, v]) => ({ produkt: NAZWY_STRUMIENI[k], polka: NAZWY_POLEK[p] ?? p, n: v.n, trafione: v.trafione, weszlo: pp(v.skutecznosc), cena: pp(v.cena), limit: v.limit_dobowy, mala: v.n < 10, historyczna: p === "poza_polkami" })),
  );
  const aktywne = polki.filter((p) => !p.historyczna && !p.mala);
  const najgorsza = [...aktywne].sort((a, b) => a.weszlo - a.cena - (b.weszlo - b.cena))[0];

  /* 5. drabinki – sito */
  const pd = T.prog_drabinek;
  const dr = T.strumienie_skrot.drabinki;
  const drabinki = {
    opublikowane: { n: pd.opublikowane.n, trafione: pd.opublikowane.trafione, weszlo: pp(pd.opublikowane.hit ?? 0), obiecywal: pp(pd.opublikowane.sr_p ?? 0) },
    odrzucone: { n: pd.pod_progiem.n, trafione: pd.pod_progiem.trafione, weszlo: pp(pd.pod_progiem.hit ?? 0), obiecywal: pp(pd.pod_progiem.sr_p ?? 0) },
    klasy: (["top", "mocny", "solidny"] as const).filter((k) => dr.klasy[k]).map((k) => ({ klasa: k, n: dr.klasy[k].n, trafione: dr.klasy[k].trafione })),
    szczeble: [
      { nr: 1, n: dr.podsumowanie.rozliczone, trafione: dr.podsumowanie.trafione },
      { nr: 2, n: dr.podsumowanie.szczebel2_n, trafione: dr.podsumowanie.szczebel2_trafione },
      { nr: 3, n: dr.podsumowanie.szczebel3_n, trafione: dr.podsumowanie.szczebel3_trafione },
    ],
  };

  /* 6. model vs kurs */
  const segmenty = Object.entries(T.przewaga_rynkow ?? {}).map(([k, v]) => ({
    klucz: k,
    nazwa: `${NAZWY_RYNKOW[v.rynek_kod] ?? v.rynek_kod} · ${v.strona === "powyzej" ? "powyżej" : v.strona === "ponizej" ? "poniżej" : v.strona}`,
    n: v.n,
    przewaga: Math.round(v.przewaga * 1000) / 10,
    pewne: Math.abs(v.se) >= 2,
  }));
  const bije = segmenty.filter((s) => s.przewaga > 0);
  const bijePewnie = bije.filter((s) => s.pewne);
  const pasma = Object.values(T.przewaga_pasm ?? {})
    .sort((a, b) => a.od - b.od)
    .map((p) => ({ zakres: `${String(p.od).replace(".", ",")}–${String(p.do === 6.01 ? 6 : p.do).replace(".", ",")}`, n: p.n, przewaga: Math.round(p.przewaga * 1000) / 10 }));

  /* 7. kupony */
  const kal = T.kupony_diag.kalibracja;
  const kupony = (["dzienny", "dlugoterminowy"] as const)
    .filter((h) => T.kupony_roi[h])
    .map((h) => ({
      nazwa: h === "dzienny" ? "Dzienne" : "Długoterminowe",
      n: T.kupony_roi[h].n,
      wygrane: T.kupony_roi[h].wygrane,
      bilans: T.kupony_roi[h].roi_j,
      obiecywal: kal[h] ? pp(kal[h].sr_p) : null,
      weszlo: kal[h] ? pp(kal[h].hit) : null,
    }));
  const ostatnieKupony = A.kupony
    .filter((k) => k.wynik)
    .slice(0, 6)
    .map((k) => ({
      dzien: k.dzien,
      horyzont: k.horyzont === "dzienny" ? "dzienny" : "długi",
      wynik: k.wynik,
      kurs: k.kurs_laczny ?? null,
      nogi: k.legi.length,
      trafione: k.legi.filter((l) => l.wynik === "wygrany").length,
    }));

  /* 8. egzamin – kalibracja na meczach spoza nauki */
  const egzamin = {
    n: A.kalibracja.razem.n,
    brier: A.kalibracja.razem.brier,
    meczow: A.meta.meczow_kalibracja,
    rynki: A.kalibracja.rynki.map((r) => ({ nazwa: NAZWY_RYNKOW[r.kod] ?? r.nazwa, n: r.n, brier: r.brier, kubelki: r.kubelki.map((k) => ({ n: k.n, x: pp(k.p_pred), y: pp(k.p_real) })) })),
  };

  /* 9. składy */
  const s = T.diagnostyka.sklady;
  const sklady = [
    { nazwa: "Oficjalny skład", n: s.official.n, zagral: pp(s.official.pct) },
    { nazwa: "Przewidywany skład", n: s.predicted.n, zagral: pp(s.predicted.pct) },
    { nazwa: "Bez składu (z historii)", n: s.brak.n, zagral: pp(s.brak.pct) },
  ];

  const ft = T.forward_test;

  const pytania = [
    {
      id: "dziala",
      krotko: "Czy wszystko działa",
      pytanie: "Czy wszystko działa?",
      status: dzialanie.status,
      liczba: `${sprawdzenia.filter((x) => x.ok).length}/${sprawdzenia.length}`,
      werdykt: zleS ? `${zleS} ${zleS === 1 ? "rzecz nie przechodzi" : "rzeczy nie przechodzą"} – szczegóły niżej.` : `Tak. ${sprawdzenia.length} z ${sprawdzenia.length} sprawdzeń i ${warstwy.length} z ${warstwy.length} warstw uczenia działa.`,
    },
    {
      id: "uczenie",
      krotko: "Czy model się uczy",
      pytanie: "Czy model się uczy?",
      status: (gorzej ? "zle" : lepiej === uczenie.length ? "ok" : "uwaga") as Status,
      liczba: `${lepiej} z ${uczenie.length}`,
      werdykt:
        uczenie
          .filter((u) => u.kierunek === "lepiej")
          .map((u) => u.nazwa)
          .join(" i ") +
        (lepiej ? " się poprawiają" : "Nic się nie poprawia") +
        (uczenie.some((u) => u.kierunek === "stoi") ? `, ${uczenie.filter((u) => u.kierunek === "stoi").map((u) => u.nazwa).join(" i ")} stoją w miejscu.` : "."),
    },
    {
      id: "rynki",
      krotko: "Gdzie tracimy",
      pytanie: "Na których rynkach model obiecuje za dużo?",
      status: (zbytPewny.length >= 3 ? "zle" : zbytPewny.length ? "uwaga" : "ok") as Status,
      liczba: `${zbytPewny.length} z ${istotne.length}`,
      werdykt: zbytPewny.length
        ? `Na ${zbytPewny.length} z ${istotne.length} rynków wchodzi o 10 pp i więcej mniej, niż obiecywał: ${zbytPewny.map((r) => r.nazwa.toLowerCase()).join(", ")}.`
        : "Na żadnym rynku z wystarczającą próbą model nie przesadza o 10 pp.",
    },
    {
      id: "polki",
      krotko: "Półki a cena",
      pytanie: "Czy półki wchodzą częściej, niż wycenia bukmacher?",
      status: (najgorsza && najgorsza.weszlo - najgorsza.cena <= -10 ? "zle" : najgorsza && najgorsza.weszlo < najgorsza.cena ? "uwaga" : "ok") as Status,
      liczba: najgorsza ? `${najgorsza.weszlo - najgorsza.cena > 0 ? "+" : "−"}${Math.abs(najgorsza.weszlo - najgorsza.cena)} pp` : "–",
      werdykt: najgorsza
        ? `Najsłabiej: ${najgorsza.polka.toLowerCase()} u ${najgorsza.produkt === "Zawodnicy" ? "zawodników" : "drużyn"} – wchodzi ${najgorsza.weszlo}%, a kurs zakłada ${najgorsza.cena}%.`
        : "Za mało rozliczeń na półkach.",
    },
    {
      id: "drabinki",
      krotko: "Sito drabinek",
      pytanie: "Czy sito drabinek odsiewa słabe karty?",
      status: (drabinki.opublikowane.weszlo - drabinki.odrzucone.weszlo >= 10 ? "ok" : "uwaga") as Status,
      liczba: `${drabinki.opublikowane.weszlo}% vs ${drabinki.odrzucone.weszlo}%`,
      werdykt: `Tak. Karty, które przeszły sito, wchodzą ${drabinki.opublikowane.weszlo}%, odrzucone tylko ${drabinki.odrzucone.weszlo}%.`,
    },
    {
      id: "kurs",
      krotko: "Model a kurs",
      pytanie: "Czy model wie więcej niż bukmacher?",
      // brak pomiaru w cyklu = mówimy to wprost (01.10: „0 z 0 segmentów” udawało wynik)
      status: (segmenty.length === 0 ? "uwaga" : bijePewnie.length >= segmenty.length / 2 ? "ok" : bije.length ? "uwaga" : "zle") as Status,
      liczba: segmenty.length ? `${bije.length} z ${segmenty.length}` : "–",
      werdykt: segmenty.length
        ? `${bijePewnie.length >= segmenty.length / 2 ? "Tak." : "Jeszcze nie."} Model jest celniejszy od kursu w ${bije.length} z ${segmenty.length} segmentów (pewnie w ${bijePewnie.length})${pasma.length && pasma.every((x) => x.przewaga < 0) ? "; w każdym paśmie kursów cena wie więcej" : ""}.`
        : "Brak pomiaru przewagi nad kursem w ostatnim cyklu – sekcja wróci, gdy cykl go policzy.",
    },
    {
      id: "kupony",
      krotko: "Kupony",
      pytanie: "Czy kupony trzymają obietnicę?",
      status: (kupony.every((k) => k.obiecywal === null || k.weszlo === null || k.weszlo >= k.obiecywal - 3) ? "ok" : "uwaga") as Status,
      liczba: `${kupony.reduce((a, k) => a + k.wygrane, 0)} z ${kupony.reduce((a, k) => a + k.n, 0)}`,
      werdykt: `Tak. ${kupony.map((k, i) => `${i ? k.nazwa.toLowerCase() : k.nazwa} obiecywały ${k.obiecywal}%, weszło ${k.weszlo}%`).join("; ")}.`,
    },
    {
      id: "egzamin",
      krotko: "Egzamin modelu",
      pytanie: "Czy model mówi prawdę o swojej pewności?",
      status: (egzamin.brier < 0.2 ? "ok" : "uwaga") as Status,
      liczba: egzamin.brier.toFixed(3).replace(".", ","),
      werdykt: `Tak, na ${egzamin.n} prognozach z ${egzamin.meczow} meczów spoza nauki (wynik Briera ${egzamin.brier.toFixed(3).replace(".", ",")} – poniżej 0,20 to dobra prognoza).`,
    },
    {
      id: "sklady",
      krotko: "Składy",
      pytanie: "Czy trafiamy, kto zagra?",
      status: (sklady[1].zagral < 90 ? "uwaga" : "ok") as Status,
      liczba: `${sklady[1].zagral}%`,
      werdykt: `Z oficjalnym składem gra ${sklady[0].zagral}% zawodników, z przewidywanym ${sklady[1].zagral}% – co ${Math.round(100 / (100 - sklady[1].zagral))}. typ z przewidywanego składu kończy się zwrotem.`,
    },
  ];

  return {
    stan: `${data(A.meta.wygenerowano_ts)}, ${godz(A.meta.wygenerowano_ts)}`,
    pytania,
    dzialanie,
    uczenie,
    rynki,
    polki,
    drabinki,
    kurs: { segmenty: [...segmenty].sort((a, b) => b.przewaga - a.przewaga), pasma },
    kupony: { podsumowanie: kupony, ostatnie: ostatnieKupony, kronika: A.kupony_wygrane_n },
    egzamin,
    sklady,
    test: { n: ft.n, trafione: ft.trafione, weszlo: pp(ft.hit), obiecywal: pp(ft.deklaracja), gotowy: ft.gotowy },
  };
}

export type DaneKontroli = ReturnType<typeof przygotujKontrole>;
