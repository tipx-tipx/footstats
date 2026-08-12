"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { memo, useEffect, useRef, useState } from "react";

import { PewnoscDots } from "./badges";
import { ChanceBar, OutcomeColumns } from "./DistributionStrip";
import { DrabinkaLinii } from "./DrabinkaLinii";
import { FormBars } from "./FormBars";
import { Krok, Kroki, SzczegolyTechniczne } from "./KrokiRozwiniecia";
import { Sygnaly, type Sygnal } from "./Sygnaly";
import { kursNetto } from "@/lib/podatek";
import {
  fmtDataCzas,
  fmtKurs,
  fmtLinia,
  fmtMnoznik,
  fmtOpisLiczby,
  fmtProc,
  nazwaPodmiotu,
  opisZakladu,
  PEWNOSC_LABEL,
  stronaLinii,
} from "@/lib/format";
import {
  kierunekMnoznika,
  klasaKierunku,
  profilTypu,
  silaTypu,
} from "@/lib/slownik";
import type { FormaRynku, Strona, ValueBet, Zawodnik } from "@/lib/types";

/** Czy wynik z meczu wszedłby w ten typ (strona typu, nie zawsze „powyżej”). */
const wchodzi = (v: number, linia: number, strona: Strona) =>
  strona === "ponizej" ? v < linia : v > linia;

/** Hit-rate linii w oknach czasowych (mecze z minutami, od najnowszych). */
function oknaFormy(forma: FormaRynku, linia: number, strona: Strona) {
  const zagrane = forma.ostatnie
    .map((v, i) => ({ v, min: forma.minuty[i] ?? 0 }))
    .filter((x) => x.min > 0);
  const okno = (n: number) => {
    const w = zagrane.slice(0, n);
    return { traf: w.filter((x) => wchodzi(x.v, linia, strona)).length, n: w.length };
  };
  return {
    zagrane: zagrane.length,
    l5: okno(5),
    l10: okno(10),
    all: okno(zagrane.length),
  };
}

/**
 * Splity kontekstowe z formy: hit-rate linii w podpróbkach, które dane
 * uczciwie wspierają (kadra vs klub, pełne występy 60+ min). Pokazujemy
 * split dopiero od 3 meczów – mniejsza próba myli bardziej, niż pomaga.
 */
function splityFormy(forma: FormaRynku, linia: number, strona: Strona) {
  const gry = forma.ostatnie.map((v, i) => ({
    v,
    min: forma.minuty[i] ?? 0,
    kadra: forma.kadra?.[i] ?? false,
  }));
  const licz = (xs: { v: number }[]) => ({
    traf: xs.filter((x) => wchodzi(x.v, linia, strona)).length,
    n: xs.length,
  });
  const zagrane = gry.filter((g) => g.min > 0);
  const wynik: { label: string; opis: string; traf: number; n: number }[] = [];
  const kadra = licz(zagrane.filter((g) => g.kadra));
  const klub = licz(zagrane.filter((g) => !g.kadra));
  // splity kadra/klub tylko gdy OBA mają próbę – inaczej to zwykłe "razem"
  if (kadra.n >= 3 && klub.n >= 3) {
    wynik.push(
      { label: "kadra", opis: "mecze reprezentacji w próbce", ...kadra },
      { label: "klub", opis: "mecze klubowe w próbce", ...klub },
    );
  }
  const pelne = licz(zagrane.filter((g) => g.min >= 60));
  if (pelne.n >= 3 && pelne.n < zagrane.length) {
    wynik.push({
      label: "pełne występy",
      opis: "mecze z co najmniej 60 minutami gry",
      ...pelne,
    });
  }
  return wynik;
}

/**
 * Odznaki przewagi – policzalny system sygnałów typu (wzorzec Linemate:
 * każdy typ nosi 0–4 odznaki). Jedno źródło prawdy dla wiersza karty
 * (chipy) i rozwinięcia (sygnały na klik).
 */
function odznakiPrzewagi(bet: ValueBet): {
  znak: string;
  label: string;
  opis: string;
  tone: "brand" | "amber";
}[] {
  const o: ReturnType<typeof odznakiPrzewagi> = [];
  if (!bet.sugestia && bet.ev_uk != null && bet.ev_uk >= 4) {
    o.push({
      znak: "↑",
      label: `+${Math.round(bet.ev_uk)}% ponad cenę z Anglii`,
      opis: `Angielscy bukmacherzy wyceniają to na ~${fmtKurs(bet.kurs_novig ?? 0)} (już bez ich prowizji), a Superbet płaci o ${bet.ev_uk.toFixed(1).replace(".", ",")}% więcej. Innymi słowy: ten sam zakład jest u nas tańszy.`,
      tone: "brand",
    });
  } else if (
    !bet.sugestia &&
    bet.kurs != null &&
    bet.kurs_ref != null &&
    bet.kurs >= bet.kurs_ref * 1.12
  ) {
    o.push({
      znak: "↑",
      label: "kurs wyższy niż gdzie indziej",
      opis: `W Anglii za to samo płacą średnio ${fmtKurs(bet.kurs_ref)}, a Superbet wyraźnie więcej`,
      tone: "brand",
    });
  }
  if (bet.matchup) {
    o.push({
      znak: "◎",
      label: "rywal sprzyja",
      opis: "Przeciwko tej drużynie zawodnicy grający na tej pozycji regularnie notują dużo więcej niż przeciętnie. Liczby znajdziesz niżej, przy „Profil rywala”.",
      tone: "brand",
    });
  }
  if (bet.miekka_linia) {
    o.push({
      znak: "↗",
      label: "zaniżony kurs",
      opis: `Z pozostałych linii Superbetu na ten rynek wychodzi kurs ~${(bet.kurs_oczekiwany ?? 0).toFixed(2).replace(".", ",")}, a akurat ta płaci wyraźnie więcej. Wygląda na przeoczenie bukmachera.`,
      tone: "brand",
    });
  }
  if (bet.rotacja) {
    o.push({
      znak: "↥",
      label: "wchodzi do składu",
      opis: "Wraca do pierwszego składu po przerwie – bukmacher często nie zdążył jeszcze poprawić kursu",
      tone: "amber",
    });
  }
  if (bet.swieze_sklady) {
    o.push({
      znak: "◷",
      label: "świeże składy",
      opis: "Składy ogłoszono w ostatnich ~45 minutach, więc część kursów jest jeszcze sprzed tej wiadomości",
      tone: "amber",
    });
  }
  // PLAKIETKA „z wcześniejszego cyklu" USUNIĘTA (decyzja usera 2026-07-30).
  // Mówiła o kuchni pipeline'u – o tym, że ostatnie przeliczenie nie odtworzyło
  // typu – a nie o samym zakładzie. Flaga `wznowiony` zostaje w danych, bo
  // pilnuje jej siatka bezpieczeństwa (typ raz pokazany zostaje do gwizdka);
  // po prostu nie zawracamy nią głowy na karcie.
  return o;
}

/**
 * Sygnały rozwinięcia: odznaki przewagi + argumenty pewniaka (pewny występ,
 * zapas nad linią) + głos historii + neutralne tło rynku UK i ceny. Jedna
 * linia etykiet, opisy dopiero na klik (komponent Sygnaly).
 */
