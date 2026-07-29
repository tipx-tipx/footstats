"use client";

import { fmtProc } from "@/lib/format";
import type { Strumien, UczenieStrumienia } from "@/lib/types";

/**
 * CZY MODEL ROBI POSTĘPY — paczki po 40 rozliczeń, jedna pod drugą.
 *
 * Pytanie „czy to się w ogóle poprawia" padało co kilka dni i za każdym razem
 * odpowiedź wymagała ręcznego przeliczenia księgi. Teraz liczy to pipeline
 * (rozliczanie.raport_uczenia), a tu jest tylko widok.
 *
 * Wiersz to STAŁA LICZBA ROZLICZEŃ, nie tydzień. Tydzień bywa raz na 3 typy,
 * raz na 90 — porównanie wiersz do wiersza mówiłoby wtedy o kalendarzu
 * rozgrywek, nie o modelu.
 *
 * Kolumna, o którą w tym wszystkim chodzi, to RÓŻNICA: ile model obiecywał
 * minus ile weszło. Jeśli model się uczy, ta liczba pełznie do zera.
 * Jeśli stoi w miejscu przez kilka paczek — deklaracja jest ozdobą.
 */

const NAZWY: Record<Strumien, string> = {
  pewniaki: "Zawodnicy",
  druzyny: "Drużyny",
  drabinki: "Drabinki",
};

/** "2026-07-03" → "3 lip" (bez roku — wszystkie paczki są z tego sezonu). */
function krotkaData(d: string): string {
  return new Intl.DateTimeFormat("pl-PL", {
    day: "numeric",
    month: "short",
  }).format(new Date(`${d}T12:00:00`));
}

/** Zwrot ze stawki przełożony na złotówki: −0,177 → „z 10 zł zostaje 8,23 zł". */
function zDziesieciu(roi: number): string {
  const zl = 10 * (1 + roi);
  return `${zl.toFixed(2).replace(".", ",")} zł`;
}

/**
 * Luka to RÓŻNICA dwóch procentów, więc jednostką są punkty procentowe.
 * „Model myli się o 20%" i „o 20 pp" to dwie różne rzeczy — pierwsze brzmi
 * jak jedna piąta deklaracji, drugie mówi, ile realnie brakuje trafień.
 */
function pp(luka: number): string {
  return `${Math.abs(luka * 100).toFixed(0)} pp`;
}

function Werdykt({ t }: { t: NonNullable<UczenieStrumienia["trend"]> }) {
  // zmiana > 0 znaczy, że luka zbliżyła się do zera — czyli postęp
  const lepiej = t.zmiana > 0.02;
  const gorzej = t.zmiana < -0.02;
  return (
    <p
      className={`rounded-(--radius-card) border px-4 py-3 text-sm leading-relaxed ${
        lepiej
          ? "border-data-green/40 bg-data-green/5 text-ink"
          : gorzej
            ? "border-data-red/40 bg-data-red/5 text-ink"
            : "border-hairline bg-card text-ink"
      }`}
    >
      {lepiej ? (
        <>
          <strong className="font-semibold">To idzie w dobrą stronę.</strong> Na
          starcie na sto typów brakowało {pp(t.luka_start)} trafień, w ostatnich
          paczkach {pp(t.luka_teraz)}.
        </>
      ) : gorzej ? (
        <>
          <strong className="font-semibold">
            Model NIE robi postępów — jest gorzej.
          </strong>{" "}
          Na starcie na sto typów brakowało {pp(t.luka_start)} trafień do tego,
          co obiecywał; w ostatnich paczkach {pp(t.luka_teraz)}.
        </>
      ) : (
        <>
          <strong className="font-semibold">Stoi w miejscu.</strong> Model myli
          się o mniej więcej tyle samo co na starcie ({pp(t.luka_start)} →{" "}
          {pp(t.luka_teraz)}).
        </>
      )}{" "}
      <span className="text-muted">
        Liczone z {t.paczek} pełnych paczek: trzy pierwsze wobec trzech
        ostatnich.
      </span>
    </p>
  );
}

