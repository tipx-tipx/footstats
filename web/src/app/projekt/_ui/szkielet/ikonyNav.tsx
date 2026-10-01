/**
 * Ikony menu – ta sama kreska 1,5 px w siatce 20 px co ikony rynków.
 * Wariant `pelna` (aktywna pozycja) wypełnia kształt, zamiast zmieniać kolor
 * samej kreski – na dolnym pasku telefonu to czytelniejsze niż kolor.
 */

const K = { fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

export type KluczNav = "zawodnicy" | "druzyny" | "kupony" | "mecze" | "skutecznosc" | "jak" | "wiecej";

export function IkonaNav({ klucz, pelna = false, rozmiar = 20 }: { klucz: KluczNav; pelna?: boolean; rozmiar?: number }) {
  const wyp = pelna ? "currentColor" : "none";
  let rys;
  switch (klucz) {
    case "zawodnicy": // koszulka
      rys = <path d="M7 3 3.2 5.2l1.4 3.6 1.9-.8V17h7V8l1.9.8 1.4-3.6L13 3c-.3 1.3-1.4 2-3 2S7.3 4.3 7 3Z" {...K} fill={pelna ? "currentColor" : "none"} fillOpacity={pelna ? 0.22 : 0} />;
      break;
    case "druzyny": // tarcza
      rys = <path d="M10 2.5 16 4.6v5.2c0 3.8-2.5 6.5-6 7.8-3.5-1.3-6-4-6-7.8V4.6Z" {...K} fill={pelna ? "currentColor" : "none"} fillOpacity={pelna ? 0.22 : 0} />;
      break;
    case "kupony": // bilet z wycięciem
      rys = (
        <>
          <path d="M3 6.5V4.8c0-.4.4-.8.8-.8h12.4c.4 0 .8.4.8.8v1.7a2.5 2.5 0 0 0 0 5v1.7c0 .4-.4.8-.8.8H3.8c-.4 0-.8-.4-.8-.8v-1.7a2.5 2.5 0 0 0 0-5Z" {...K} fill={pelna ? "currentColor" : "none"} fillOpacity={pelna ? 0.22 : 0} />
          <path d="M12 5.5v1.2M12 8.4v1.2M12 11.3v1.2" {...K} />
        </>
      );
      break;
    case "mecze": // boisko
      rys = (
        <>
          <rect x="2.5" y="4" width="15" height="12" rx="1.5" {...K} fill={pelna ? "currentColor" : "none"} fillOpacity={pelna ? 0.22 : 0} />
          <path d="M10 4v12" {...K} />
          <circle cx="10" cy="10" r="2.2" {...K} />
        </>
      );
      break;
    case "skutecznosc": // słupki z kropką trafienia
      rys = (
        <>
          <path d="M4 16V11M8.5 16V7.5M13 16v-5.5M3 16.5h14" {...K} />
          <circle cx="15.5" cy="5" r="1.8" fill={wyp === "none" ? "none" : "currentColor"} stroke="currentColor" strokeWidth={1.5} />
        </>
      );
      break;
    case "jak": // znak zapytania w kole
      rys = (
        <>
          <circle cx="10" cy="10" r="7.2" {...K} fill={pelna ? "currentColor" : "none"} fillOpacity={pelna ? 0.22 : 0} />
          <path d="M8 8a2 2 0 1 1 2.7 1.9c-.5.2-.7.6-.7 1.1v.5" {...K} />
          <circle cx="10" cy="13.8" r=".6" fill="currentColor" />
        </>
      );
      break;
    default: // więcej
      rys = (
        <>
          <circle cx="5" cy="10" r="1.4" fill="currentColor" />
          <circle cx="10" cy="10" r="1.4" fill="currentColor" />
          <circle cx="15" cy="10" r="1.4" fill="currentColor" />
        </>
      );
  }
  return (
    <svg width={rozmiar} height={rozmiar} viewBox="0 0 20 20" aria-hidden style={{ flex: "none" }}>
      {rys}
    </svg>
  );
}

export function IkonaSzukaj({ r = 16 }: { r?: number }) {
  return (
    <svg width={r} height={r} viewBox="0 0 16 16" aria-hidden>
      <circle cx="7" cy="7" r="4.8" {...K} />
      <path d="m10.6 10.6 3.4 3.4" {...K} />
    </svg>
  );
}

export function IkonaMotyw({ ciemny, r = 18 }: { ciemny: boolean; r?: number }) {
  return ciemny ? (
    <svg width={r} height={r} viewBox="0 0 18 18" aria-hidden>
      <path d="M14.5 11.3A6 6 0 0 1 6.7 3.5a6 6 0 1 0 7.8 7.8Z" {...K} />
    </svg>
  ) : (
    <svg width={r} height={r} viewBox="0 0 18 18" aria-hidden>
      <circle cx="9" cy="9" r="3.2" {...K} />
      <path d="M9 1.8v1.6M9 14.6v1.6M1.8 9h1.6M14.6 9h1.6M3.9 3.9l1.1 1.1M13 13l1.1 1.1M3.9 14.1 5 13M13 5l1.1-1.1" {...K} />
    </svg>
  );
}

export function IkonaWyloguj({ r = 18 }: { r?: number }) {
  return (
    <svg width={r} height={r} viewBox="0 0 18 18" aria-hidden>
      <path d="M7 3H4.2c-.7 0-1.2.5-1.2 1.2v9.6c0 .7.5 1.2 1.2 1.2H7M12 12.5 15.5 9 12 5.5M15.5 9H7" {...K} />
    </svg>
  );
}
