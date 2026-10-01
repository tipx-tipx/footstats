/* 2.9 kość wiersza – osobny plik: ładuje się pod logowaniem i przy ładowaniu stron, bez reszty atomów */

/** te same wymiary co WierszTypu – po doczytaniu nic nie skacze */
export function SzkieletWiersza() {
  return (
    <div style={{ display: "grid", gap: 12 }} aria-hidden>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", alignItems: "center", gap: 16 }}>
        <div style={{ display: "grid", gap: 7 }}>
          <div className="d-kosc" style={{ width: "42%", height: 15 }} />
          <div className="d-kosc" style={{ width: "58%", height: 12 }} />
        </div>
        <div className="d-kosc" style={{ width: 132, height: 40, borderRadius: 8 }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <div className="d-kosc" style={{ width: 70, height: 18 }} />
        <div className="d-kosc" style={{ width: 90, height: 12 }} />
      </div>
      <div style={{ display: "flex", gap: 4 }}>
        {Array.from({ length: 10 }, (_, i) => (
          <div key={i} className="d-kosc" style={{ width: 30, height: 30, borderRadius: 7 }} />
        ))}
      </div>
      <div style={{ height: 14 }} />
    </div>
  );
}
