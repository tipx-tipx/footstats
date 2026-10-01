import "../../atomy2.css";
import "../../strony.css";

import { SzkieletWiersza } from "../atomy2/reszta";

/**
 * Szkielet strony z zatwierdzonych kości (2.9): nagłówek + wiersze typów
 * w dokładnym kształcie. Tło logowania (bez dzisiejszych typów w HTML)
 * i ładowanie stron aplikacji (widać dopiero po 300 ms – szybkie przejście
 * nie mruga szarymi paskami).
 */
export function SzkieletStrony({ wiersze = 6, opozniony = false }: { wiersze?: number; opozniony?: boolean }) {
  return (
    <main className="st-strona st-c" data-opozniony={opozniony || undefined} aria-hidden={!opozniony || undefined} aria-busy={opozniony || undefined} aria-label={opozniony ? "Wczytywanie" : undefined}>
      <div style={{ display: "grid", gap: 28, maxWidth: 760 }}>
        <div style={{ display: "grid", gap: 10 }}>
          <div className="d-kosc" style={{ width: 210, height: 26 }} />
          <div className="d-kosc" style={{ width: 320, maxWidth: "70%", height: 13 }} />
        </div>
        {Array.from({ length: wiersze }, (_, i) => (
          <SzkieletWiersza key={i} />
        ))}
      </div>
    </main>
  );
}