function sygnalyTypu(
  bet: ValueBet,
  okna: ReturnType<typeof oknaFormy> | null,
  forma?: FormaRynku,
): Sygnal[] {
  const s: Sygnal[] = odznakiPrzewagi(bet).map((o) => ({
    id: o.label,
    znak: o.znak,
    label: o.label,
    opis: `${o.opis}.`,
    ton: o.tone,
  }));
  if (bet.pewniak) {
    // pewny występ – dane siedzą w czynniku „Minuty" (pipeline pisze tam
    // szansę na pierwszy skład), tu wychodzą na światło jako argument
    const minuty = bet.uzasadnienie.czynniki.find((c) => c.nazwa === "Minuty");
    const skladOgloszony = minuty?.opis.includes("pewny występ") ?? false;
    const pSklad = minuty?.opis.includes("pierwszy skład")
      ? Number(minuty.opis.match(/(\d+)\s*%/)?.[1] ?? NaN)
      : NaN;
    if (skladOgloszony) {
      s.push({
        id: "xi",
        znak: "XI",
        label: "w wyjściowym składzie",
        ton: "brand",
        opis: "Trener ogłosił skład i zawodnik wychodzi od pierwszej minuty. Nie ma ryzyka, że przesiedzi mecz na ławce.",
      });
    } else if (pSklad >= 85) {
      s.push({
        id: "xi",
        znak: "XI",
        label: "pewny występ",
        ton: "brand",
        opis: `Szansa, że wyjdzie w pierwszym składzie: ${pSklad}%${
          bet.oczekiwane_minuty != null
            ? `, spodziewamy się ${Math.round(bet.oczekiwane_minuty)} minut na boisku`
            : ""
        }. Ryzyko, że nie zagra, jest tu małe.`,
      });
    }
    // duży zapas nad linią: średnia z formy wyraźnie ponad linię zakładu
    if (
      forma &&
      bet.strona === "powyzej" &&
      okna != null &&
      okna.zagrane >= 5 &&
      forma.srednia90 >= bet.linia * 1.6
    ) {
      s.push({
        id: "zapas",
        znak: "≫",
        label: "duży zapas nad linią",
        ton: "brand",
        opis: `Średnia z ostatnich meczów to ${forma.srednia90
          .toFixed(2)
          .replace(".", ",")} na 90 minut, a linia stoi na ${fmtLinia(
          bet.linia,
        )}. Zapas jest tak duży, że zwykle wystarcza nawet słabszy mecz.`,
      });
    }
  }
  if (okna) {
    const w = okna.l10.n >= 5 ? okna.l10 : okna.all;
    if (w.n >= 5) {
      const hr = w.traf / w.n;
      if (hr >= 0.65) {
        s.push({
          id: "forma-za",
          znak: "✓",
          label: `weszło w ${w.traf} z ${w.n} meczów`,
          ton: "brand",
          opis: `Ten typ wszedłby w ${w.traf} z ostatnich ${w.n} rozegranych meczów. Wykres mecz po meczu jest niżej, w zakładce Forma.`,
        });
      } else if (hr < 0.45) {
        s.push({
          id: "forma-przeciw",
          znak: "↓",
          label: `weszło tylko w ${w.traf} z ${w.n}`,
          ton: "czerwony",
          opis: `Ostrożnie: ten typ wszedłby tylko w ${w.traf} z ostatnich ${w.n} rozegranych meczów. Obejrzyj wykres w zakładce Forma, zanim zagrasz.`,
        });
      }
    }
  }
  // WIEK CENY (2026-08-08). Kurs zapisujemy w chwili, gdy typ trafia na listę,
  // i po nim rozlicza księga – ale u bukmachera mógł się od tego czasu ruszyć.
  // Ofertę drugiego bukmachera pobieramy raz na mecz (decyzja usera: „kurs
  // pobierany jednorazowo, nawet jak później się zmieni"), więc bywa sprzed
  // godzin. Milczenie o tym byłoby najgorszym wyjściem: user zobaczyłby cenę,
  // której nie dostanie, i to wygląda na oszustwo, a nie na nieaktualność.
  // Próg dwóch godzin, żeby nie zawracać głowy przy każdym świeżym typie.
  if (!bet.sugestia && bet.kurs != null && bet.kurs_ts != null) {
    const godzin = Math.floor((Date.now() / 1000 - bet.kurs_ts) / 3600);
    if (godzin >= 2) {
      s.push({
        id: "wiek-ceny",
        znak: "◷",
        label: `cena sprawdzona ${godzin} h temu`,
        ton: "cichy",
        opis: `Ten kurs widzieliśmy ${godzin} godz. temu u ${bet.bukmacher || "bukmachera"} i po nim liczymy wynik. Do gwizdka mógł się lekko zmienić – sprawdź go przed zagraniem.`,
      });
    }
  }
  const maUk = s.some((x) => x.id.includes("vs UK") || x.id === "odstaje od rynku");
  if (!bet.sugestia && bet.kurs_ref != null && !maUk) {
    s.push({
      id: "tlo-uk",
      znak: "·",
      label: `w Anglii płacą ${fmtKurs(bet.kurs_ref)}`,
      ton: "cichy",
      opis:
        bet.kurs_novig != null
          ? `W Anglii za to samo płacą średnio ${fmtKurs(bet.kurs_ref)}, a po odjęciu ich prowizji uczciwa cena wychodzi ${fmtKurs(bet.kurs_novig)}. To punkt odniesienia niezależny od nas.`
          : `W Anglii za to samo płacą średnio ${fmtKurs(bet.kurs_ref)}. To punkt odniesienia niezależny od nas.`,
    });
  }
  // CENA JEST INFORMACJĄ, NIE WERDYKTEM (decyzja właściciela 2026-08-13).
  //
  // Stał tu sygnał „kurs poniżej wartości" przy wartości netto ≤ −8%. Odkąd
  // szansa na karcie jest ściągana do uczciwej ceny (backend: `marza_sciagania`),
  // ta różnica to po prostu marża bukmachera — więc sygnał zapalał się przy
  // KAŻDYM typie i przestał cokolwiek odróżniać. Zamiast werdyktu mówimy
  // wprost, ile zabiera zakład; to ta sama liczba, ale bez oceny typu.
  if (!bet.sugestia && bet.pewniak && bet.kurs != null && bet.fair_kurs) {
    s.push({
      id: "cena",
      znak: "·",
      label: `bez marży byłoby ${fmtKurs(bet.fair_kurs)}`,
      ton: "cichy",
      opis: `${bet.bukmacher} płaci ${fmtKurs(bet.kurs)}. Bez marży bukmachera ten sam zakład płaciłby ${fmtKurs(
        bet.fair_kurs,
      )} – tę różnicę zabiera zakład i jest ona w każdym kursie, u każdego bukmachera. Ten typ bierzesz za to, jak często wchodzi.`,
    });
  }
  return s;
}

/** Liczba w zdaniu werdyktu – mono, żeby czytała się jak odczyt, nie proza. */
function Num({ children }: { children: React.ReactNode }) {
  return <span className="font-data font-semibold">{children}</span>;
}

/**
 * Werdykt pewniaka: prowadzi szansą trafienia, nie ceną. Pewniaki niemal
 * zawsze mają ujemne EV (marża + selekcja za szansę), więc werdykt value
 * („bez przewagi w kursie") mówił „nie graj" na każdej karcie tej sekcji
 * i zaprzeczał chipowi, który user właśnie kliknął. Zdanie główne niesie
 * kategorię typu, cena schodzi do drugiego zdania jako kontekst.
 */
