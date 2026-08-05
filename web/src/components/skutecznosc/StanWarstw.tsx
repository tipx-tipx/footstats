import type { Meta } from "@/lib/types";

/**
 * Stan warstw uczenia z ostatniego cyklu – panel wyłącznie dla admina.
 *
 * Po co: warstwa, która padła, do 05.08 wyglądała dokładnie tak samo jak
 * warstwa, która policzyła zero. Obie kończyły się pustym słownikiem i cichym
 * printem w logu GitHub Actions, a ten log znika po kilku dniach. Raz kosztowało
 * to półtorej doby uczenia (`korekta_strumienia`, 01.08) i nikt nie zauważył,
 * bo strona wyglądała normalnie – po prostu typów było mniej.
 *
 * Panel pokazuje trzy rzeczy naraz: czy warstwa w ogóle się uruchomiła,
 * na ilu rekordach liczyła i co konkretnie się wywaliło.
 */
export function StanWarstw({ stan }: { stan: Meta["uczenie_stan"] }) {
  const wpisy = Object.entries(stan ?? {});
  if (wpisy.length === 0) {
    return (
      <div className="rounded-(--radius-card) border border-hairline bg-card px-4 py-3.5 text-sm text-muted">
        <p className="text-[10px] uppercase tracking-wide text-faint">
          warstwy uczenia
        </p>
        <p className="mt-1.5">
          Brak pomiaru – ostatni cykl nie zapisał stanu warstw. Zwykle znaczy to,
          że strona jedzie na danych sprzed wdrożenia tego licznika.
        </p>
      </div>
    );
  }

  const padniete = wpisy.filter(([, w]) => !w.ok);

  return (
    <div className="rounded-(--radius-card) border border-hairline bg-card px-4 py-3.5">
      <p className="text-[10px] uppercase tracking-wide text-faint">
        warstwy uczenia w ostatnim cyklu
      </p>
      <p className="mt-1.5 text-sm">
        {padniete.length === 0 ? (
          <>
            Działa <strong>{wpisy.length} z {wpisy.length}</strong>. Każda
            policzyła swoją poprawkę na danych z rozliczeń.
          </>
        ) : (
          <>
            <strong className="text-data-red-ink">
              Padło {padniete.length} z {wpisy.length}
            </strong>{" "}
            – te poprawki nie zostały policzone, więc model jechał na
            wartościach domyślnych.
          </>
        )}
      </p>

      <ul className="mt-3 space-y-2.5">
        {wpisy.map(([nazwa, w]) => (
          <li key={nazwa} className="flex gap-2 text-sm">
            <span
              aria-hidden
              className={`mt-2 inline-block size-1.5 shrink-0 rounded-full ${
                w.ok ? "bg-data-green" : "bg-data-red"
              }`}
            />
            <div className="min-w-0">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-medium">{NAZWY[nazwa] ?? nazwa}</span>
                {/* BEZ PRZYIMKA „z". Polski wymaga po nim dopełniacza
                    („z 3 rynków"), a odmiana liczebnika daje mianownik
                    („3 rynki") – sama liczba z rzeczownikiem jest poprawna
                    w każdym przypadku, więc nie kombinujemy z fleksją. */}
                {w.n !== null && w.n !== undefined && (
                  <span className="text-muted">{odmien(w.n, w.jednostka)}</span>
                )}
                {w.krytyczna && (
                  <span className="rounded-(--radius-control) bg-paper px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-faint">
                    bez niej nie publikujemy
                  </span>
                )}
              </div>
              {(w.blad ?? w.opis) && (
                <p
                  className={`mt-0.5 break-words text-[13px] ${
                    w.ok ? "text-faint" : "text-data-red-ink"
                  }`}
                >
                  {w.blad ?? w.opis}
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Odmiana liczebnika. Jednostkę podaje BACKEND (`rozliczanie.JEDNOSTKI_WARSTW`),
 * bo `n` znaczy co innego w każdej warstwie: korekta strumienia liczy
 * rozliczenia, kwarantanna rynków – rynki, wagi zaufania – kubełki pewności.
 * Wcześniej panel podpisywał każdą liczbę słowem „rozliczeń" i przez to
 * podawał nieprawdę przy siedmiu warstwach z dziewięciu.
 */
function odmien(n: number, formy?: string[]): string {
  if (!formy || formy.length !== 3) return String(n);
  const [jeden, kilka, wielu] = formy;
  const abs = Math.abs(Math.trunc(n));
  if (abs === 1) return `${abs} ${jeden}`;
  const r10 = abs % 10;
  const r100 = abs % 100;
  if (r10 >= 2 && r10 <= 4 && !(r100 >= 12 && r100 <= 14)) {
    return `${abs} ${kilka}`;
  }
  return `${abs} ${wielu}`;
}

/**
 * Nazwy po ludzku. Kod warstwy jest dla nas, ale panel czyta się szybciej,
 * gdy widać, CO dana warstwa poprawia.
 */
const NAZWY: Record<string, string> = {
  korekta_strumienia: "Poprawka szansy przed bramą",
  szansa_pokazywana: "Szansa pokazywana na stronie",
  kwarantanna_rynkow: "Wstrzymane rynki",
  kwarantanna_kategorii: "Wstrzymane powody typowania",
  kwarantanna_stron: "Wstrzymane strony linii",
  przewaga_rynkow: "Czy bijemy kurs",
  waga_rynku: "Ile mieszać naszą liczbę z ceną",
  wagi_zaufania: "Zaufanie do modelu w kuponach",
  kalibracja_kuponow: "Urealnienie szansy kuponu",
};
