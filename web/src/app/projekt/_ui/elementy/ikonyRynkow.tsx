/**
 * Ikony rynków – język z boiska, nie z biblioteki ikon: bramka z siatką,
 * cel, gwizdek, chorągiewka rożna, kartka, chorągiewka sędziego liniowego.
 * Rysowane jedną kreską 1,5 px w siatce 16 px, żeby stały obok tekstu 13–15 px.
 */

const WSPOLNE = { fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

function Bramka() {
  return (
    <>
      <path d="M2 13V4h12v9" {...WSPOLNE} />
      <path d="M2 7h12M2 10h12M6 4v9M10 4v9" {...WSPOLNE} strokeWidth={0.8} opacity={0.6} />
    </>
  );
}

function Cel({ celny }: { celny?: boolean }) {
  return (
    <>
      <circle cx="8" cy="8" r="5.5" {...WSPOLNE} />
      <circle cx="8" cy="8" r="2.5" {...WSPOLNE} />
      {celny && <circle cx="8" cy="8" r="0.9" fill="currentColor" />}
    </>
  );
}

function Gwizdek() {
  return (
    <>
      <path d="M2.5 7.5h6.5a3.5 3.5 0 1 1-3.3 4.7L2.5 11Z" {...WSPOLNE} />
      <path d="M9 7.5V5.5h4" {...WSPOLNE} />
    </>
  );
}

function Rozny() {
  return (
    <>
      <path d="M4 14V2.5l7 2.5-7 2.5" {...WSPOLNE} />
      <path d="M8.5 14a4.5 4.5 0 0 0 4.5-4.5" {...WSPOLNE} />
    </>
  );
}

function Kartka() {
  return <rect x="4.5" y="2.5" width="7" height="11" rx="1.2" {...WSPOLNE} />;
}

function Spalony() {
  return (
    <>
      <path d="M4 14V2.5" {...WSPOLNE} />
      <path d="M4 3h8v5H4" {...WSPOLNE} />
      <path d="M4 5.5h8M8 3v5" {...WSPOLNE} strokeWidth={0.8} opacity={0.6} />
    </>
  );
}

function Odbior() {
  return (
    <>
      <circle cx="10.5" cy="10.5" r="3" {...WSPOLNE} />
      <path d="M2.5 13.5 7 9M2.5 9.5l2 2" {...WSPOLNE} />
    </>
  );
}

/** rynek (nazwa po polsku z danych) -> ikona */
export function IkonaRynku({ rynek, rozmiar = 16 }: { rynek: string; rozmiar?: number }) {
  const r = rynek.toLowerCase();
  let rys = <Cel />;
  if (r.includes("gol")) rys = <Bramka />;
  else if (r.includes("celne")) rys = <Cel celny />;
  else if (r.includes("strza")) rys = <Cel />;
  else if (r.includes("faul")) rys = <Gwizdek />;
  else if (r.includes("roż") || r.includes("roz")) rys = <Rozny />;
  else if (r.includes("kart")) rys = <Kartka />;
  else if (r.includes("spalon")) rys = <Spalony />;
  else if (r.includes("odbi")) rys = <Odbior />;
  return (
    <svg width={rozmiar} height={rozmiar} viewBox="0 0 16 16" aria-hidden style={{ flex: "none" }}>
      {rys}
    </svg>
  );
}