function WerdyktPewniaka({ bet }: { bet: ValueBet }) {
  const p = fmtProc(bet.p_model);
  const fair = fmtKurs(bet.fair_kurs);
  const kurs = fmtKurs(bet.kurs as number);

  let glowne: React.ReactNode;
  if (bet.wyzsza_linia) {
    glowne = (
      <>
        Wyższa linia za lepszy kurs: wciąż <Num>{p}</Num> szans na trafienie.
      </>
    );
  } else if (bet.p_model >= 0.75) {
    glowne = (
      <>
        Model daje temu typowi <Num>{p}</Num> szans – najwyższy przedział na
        liście. Uwaga: przy takich szansach kurs jest niski, więc częste
        trafienia same z siebie nie oznaczają zysku.
      </>
    );
  } else if (bet.p_model >= 0.62) {
    glowne = (
      <>
        Model daje temu typowi <Num>{p}</Num> szans. Wysoka szansa, dobry
        kandydat na kupon.
      </>
    );
  } else if (bet.p_model >= 0.52) {
    glowne = (
      <>
        Model daje temu typowi <Num>{p}</Num> szans, niewiele ponad połowę.
        Graj z rozwagą.
      </>
    );
  } else if ((bet.kurs ?? 0) >= 1.9) {
    glowne = (
      <>
        Niska szansa – <Num>{p}</Num> – za to kurs <Num>{kurs}</Num> płaci
        wyraźnie więcej. Świadome ryzyko, nie wpadka.
      </>
    );
  } else {
    glowne = (
      <>
        Model daje temu typowi tylko <Num>{p}</Num> szans. To najsłabsza
        kategoria na liście, graj ostrożnie.
      </>
    );
  }

  return (
    <>
      <p className="text-[12px] leading-relaxed text-muted">
        {glowne}
      </p>
      {/* CENA JAKO INFORMACJA, NIE WERDYKT (2026-08-13).
          Stały tu dwie gałęzie: „kurs płaci +X ponad wartość" albo „mniej niż
          uczciwe Y – bierzesz za szansę". Odkąd szansa na karcie jest ściągana
          do uczciwej ceny, pierwsza gałąź nie odpala się nigdy, a druga przy
          każdym typie – bo różnica między kursem a uczciwą ceną to po prostu
          marża. Zdanie mówi więc, ile zabiera zakład, i nie ocenia typu.
          Podatek zostaje, bo to jedyne miejsce, gdzie user widzi, co naprawdę
          zostaje z kursu. */}
      <p className="mt-1 text-[12px] leading-relaxed text-muted">
        {bet.bukmacher} płaci <Num>{kurs}</Num>, bez marży bukmachera byłoby{" "}
        <Num>{fair}</Num> – tę różnicę zabiera zakład. Po podatku od stawki
        zostaje <Num>{fmtKurs(kursNetto(bet.kurs!, bet.tryb_podatku))}</Num>.
      </p>
    </>
  );
}

/**
 * Werdykt jednym zdaniem: największa typografia rozwinięcia. Liczby wchodzą
 * do zdania (zamiast osobnego rządka trzech liczb + akapitu, które mówiły
 * to samo dwa razy). Drugie zdanie tłumaczy skąd wniosek.
 */
function WerdyktZdanie({ bet }: { bet: ValueBet }) {
  const fair = fmtKurs(bet.fair_kurs);
  const p = fmtProc(bet.p_model);
  if (bet.pewniak && bet.kurs != null && !bet.sugestia) {
    return <WerdyktPewniaka bet={bet} />;
  }
  if (bet.sugestia || bet.kurs == null) {
    return (
      <>
        <p className="text-[12px] leading-relaxed text-muted">
          Uczciwa cena to <Num>{fair}</Num>. W STS warto grać od{" "}
          <span className="text-brand-deep">
            <Num>~{fmtKurs(bet.fair_kurs * 1.05)}</Num>
          </span>{" "}
          w górę.
        </p>
        <p className="mt-1 text-[12px] leading-relaxed text-muted">
          Model daje temu zdarzeniu {p} szans. Kursu nie pobieramy automatycznie,
          bo ten rynek jest tylko w STS. Jeśli grasz, dodaj zakład ręcznie w
          Moich zakładach.
        </p>
      </>
    );
  }
  const kurs = fmtKurs(bet.kurs);
  const wycena = fmtProc(1 / bet.kurs);
  // JEDNO ZDANIE ZAMIAST TRZECH WERDYKTÓW (2026-08-13, decyzja właściciela).
  //
  // Stały tu trzy gałęzie po wartości netto: „X ponad wartość" / „nie płaci
  // tyle, ile powinien" / „cena praktycznie uczciwa". Odkąd szansa na karcie
  // jest ściągana do uczciwej ceny (backend: `marza_sciagania`), różnica
  // między kursem a naszą wyceną to po prostu marża bukmachera — pierwsza
  // gałąź nie odpalała się nigdy, druga przy każdym typie. Werdykt o przewadze
  // przestał więc cokolwiek znaczyć i schodzi z karty; zostaje to, co jest
  // prawdą i co odróżnia typy od siebie: szansa, cena i podatek.
  const poPodatku = fmtKurs(kursNetto(bet.kurs, bet.tryb_podatku));
  return (
    <>
      <p className="text-[12px] leading-relaxed text-muted">
        {bet.bukmacher} płaci <Num>{kurs}</Num>, bez marży bukmachera byłoby{" "}
        <Num>{fair}</Num>. Po podatku od stawki zostaje <Num>{poPodatku}</Num>.
      </p>
      <p className="mt-1 text-[12px] leading-relaxed text-muted">
        Model daje temu zdarzeniu {p} szans, a kurs wycenia je na {wycena}.
      </p>
    </>
  );
}

/**
 * Odczyt okna formy (L5 · L10 · razem, splity): kolor niesie ton, tekst
 * niesie treść. Bez washa i pastylki – chipów zostaje na karcie tylko status.
 */
function OdczytOkna({
  label,
  traf,
  n,
  tytul,
}: {
  label: string;
  traf: number;
  n: number;
  tytul?: string;
}) {
  const r = n > 0 ? traf / n : 0;
  const kolor =
    n >= 3 && r >= 0.6
      ? "text-data-green-ink"
      : n >= 3 && r < 0.45
        ? "text-data-red-ink"
        : "text-muted";
  return (
    <span className={`font-data text-[11px] font-semibold ${kolor}`} title={tytul}>
      <span className="mr-1 text-[9px] font-medium uppercase opacity-70">{label}</span>
      {traf}/{n}
    </span>
  );
}

/**
 * KROK „JAK BYŁO OSTATNIO" – surowa historia i jedno zdanie, co z niej wynika.
 *
 * To jest część historii, nie materiał diagnostyczny, więc od 2026-08-01
 * (część 2) stoi na wierzchu rozwinięcia, a nie w zakładce. Rozbiór na okna
 * L5/L10/razem i splity kadra-klub został – ale zszedł do „Szczegółów
 * technicznych", bo odpowiada na pytanie o próbę, a nie o ten mecz.
 */
function HistoriaKrotko({ bet, forma }: { bet: ValueBet; forma: FormaRynku }) {
  const okna = oknaFormy(forma, bet.linia, bet.strona);
  const w = okna.l10.n >= 5 ? okna.l10 : okna.all;
  return (
    <div>
      <FormBars
        counts={forma.ostatnie}
        minutes={forma.minuty}
        opponents={forma.rywale}
        kadra={forma.kadra}
        line={bet.linia}
        side={bet.strona}
        height={64}
        rynek={bet.rynek.toLowerCase()}
      />
      {okna.zagrane > 0 && (
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          W {w.n} ostatnich {w.n === 1 ? "meczu" : "meczach"} ten typ wszedłby{" "}
          <span className="font-data font-semibold text-ink">{w.traf}</span>{" "}
          {w.traf === 1 ? "raz" : "razy"}, średnio wychodziło{" "}
          <span className="font-data font-semibold text-ink">
            {forma.srednia90.toFixed(2).replace(".", ",")}
          </span>{" "}
          na mecz.
        </p>
      )}
    </div>
  );
}

/**
 * Rozbiór historii na okna i podpróbki – materiał diagnostyczny, więc jedzie
 * pod „Szczegóły techniczne". Odpowiada na pytanie „na czym stoi ta próba",
 * którego prawie nikt nie zadaje przed postawieniem zakładu.
 */