function Tabela({ u }: { u: UczenieStrumienia }) {
  return (
    <div className="overflow-x-auto rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card)">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-hairline bg-card-soft text-left text-[11px] uppercase tracking-wide text-faint">
            <th className="px-3 py-2.5 font-medium sm:px-4">mecze</th>
            <th className="px-3 py-2.5 font-medium sm:px-4">weszło</th>
            <th className="hidden px-3 py-2.5 font-medium sm:table-cell sm:px-4">
              obiecywał
            </th>
            <th className="px-3 py-2.5 font-medium sm:px-4">różnica</th>
            {/* na telefonie sam „z 10 zł" — pełny nagłówek rozpychał tabelę
                poza szerokość ekranu (audyt: 416 px w kontenerze 356 px) */}
            <th
              className="px-3 py-2.5 font-medium sm:px-4"
              title="Ile zostaje ze stawki 10 zł na typ"
            >
              z 10 zł<span className="hidden sm:inline"> zostaje</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {u.paczki.map((p) => (
            <tr
              key={`${p.od}-${p.do}-${p.n}`}
              className={`even:bg-card-soft ${p.pelna ? "" : "text-faint"}`}
              title={
                p.pelna
                  ? undefined
                  : `Paczka jeszcze rośnie (${p.n} rozliczeń) — te liczby będą się zmieniać`
              }
            >
              <td className="px-3 py-2.5 whitespace-nowrap sm:px-4">
                {krotkaData(p.od)}
                <span className="text-faint">–</span>
                {krotkaData(p.do)}
                {!p.pelna && (
                  <span className="ml-2 text-[10px] uppercase tracking-wide text-faint">
                    trwa
                  </span>
                )}
              </td>
              <td className="font-data px-3 py-2.5 whitespace-nowrap sm:px-4">
                {p.trafione}/{p.n}
                {/* procent to ta sama informacja co ułamek obok — na wąskim
                    ekranie oddaje miejsce kolumnie, której nie da się policzyć
                    w głowie */}
                <span className="ml-2 hidden text-muted sm:inline">
                  {fmtProc(p.hit)}
                </span>
              </td>
              <td className="font-data hidden px-3 py-2.5 text-muted sm:table-cell sm:px-4">
                {fmtProc(p.deklaracja)}
              </td>
              <td
                className={`font-data px-3 py-2.5 font-semibold whitespace-nowrap sm:px-4 ${
                  !p.pelna
                    ? ""
                    : p.luka >= 0
                      ? "text-data-green"
                      : p.luka < -0.1
                        ? "text-data-red"
                        : "text-data-amber-ink"
                }`}
              >
                {p.luka >= 0 ? "+" : "−"}
                {Math.abs(p.luka * 100).toFixed(0)} pp
              </td>
              <td
                className={`font-data px-3 py-2.5 whitespace-nowrap sm:px-4 ${
                  !p.pelna || p.roi == null
                    ? ""
                    : p.roi >= 0
                      ? "text-data-green"
                      : "text-data-red"
                }`}
              >
                {p.roi == null ? "—" : zDziesieciu(p.roi)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RaportUczenia({
  raport,
  strumienie,
}: {
  raport: Partial<Record<Strumien, UczenieStrumienia>>;
  /** które produkty pokazać — filtr ze strony obowiązuje i tutaj */
  strumienie: Strumien[];
}) {
  const widoczne = strumienie.filter((k) => (raport[k]?.paczki.length ?? 0) > 0);
  if (widoczne.length === 0) {
    return (
      <p className="rounded-(--radius-card) border border-hairline bg-card px-4 py-3.5 text-sm text-muted shadow-(--shadow-card)">
        Za mało rozliczeń, żeby cokolwiek powiedzieć o postępach.
      </p>
    );
  }
  return (
    <div className="max-w-3xl space-y-6">
      <p className="max-w-prose text-sm leading-relaxed text-muted">
        Każdy wiersz to{" "}
        <strong className="font-semibold">
          kolejne 40 rozliczonych typów
        </strong>{" "}
        — nie tydzień, bo tydzień bywa raz na trzy typy, a raz na dziewięćdziesiąt.
        Kolumna <strong className="font-semibold">różnica</strong> mówi, o ile
        model się pomylił: na minusie był zbyt pewny siebie. Jeśli się uczy, ta
        liczba z wiersza na wiersz zbliża się do zera.
      </p>
      {widoczne.map((k) => {
        const u = raport[k]!;
        return (
          <section key={k} className="space-y-3">
            {strumienie.length > 1 && (
              <h3 className="text-sm font-semibold text-ink">{NAZWY[k]}</h3>
            )}
            {u.trend ? (
              <Werdykt t={u.trend} />
            ) : (
              <p className="rounded-(--radius-card) border border-hairline bg-card px-4 py-3 text-sm text-muted">
                Za mało pełnych paczek na wniosek o kierunku — potrzeba sześciu,
                żeby porównać początek z końcem.
              </p>
            )}
            <Tabela u={u} />
          </section>
        );
      })}
    </div>
  );
}
