/**
 * Poziomy układ logo złożony z JEDNEGO pliku marki (pionowe logo 1254×443):
 * znak (piłka z wykresem) i napis wycinamy tłem z tego samego obrazka
 * i stawiamy obok siebie. Pionowe logo w pasku 56 px dawało napis wielkości
 * przypisu – tak znak i nazwa mają czytelny rozmiar, a plik się nie zmienia.
 */

const W = 1254;
const H = 443;
// kadry w pikselach pliku źródłowego
const ZNAK = { x: 481, y: 8, w: 320, h: 264 };
const NAPIS = { x: 169, y: 300, w: 948, h: 134 };

function Kadr({
  src,
  kadr,
  wysokosc,
}: {
  src: string;
  kadr: { x: number; y: number; w: number; h: number };
  wysokosc: number;
}) {
  const s = wysokosc / kadr.h;
  return (
    <span
      aria-hidden
      style={{
        display: "block",
        width: Math.round(kadr.w * s),
        height: wysokosc,
        backgroundImage: `url(${src})`,
        backgroundSize: `${W * s}px ${H * s}px`,
        backgroundPosition: `${-kadr.x * s}px ${-kadr.y * s}px`,
        backgroundRepeat: "no-repeat",
      }}
    />
  );
}

export function LogoPoziome({ jasne, wysokosc = 26 }: { jasne: boolean; wysokosc?: number }) {
  const src = jasne ? "/logo-dark.png" : "/logo-light.png";
  return (
    <span role="img" aria-label="FootStats" style={{ display: "inline-flex", alignItems: "center", gap: 8, flex: "none" }}>
      <Kadr src={src} kadr={ZNAK} wysokosc={wysokosc} />
      <Kadr src={src} kadr={NAPIS} wysokosc={Math.round(wysokosc * 0.66)} />
    </span>
  );
}

/** sam napis „FootStats” z logo – do animowanego logo (znak rysujemy wektorowo) */
export function NapisLogo({ jasne, wysokosc = 18 }: { jasne: boolean; wysokosc?: number }) {
  return <Kadr src={jasne ? "/logo-dark.png" : "/logo-light.png"} kadr={NAPIS} wysokosc={wysokosc} />;
}