function HistoriaWLiczbach({ bet, forma }: { bet: ValueBet; forma: FormaRynku }) {
  const okna = oknaFormy(forma, bet.linia, bet.strona);
  const zagrane = okna.zagrane;
  // okna jak w Props.cash/StatsHub: forma TERAZ vs średnia – L5 wykrywa
  // trend, którego jedna suma nie pokaże
  const odczyty = [
    ...(zagrane >= 3 ? [{ label: "L5", ...okna.l5 }] : []),
    ...(zagrane >= 7 ? [{ label: "L10", ...okna.l10 }] : []),
    { label: "razem", ...okna.all },
  ];
  const splity = splityFormy(forma, bet.linia, bet.strona);
  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
        {zagrane > 0 &&
          odczyty.map((c) => <OdczytOkna key={c.label} {...c} />)}
      </div>
      {zagrane > 0 && (
        <p className="mt-1.5 text-[11px] leading-relaxed text-faint">
          Ile razy ten typ by wszedł – w ostatnich 5, 10 i we wszystkich
          meczach, w których {bet.podmiot_typ === "druzyna" ? "drużyna grała" : "zawodnik grał"}.
        </p>
      )}
      {/* etykiety mówią same za siebie – bez dymków, które i tak nie
          działają na telefonie (przegląd kart 2026-08-01) */}
      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-hairline pt-2.5">
        <span className="font-data text-[11px] font-semibold text-ink-soft">
          <span className="mr-1 text-[9px] font-medium uppercase opacity-70">
            średnio na mecz z ostatnich {zagrane}
          </span>
          {forma.srednia90.toFixed(2).replace(".", ",")}
        </span>
        {bet.oczekiwane_minuty != null && (
          <span className="font-data text-[11px] font-semibold text-ink-soft">
            <span className="mr-1 text-[9px] font-medium uppercase opacity-70">
              spodziewamy się minut w tym meczu
            </span>
            {Math.round(bet.oczekiwane_minuty)}
          </span>
        )}
        {splity.map((s) => (
          <OdczytOkna
            key={s.label}
            {...s}
            tytul={`${s.opis}: ten typ wszedłby w ${s.traf} z ${s.n} meczów`}
          />
        ))}
      </div>
    </div>
  );
}

/**
 * Odchylenie czynnika od neutralnego 1,00 jako kreska w lewo/prawo od osi.
 * Pełne wychylenie = ±15% – realne czynniki mieszczą się w ~0,85–1,15,
 * więc szersza skala robiła z każdego z nich niewidoczną drobinkę.
 */
function MnoznikBar({ m }: { m: number }) {
  const neutralny = Math.abs(m - 1) < 0.005;
  const odch = Math.min(Math.abs(m - 1) / 0.15, 1);
  return (
    <span aria-hidden className="relative block h-2.5 w-10 shrink-0">
      <span className="absolute left-1/2 top-0 h-full w-px bg-hairline-strong" />
      {!neutralny && (
        <span
          className={`absolute top-1/2 h-[3px] min-w-[3px] -translate-y-1/2 rounded-full ${
            m > 1 ? "left-1/2 bg-data-green" : "right-1/2 bg-data-red"
          }`}
          style={{ width: `${odch * 50}%` }}
        />
      )}
    </span>
  );
}

/**
 * Sygnalizacja świetlna (wzorzec Outlier): triage wzrokiem bez czytania.
 * zielony = historia (L10) i model zgodnie wysoko; czerwony = historia
 * przeczy linii; bursztyn = środek; null = za mała próba (bez paska).
 */
export function swiatloTypu(
  forma: FormaRynku | undefined,
  linia: number,
  pModel: number,
  strona: Strona,
): "green" | "amber" | "red" | null {
  if (!forma) return null;
  const o = oknaFormy(forma, linia, strona);
  if (o.zagrane < 5) return null;
  const hr = o.l10.traf / Math.max(o.l10.n, 1);
  if (hr >= 0.65 && pModel >= 0.55) return "green";
  if (hr < 0.45) return "red";
  return "amber";
}

export const SWIATLO_STYL = {
  green: {
    pasek: "bg-data-green",
    opis: "Zielone światło: w ostatnich 10 meczach ta linia padła co najmniej 6-7 razy, a model też daje wysoką szansę",
  },
  amber: {
    pasek: "bg-data-amber",
    opis: "Żółte światło: historia zawodnika i model nie zgadzają się ze sobą. Zajrzyj w szczegóły przed zagraniem.",
  },
  red: {
    pasek: "bg-data-red",
    opis: "Czerwone światło: w ostatnich 10 meczach ta linia padła mniej niż 5 razy. Historia przeczy temu typowi.",
  },
} as const;

/**
 * Oznaczenie typu – JEDNA skala z `lib/slownik.ts`, ta sama w całym
 * produkcie (2026-08-01). Wcześniej były tu trzy równoległe słowniki:
 * „★ pewniak / mocny typ / umiarkowany / ryzykowny" tutaj, „TOP / mocny /
 * solidny" na kartach Drabinek i jeszcze raz czterostopniowa skala niżej
 * w rozwinięciu. Do tego „perełka" i „wyższa linia" mówiły to samo dwiema
 * nazwami, choć opisują nie SIŁĘ typu, tylko sposób jego postawienia –
 * dlatego dziś to osobna, druga plakietka (`profilTypu`).
 */
function tierTypu(bet: ValueBet): {
  label: string;
  cls: string;
  opis: string;
} {
  const profil = profilTypu(bet);
  if (profil) return profil;
  const s = silaTypu(bet.p_model);
  return { label: s.label, cls: s.cls, opis: s.opis };
}

/** Nazwy czynników w mianowniku prozy „skąd ta liczba". */
const CZYNNIK_PO_LUDZKU: Record<string, string> = {
  Minuty: "przewidywane minuty",
  Rywal: "profil rywala",
  "Profil rywala": "profil rywala",
  Sędzia: "sędzia",
  "Scenariusz meczu": "przewidywany przebieg meczu",
  "Matchup (kto na kogo)": "zestawienie z rywalem",
  "Dom / wyjazd": "miejsce meczu",
  // rynki drużynowe nazywają czynniki inaczej niż zawodnicze; bez tych
  // dwóch wpisów proza mówiła „w górę ciągną dom i wyjazd i przewidywany
  // przebieg meczu" – dwa „i" pod rząd i nazwa wprost z kodu backendu
  "Dom i wyjazd": "miejsce meczu",
  "Styl rywala": "styl gry rywala",
};

const listaPoPolsku = (xs: string[]) =>
  xs.join(", ").replace(/, ([^,]*)$/, " i $1");

/**
 * Proza „skąd ta liczba": baza z ostatnich meczów → korekty na ten mecz →
 * oczekiwany wynik → próg linii → szansa. Zamiast osi z kursem bukmachera,
 * której nikt nie rozumiał – po prostu opowiadamy, jak model doszedł do
 * swojego procentu. Ostatnie zdanie domyka rozjazd „oczekiwane 2,3 vs 76%"
 * (model dolicza ryzyko krótszej gry, patrz pułapka p_model vs rozkład).
 *
 * OD 2026-08-01 (część 2) zwraca DWA KAWAŁKI, nie jedno zdanie: pierwszy jest
 * krokiem „skąd ta liczba", drugi krokiem „co zmienia ten mecz". Wcześniej
 * cała proza leciała jednym ciągiem – i, co gorsza, wisiała wyłącznie przy
 * typach o wysokiej szansie (`OcenaTypu`), więc karta drużynowa, czyli jedyny
 * zarabiający strumień, nie tłumaczyła się w ogóle.
 */
function skadTaLiczba(
  bet: ValueBet,
): { baza: string; zmiana: string } | null {
  const cz = bet.uzasadnienie.czynniki;
  const baza = cz.find((c) => c.nazwa === "Poziom bazowy");
  if (!baza) return null;
  const korekty = cz.filter(
    (c) => c.mnoznik != null && Math.abs(c.mnoznik - 1) > 0.02,
  );
  const nazwa = (n: string) => CZYNNIK_PO_LUDZKU[n] ?? n.toLowerCase();
  const wGore = korekty
    .filter((c) => (c.mnoznik as number) > 1)
    .map((c) => nazwa(c.nazwa));
  const wDol = korekty
    .filter((c) => (c.mnoznik as number) < 1)
    .map((c) => nazwa(c.nazwa));
  let korekta: string;
  if (wGore.length > 0 && wDol.length > 0) {
    korekta = `Na ten mecz w górę ${
      wGore.length > 1 ? "ciągną" : "ciągnie"
    } ją ${listaPoPolsku(wGore)}, w dół ${listaPoPolsku(wDol)}`;
  } else if (wDol.length > 0) {
    korekta = `Na ten mecz ${
      wDol.length > 1 ? "obniżają" : "obniża"
    } ją ${listaPoPolsku(wDol)}`;
  } else if (wGore.length > 0) {
    korekta = `Na ten mecz ${
      wGore.length > 1 ? "podnoszą" : "podnosi"
    } ją ${listaPoPolsku(wGore)}`;
  } else {
    korekta = "Warunki tego meczu niewiele tu zmieniają";
  }
  const ocz = bet.uzasadnienie.oczekiwana_liczba
    .toFixed(1)
    .replace(".", ",");
  const prog =
    bet.strona === "ponizej"
      ? `Typ wchodzi przy najwyżej ${Math.floor(bet.linia)}`
      : Math.floor(bet.linia) + 1 === 1
        ? "Do wejścia typu wystarczy 1"
        : `Do wejścia typu potrzeba co najmniej ${Math.floor(bet.linia) + 1}`;
  // "ryzyko krótszej gry" dotyczy zawodnika (rotacja, zmiana); drużyna
  // gra zawsze pełny mecz – jej szansa wynika z rozkładu możliwych wyników.
  //
  // OD 2026-07-29 pokazywana liczba jest jeszcze ściągnięta o zmierzony
  // rozjazd deklaracji z wynikami, więc zdanie „rozkład daje X%" przestałoby
  // być prawdziwe – X nie pochodzi już z samego rozkładu.
  const skad = bet.p_urealnione
    ? "a po odjęciu tego, o ile takie typy rozmijały się z rzeczywistością, zostaje"
    : bet.podmiot_typ === "druzyna"
      ? "a rozkład możliwych wyników daje"
      : "ale model dolicza jeszcze ryzyko krótszej gry i ostatecznie daje";
  const domkniecie = `${prog}, ${skad} ${fmtProc(bet.p_model)}.`;
  return {
    baza: `${fmtOpisLiczby(baza.opis)}.`,
    zmiana: `${korekta} – zostaje ok. ${ocz}. ${domkniecie}`,
  };
}


/**
 * „W ostatnich 10 meczach weszłoby 2 razy, a wy dajecie 48%" – zgłoszenie
 * usera 2026-08-01 (Viking FK, rożne poniżej 5,5).
 *
 * OBIE LICZBY BYŁY POPRAWNE, tylko liczyły co innego, a karta nigdzie tego
 * nie mówiła. Licznik trafień patrzy na 10 ostatnich meczów i nic poza tym.
 * Model bierze ~20 meczów, waży świeższe mocniej, ściąga wynik do średniej
 * rozgrywek (krótka próba nie ma prawa decydować sama) i dopiero potem
 * poprawia go o rywala i miejsce gry. Przy Vikingu ostatnie 10 dawało 20%,
 * pełne 20 meczów 45%, a po korekcie na wyjazd wyszło 48%.
 *
 * Zestawione bez słowa komentarza wyglądało to jak pomyłka – i to jest
 * najgorszy możliwy efekt, bo akurat TU liczby były w porządku.
 *
 * Blok pokazuje się tylko przy realnym rozjeździe (12 pp), żeby nie tłumaczyć
 * rzeczy, które same się zgadzają.
 */
const PROG_ROZJAZDU = 0.12;

function RozjazdZHistoria({
  bet,
  okna,
}: {
  bet: ValueBet;
  okna: ReturnType<typeof oknaFormy> | null;
}) {
  const w = okna?.l10;
  if (!w || w.n < 5) return null;
  const hr = w.traf / w.n;
  const roznica = bet.p_model - hr;
  if (Math.abs(roznica) < PROG_ROZJAZDU) return null;
  const wGore = roznica > 0;
  const ruszaja = bet.uzasadnienie.czynniki
    .filter((c) => c.mnoznik != null && Math.abs(c.mnoznik - 1) > 0.04)
    .filter((c) => (wGore ? (c.mnoznik as number) < 1 : (c.mnoznik as number) > 1))
    .map((c) => (CZYNNIK_PO_LUDZKU[c.nazwa] ?? c.nazwa.toLowerCase()));
  return (
    <p className="mt-2 text-sm leading-relaxed text-muted">
      Ta liczba i nasza szansa (
      <span className="font-data font-semibold text-ink">
        {fmtProc(bet.p_model)}
      </span>
      ) to nie pomyłka – liczą co innego. Licznik wyżej patrzy tylko na {w.n}{" "}
      ostatnich meczów. Model bierze około dwudziestu, świeższe waży mocniej,
      ściąga wynik do średniej rozgrywek – bo krótka seria nie ma prawa
      decydować sama – i dopiero potem poprawia go o rywala i miejsce gry.
      {ruszaja.length > 0 && (
        <>
          {" "}
          Tutaj w {wGore ? "górę" : "dół"} ciągnie{" "}
          {ruszaja.length > 1 ? "je" : "ją"} {listaPoPolsku(ruszaja)}.
        </>
      )}
    </p>
  );
}

type TabSzczegolow = "forma" | "czynniki" | "wyniki";

/**
 * Rozwinięcie typu: werdykt z akcją, oś wyceny, sygnały i głębia w
 * zakładkach. Współdzielone przez kartę (BetCard) i gęsty wiersz tablicy
 * (BetRow) – jedna prawda o szczegółach niezależnie od gęstości listy.
 */
export function SzczegolyTypu({
  bet,
  forma,
  open,
}: {
  bet: ValueBet;
  forma?: FormaRynku;
  open: boolean;
}) {
  const okna = forma ? oknaFormy(forma, bet.linia, bet.strona) : null;
  const sygnaly = sygnalyTypu(bet, okna, forma);

  // SZCZEGÓŁY TECHNICZNE ZWINIĘTE (2026-08-01, zasada uzgodniona z userem).
  // Rozwinięcie karty odpowiadało na pytania, których nikt nie zadał: tabela
  // mnożników, przedział ufności, rozkład możliwych wyników. To materiał
  // diagnostyczny – potrzebny, ale dla jednego użytkownika na stu. Na wierzchu
  // zostaje historia w czterech krokach, która odpowiada na to jedno pytanie,
  // które zadaje każdy: dlaczego ten typ i czemu mam w to wierzyć.
  const taby: { kod: TabSzczegolow; label: string }[] = [
    ...(forma ? [{ kod: "forma" as const, label: "Historia w liczbach" }] : []),
    ...(bet.uzasadnienie.czynniki.length > 0
      ? [{ kod: "czynniki" as const, label: "Czynniki modelu" }]
      : []),
    ...(bet.rozklad ? [{ kod: "wyniki" as const, label: "Możliwe wyniki" }] : []),
  ];
  const [tab, setTab] = useState<TabSzczegolow>(taby[0]?.kod ?? "czynniki");
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const onTabKeyDown = (
    e: React.KeyboardEvent<HTMLButtonElement>,
    idx: number,
  ) => {
    let next = idx;
    if (e.key === "ArrowRight") next = (idx + 1) % taby.length;
    else if (e.key === "ArrowLeft") next = (idx - 1 + taby.length) % taby.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = taby.length - 1;
    else return;
    e.preventDefault();
    setTab(taby[next].kod);
    tabRefs.current[next]?.focus();
  };

  // rozkład (i „inne linie”) liczą się przy przewidywanych minutach, p_model
  // dokłada do tego scenariusze rotacji – te dwie liczby potrafią się rozjechać
  // o kilkanaście pp, więc karta musi powiedzieć wprost, skąd różnica
  const przyMinutach =
    bet.oczekiwane_minuty != null ? Math.round(bet.oczekiwane_minuty) : null;
  const pLiniiZRozkladu = (() => {
    if (!bet.rozklad) return null;
    const total = bet.rozklad.reduce((a, b) => a + b, 0) || 1;
    const over =
      bet.rozklad.slice(Math.floor(bet.linia) + 1).reduce((a, b) => a + b, 0) / total;
    return bet.strona === "ponizej" ? 1 - over : over;
  })();
  const rozjazdMinut =
    pLiniiZRozkladu != null && Math.abs(pLiniiZRozkladu - bet.p_model) >= 0.03;

  const reduced = useReducedMotion();

  // JEDNA HISTORIA ZAMIAST CZTERECH SEKCJI (2026-08-01, część 2 przeglądu).
  //
  // Rozwinięcie otwierał WERDYKT – czyli wniosek, postawiony przed rachunkiem,
  // więc do wzięcia wyłącznie na wiarę. Teraz karta prowadzi tak, jak człowiek
  // tłumaczy typ na głos: skąd bierzemy tę liczbę → co zmienia ten mecz → jak
  // było ostatnio → i dopiero na końcu, gdzie jest w tym przewaga.
  //
  // Proza „skąd ta liczba" wisiała dotąd wyłącznie przy typach o wysokiej
  // szansie (wewnątrz `OcenaTypu`). Karta drużynowa – jedyny strumień, na
  // którym zarabiamy – nie tłumaczyła się w ogóle. Teraz jedzie na każdej.
  const proza = skadTaLiczba(bet);
  const pokazHistorie = forma != null && (okna?.zagrane ?? 0) > 0;
  // krok „jak było ostatnio" niesie już tę samą liczbę co sygnały o formie –
  // bez tego filtra to samo „weszło w 7 z 10" pada dwa razy w jednym akapicie
  const sygnalyDoPokazania = pokazHistorie
    ? sygnaly.filter((s) => s.id !== "forma-za" && s.id !== "forma-przeciw")
    : sygnaly;

  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          key="detail"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.28, ease: [0.25, 0.9, 0.3, 1] }}
        >
          <div className="border-t border-hairline bg-paper/50 px-4 py-5 sm:px-6">
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.04 }}
            >
              {/* LINIA KONTEKSTU, NIE KROK (2026-08-02). Karta zaczynała się
                  krokiem „co musi się stać", który tłumaczył dorosłemu
                  człowiekowi, że „poniżej 0,5" znaczy „bez gola". Zamiast tego
                  jedno ciche zdanie: kiedy mecz i — przy typie wznowionym —
                  kiedy go wystawiliśmy. To drugie jest potrzebne naprawdę:
                  kurs jest ZAMROŻONY z tamtej chwili i u bukmachera może dziś
                  wyglądać inaczej. */}
              <p className="mb-4 text-[13px] leading-relaxed text-faint">
                {bet.mecz} · {fmtDataCzas(bet.kickoff_ts)}
                {bet.opublikowano_ts ? (
                  <>
                    {" · "}wystawiony {fmtDataCzas(bet.opublikowano_ts)} po
                    kursie {bet.kurs != null ? fmtKurs(bet.kurs) : "–"}
                  </>
                ) : null}
              </p>

              {/* RYNEK WSTRZYMANY — MÓWIMY, ZAMIAST MILCZEĆ (2026-08-03).
                  Kwarantanna blokuje nowe typy z rynku, ale tego nie
                  wycofujemy: cena jest zamrożona i user mógł go zagrać.
                  OSTRZEŻENIE STOI PRZED HISTORIĄ (2026-08-06, ta sama zasada
                  co „raczej poza składem" na drabince): jeśli sami przestaliśmy
                  ten zakład polecać, reszta rachunku jest drugorzędna —
                  w kroku ceny na dole nikt go nie widział. */}
              {/* „TEGO ZAKŁADU", NIE „TEGO RYNKU" (2026-08-04). Wstrzymanie
                  bywa węższe niż rynek: zdejmujemy samą stronę linii, a druga
                  strona tego samego rynku jest dalej typowana. */}
              {bet.rynek_wstrzymany && (
                <p className="mb-4 rounded-(--radius-control) bg-data-amber-wash px-3.5 py-2.5 text-sm leading-relaxed text-data-amber-ink">
                  Tego zakładu chwilowo nie polecamy – ostatnie rozliczenia
                  takich typów wychodzą pod kreską, więc nowych nie wystawiamy
                  i nie wchodzą do kuponów. Ten został wystawiony wcześniej,
                  po cenie z tamtej chwili, i dlatego zostaje na liście.
                </p>
              )}

              <Kroki>
                {/* KARTA NIGDY NIE MÓWI O SOBIE (2026-08-02). Stało tu zdanie
                    „tej karcie nie rozpiszemy pełnego rachunku" — komunikat
                    o naszej kuchni, nie o zakładzie, a czytelnik słyszał w nim
                    „nie wiemy, czemu to polecamy". Zdanie wypada bez
                    zastępstwa: krok, dla którego nie mamy materiału, po prostu
                    nie istnieje. Materiał ma być, a nie tłumaczenie, czemu go
                    nie ma — stąd dosypywanie formy drużyn w pipelinie. */}
                {proza && (
                  <Krok kod="skad">
                    <p className="text-sm leading-relaxed text-ink-soft">
                      {proza.baza}
                    </p>
                  </Krok>
                )}

                {/* FAKTY PRZED KOREKTAMI, HISTORIA OTWARTA (2026-08-06,
                    układ „historia sercem" zaakceptowany na drabinkach):
                    najpierw surowe mecze, potem nasze korekty, cena na końcu.
                    Zwinięty krok wyglądał jak pusta etykieta z myślnikiem. */}
                {pokazHistorie && forma && (
                  <Krok kod="ostatnio">
                    <HistoriaKrotko bet={bet} forma={forma} />
                    {/* DLACZEGO NIE TYLE, ILE MÓWI OSTATNIE 10 MECZÓW.
                        Odpowiedź na najczęstsze „czy to na pewno nie błąd" –
                        i jedyne miejsce, gdzie ma sens: tuż pod liczbą,
                        która to pytanie wywołuje. */}
                    <RozjazdZHistoria bet={bet} okna={okna} />
                  </Krok>
                )}

                {proza && (
                  <Krok kod="zmiana">
                    <p className="text-sm leading-relaxed text-ink-soft">
                      {proza.zmiana}
                    </p>
                  </Krok>
                )}

                {/* „CENA", NIE „GDZIE JEST PRZEWAGA" (2026-08-06, układ
                    „historia sercem"): dodatek do historii, nie punkt
                    kulminacyjny. Stoi OSTATNIA i mówi najdrobniejszym drukiem
                    na karcie. Oś wyceny wypadła bez zastępstwa — jej liczby
                    (uczciwy kurs, cena, marża) są w zdaniu obok. */}
                <Krok kod="przewaga" tytul="cena">
                  {/* PLAKIETKA RYZYKA USUNIĘTA (2026-08-02). Karta oceniała
                      ryzyko TRZY RAZY jedna nad drugą: plakietką („ryzyko:
                      średnie"), zdaniem werdyktu („niska szansa, świadome
                      ryzyko") i czterostopniową skalą pod spodem. Trzy skale
                      na jedną rzecz to nie precyzja, tylko szum — zostaje
                      zdanie, bo jako jedyne mówi, co z tym zrobić. */}
                  <WerdyktZdanie bet={bet} />

                  {/* SKALA CZTERECH SZANS ZASTĄPIONA ZDANIEM (2026-08-02).
                      Cztery kolumny zajmowały ćwierć rozwinięcia, żeby
                      podświetlić jedną komórkę. Pełna skala ma sens RAZ na
                      stronie, w „Jak to działa" — nie przy każdym typie. */}
                  {bet.pewniak && (
                    <p className="mt-2 text-[12px] leading-relaxed text-muted">
                      <span className="font-data font-semibold text-ink-soft">
                        {fmtProc(bet.p_model)}
                      </span>{" "}
                      – {silaTypu(bet.p_model).label}. {silaTypu(bet.p_model).opis}
                    </p>
                  )}

                  {/* sygnały w jednej linii, opis na klik */}
                  {sygnalyDoPokazania.length > 0 && (
                    <div className="mt-3">
                      <Sygnaly
                        naglowek={
                          sygnalyDoPokazania.some((s) => s.ton === "czerwony")
                            ? "Za i przeciw"
                            : "Za tym typem"
                        }
                        sygnaly={sygnalyDoPokazania}
                      />
                    </div>
                  )}

                  {/* PRZYCISK „dodaj do moich zakładów" USUNIĘTY 2026-08-04
                      razem z całą zakładką (patrz Nav.tsx). Wpisy siedziały
                      w localStorage, więc nie przechodziły między urządzeniami,
                      a sam mechanizm wymagał od użytkownika ręcznego wpisywania
                      kursu zamknięcia — pracy, której sensu nie tłumaczyliśmy. */}
                  {(bet.sugestia || bet.kurs == null) && (
                    <p className="font-data mt-4 text-[10px] uppercase tracking-wide text-faint">
                      kurs sprawdzasz ręcznie
                    </p>
                  )}
                </Krok>
              </Kroki>
            </motion.div>

            {/* głębia na żądaniu: jedna sekcja naraz = jeden wykres naraz */}
            {taby.length > 0 && (
              <SzczegolyTechniczne>
                <div
                  role="tablist"
                  aria-label="Szczegóły typu"
                  className="flex flex-wrap items-end gap-x-5 border-b border-hairline"
                >
                  {taby.map((t, i) => (
                    <button
                      key={t.kod}
                      ref={(el) => {
                        tabRefs.current[i] = el;
                      }}
                      role="tab"
                      tabIndex={tab === t.kod ? 0 : -1}
                      aria-selected={tab === t.kod}
                      onClick={() => setTab(t.kod)}
                      onKeyDown={(e) => onTabKeyDown(e, i)}
                      className={`font-display -mb-px border-b-2 px-0.5 pb-2 pt-1 text-[11px] font-semibold uppercase tracking-wide transition-colors ${
                        tab === t.kod
                          ? "border-brand text-brand-deep"
                          : "border-transparent text-muted hover:text-ink"
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>

                <AnimatePresence mode="wait" initial={false}>
                  <motion.div
                    key={tab}
                    initial={reduced ? false : { opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={reduced ? undefined : { opacity: 0 }}
                    transition={{ duration: 0.16 }}
                    className="pt-4"
                  >
                    {tab === "forma" && forma && (
                      <HistoriaWLiczbach bet={bet} forma={forma} />
                    )}

                    {tab === "czynniki" && (
                      /* KIERUNEK SŁOWEM, MNOŻNIK JAKO PRZYPIS (2026-08-01).
                         Kolumna liczb „×1,12" nie ma jednostki ani kierunku:
                         żeby cokolwiek z niej wyczytać, trzeba wiedzieć, że
                         1,00 znaczy „bez wpływu" – a to wiedza wewnętrzna.
                         Teraz każdy wiersz mówi wprost „podnosi" / „obniża",
                         a sama liczba została dla tych, którzy jej szukają. */
                      <ul className="space-y-2">
                        {bet.uzasadnienie.czynniki.map((c) => (
                          <li
                            key={c.nazwa}
                            className="flex items-start gap-3 text-sm"
                          >
                            <span className="flex-1">
                              <span className="font-medium">{c.nazwa}:</span>{" "}
                              <span className="text-ink-soft">
                                {fmtOpisLiczby(c.opis)}
                              </span>
                            </span>
                            {c.mnoznik !== null && (
                              <span className="flex shrink-0 items-center gap-2 pt-1">
                                <MnoznikBar m={c.mnoznik} />
                                <span className="w-24 text-right">
                                  <span
                                    className={`text-xs font-semibold ${klasaKierunku(c.mnoznik)}`}
                                  >
                                    {kierunekMnoznika(c.mnoznik)}
                                  </span>
                                  <span className="font-data block text-[10px] text-faint">
                                    {fmtMnoznik(c.mnoznik)}
                                  </span>
                                </span>
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}

                    {tab === "wyniki" && bet.rozklad && (
                      <div>
                        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3">
                          <span className="text-[10px] uppercase tracking-wide text-faint">
                            liczba zdarzeń w meczu
                          </span>
                          {przyMinutach && (
                            <span className="text-[10px] uppercase tracking-wide text-faint">
                              przy {przyMinutach} min
                            </span>
                          )}
                        </div>
                        <OutcomeColumns
                          dist={bet.rozklad}
                          line={bet.linia}
                          side={stronaLinii(bet.strona)}
                        />
                        {/* rozkład liczy się przy przewidywanych minutach, a p_model
                            wlicza jeszcze ryzyko rotacji – bez tego zdania user widzi
                            dwie różne liczby na tej samej karcie i traci zaufanie */}
                        {rozjazdMinut && (
                          <p className="mt-2 text-xs leading-relaxed text-faint">
                            Model daje temu typowi{" "}
                            <span className="font-data text-ink-soft">
                              {fmtProc(bet.p_model)}
                            </span>
                            , czyli mniej, bo wlicza też ryzyko, że zawodnik
                            zagra krócej albo w ogóle nie wyjdzie
                            {/* od 2026-07-29 to już nie jedyny powód różnicy:
                                pokazywana szansa jest dodatkowo ściągnięta
                                o zmierzony rozjazd deklaracji z wynikami.
                                Bez tego zdania karta zwalałaby całą różnicę
                                na minuty – czyli mówiłaby nieprawdę. */}
                            {bet.p_urealnione
                              ? " – a na końcu jeszcze o tyle, o ile takie typy rozmijały się z rzeczywistością w rozliczeniach."
                              : "."}
                          </p>
                        )}
                        <h4 className="mb-2.5 mt-5 text-xs font-semibold uppercase tracking-wide text-faint">
                          Szanse na inne linie
                        </h4>
                        {/* podkreślenie zamiast kafelka – linia tego typu czyta się
                            jak aktywna zakładka */}
                        <div className="flex items-end gap-3">
                          {[0.5, 1.5, 2.5, 3.5].map((l) => {
                            const total =
                              bet.rozklad!.reduce((a, b) => a + b, 0) || 1;
                            const pOver =
                              bet.rozklad!
                                .slice(Math.floor(l) + 1)
                                .reduce((a, b) => a + b, 0) / total;
                            const p =
                              bet.strona === "ponizej" ? 1 - pOver : pOver;
                            const aktualna = Math.abs(l - bet.linia) < 0.01;
                            if (p < 0.02 && !aktualna) return null;
                            const skrot =
                              bet.strona === "ponizej" ? "pon." : "pow.";
                            return (
                              <div
                                key={l}
                                className={`flex-1 border-b-2 pb-1.5 ${
                                  aktualna ? "border-brand" : "border-hairline"
                                }`}
                                title={
                                  aktualna
                                    ? "Linia tego typu"
                                    : `Szansa modelu na ${
                                        bet.strona === "ponizej"
                                          ? "poniżej"
                                          : "powyżej"
                                      } ${fmtLinia(l)}`
                                }
                              >
                                <p className="text-[10px] uppercase tracking-wide text-faint">
                                  {skrot} {fmtLinia(l)}
                                </p>
                                <p
                                  className={`font-data mt-0.5 text-base font-semibold leading-none ${
                                    aktualna ? "text-brand-deep" : "text-ink"
                                  }`}
                                >
                                  {fmtProc(p)}
                                </p>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </motion.div>
                </AnimatePresence>
              </SzczegolyTechniczne>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** memo: przy zmianie filtrów listy nie przerenderowują się wszystkie karty */
export const BetCard = memo(function BetCard({
  bet: glowny,
  rank,
  zawodnik,
  warianty,
}: {
  bet: ValueBet;
  rank: number;
  zawodnik?: Zawodnik;
  /** wszystkie linie tego samego typu (mecz, podmiot, rynek, strona).
   *  Więcej niż jedna = karta dostaje drabinkę wyboru zamiast dublować się
   *  w liście – patrz lib/warianty.ts */
  warianty?: ValueBet[];
}) {
  const [open, setOpen] = useState(false);
  const [wybranyId, setWybranyId] = useState(glowny.id);
  const reduced = useReducedMotion();

  // karta tłumaczy JEDEN szczebel naraz – ten, który user kliknął
  const bet = warianty?.find((b) => b.id === wybranyId) ?? glowny;

  const forma = zawodnik?.forma[bet.rynek_kod];
  const swiatlo = swiatloTypu(forma, bet.linia, bet.p_model, bet.strona);
  const odznaki = odznakiPrzewagi(bet);

  return (
    <motion.article
      layout={!reduced}
      className="relative overflow-hidden rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card) transition-[border-color,box-shadow] duration-200 hover:border-brand/30 hover:shadow-(--shadow-card-hover)"
    >
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="group w-full text-left"
      >
        {/* wiersz główny: numer z koszulki · kto i co · szansa · kurs */}
        <span className="grid grid-cols-[1fr_auto] items-center gap-x-4 px-4 pb-3 pt-3.5 sm:grid-cols-[auto_1.4fr_1fr_auto] sm:px-5">
          {/* ghost-numer jak nadruk na koszulce – orientacja w rankingu bez
              kolejnego "pudełka"; przy hoverze nabiera koloru marki */}
          <span
            aria-hidden
            className="font-display hidden w-10 shrink-0 text-center text-[1.7rem] font-bold leading-none text-ink/15 transition-colors group-hover:text-brand/40 sm:block"
          >
            {rank}
          </span>

          <span className="min-w-0">
            <span className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
              {/* dioda formy: historia vs model jednym rzutem oka (zamiast
                  paska na krawędzi, który ginął przy zielonych miernikach) */}
              {/* bez dymka: dioda to skrót wykresu formy, który po rozwinięciu
                  stoi na karcie w całości (przegląd 2026-08-01) */}
              {swiatlo && (
                <span className="relative inline-flex h-2 w-2 shrink-0 translate-y-px items-center justify-center">
                  <span
                    aria-hidden
                    className={`absolute -inset-1 rounded-full opacity-20 ${SWIATLO_STYL[swiatlo].pasek}`}
                  />
                  <span
                    aria-hidden
                    className={`h-2 w-2 rounded-full ${SWIATLO_STYL[swiatlo].pasek}`}
                  />
                </span>
              )}
              <span role="heading" aria-level={3} className="truncate font-semibold">
                {nazwaPodmiotu(bet)}
              </span>
              <span className="text-sm text-muted">{opisZakladu(bet)}</span>
            </span>
            <span className="mt-1 block truncate text-xs text-faint">
              {bet.mecz} · {fmtDataCzas(bet.kickoff_ts)}
            </span>
            {/* pasek szansy na mobile – pod nazwą, żeby triage działał też kciukiem */}
            <span className="mt-2 block max-w-56 sm:hidden">
              <ChanceBar
                p={bet.p_model}
                line={bet.linia}
                side={stronaLinii(bet.strona)}
                opis={opisZakladu(bet)}
              />
            </span>
          </span>

          <span className="hidden min-w-0 items-center sm:flex">
            <span className="w-full max-w-48">
              <ChanceBar
                p={bet.p_model}
                line={bet.linia}
                side={stronaLinii(bet.strona)}
                opis={opisZakladu(bet)}
              />
            </span>
          </span>

          {/* rubryka kursu za gradientową linią – liczba, nie przycisk;
              bez kursu: od jakiego kursu w STS typ jest wart zagrania */}
          <span
            className="relative flex flex-col items-end justify-center gap-1 self-stretch justify-self-end pl-5 sm:pl-6"
            title={
              bet.kurs == null
                ? `Otwórz STS i porównaj: kurs ~${fmtKurs(bet.fair_kurs * 1.05)} lub wyższy = warto grać, niższy = odpuść`
                : undefined
            }
          >
            <span
              aria-hidden
              className="absolute inset-y-0 left-0 hidden w-px bg-gradient-to-b from-transparent via-hairline-strong to-transparent sm:block"
            />
            <span className="font-data text-xl font-semibold leading-none tracking-tight">
              {bet.kurs != null ? fmtKurs(bet.kurs) : `~${fmtKurs(bet.fair_kurs * 1.05)}`}
            </span>
            <span className="text-[9px] uppercase tracking-wide text-faint">
              {bet.kurs != null ? bet.bukmacher : "dobry kurs od"}
            </span>
          </span>
        </span>

        {/* linia meta: ocena typu + odznaki przewagi + pewność + detale –
            bez własnego pudełka, wcięta do kolumny nazwiska */}
        <span className="flex flex-wrap items-center gap-x-1.5 gap-y-1.5 px-4 pb-3.5 sm:pl-[4.75rem] sm:pr-5">
          {/* KATEGORIA TYPU, NIE PROCENT WARTOŚCI (2026-08-13). Stała tu
              odznaka z wartością netto – zawsze na zielonym tle, także gdy
              liczba była ujemna. Odkąd karta pokazuje szansę ściągniętą do
              uczciwej ceny, ta wartość jest ujemna przy każdym typie i mówi
              o marży bukmachera, nie o typie. Wszystkie typy z kursem
              dostają więc tę samą etykietę co pewniaki – kategorię. */}
          {bet.sugestia || bet.kurs == null ? (
            <span className="inline-flex items-center rounded-full bg-data-amber-wash px-2.5 py-0.5 text-xs font-semibold text-data-amber-ink">
              sprawdź w STS
            </span>
          ) : (
            (() => {
              const t = tierTypu(bet);
              return (
                <span
                  className={`font-data inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${t.cls}`}
                >
                  {t.label}
                </span>
              );
            })()
          )}
          {/* odznaki przewagi – tekstowe odczyty HUD zamiast kolejnych
              chipów; jedno źródło prawdy (odznakiPrzewagi) */}
          {/* BEZ DYMKA: pełne wyjaśnienie każdej odznaki jest w rozwinięciu
              (komponent Sygnaly, opis na stronie i na klik). Dymek dublował
              tę treść tam, gdzie na telefonie i tak jej nie widać. */}
          {odznaki.map((o) => (
            <span
              key={o.label}
              className={`inline-flex items-center gap-1 px-1 text-[11px] font-medium ${
                o.tone === "brand" ? "text-brand-deep" : "text-data-amber-ink"
              }`}
            >
              <span aria-hidden className="font-data">{o.znak}</span> {o.label}
            </span>
          ))}
          <span className="ml-auto flex items-center gap-3">
            <span className="flex items-center gap-1 text-[10px] text-faint">
              <PewnoscDots level={bet.pewnosc} />
              {PEWNOSC_LABEL[bet.pewnosc]} pewność
            </span>
            <span className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-faint">
              {open ? "zwiń" : "skąd ta liczba"}
              <svg
                aria-hidden
                width="12"
                height="12"
                viewBox="0 0 14 14"
                className={`transition-transform ${open ? "rotate-180" : ""}`}
              >
                <path
                  d="M3 5.5 L7 9.5 L11 5.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
          </span>
        </span>
      </button>

      {/* JEDNA KARTA ZAMIAST TRZECH: gdy ten sam typ ma kilka poprzeczek,
          wybór szczebla stoi tu, a rozwinięcie tłumaczy wybrany */}
      {warianty && warianty.length > 1 && (
        <DrabinkaLinii
          warianty={warianty}
          wybrany={bet.id}
          onWybor={setWybranyId}
        />
      )}

      <SzczegolyTypu bet={bet} forma={forma} open={open} />
    </motion.article>
  );
});
