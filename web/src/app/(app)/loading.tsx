/**
 * Szkielet ładowania dla stron grupy (app). Strona główna jest dynamiczna
 * (searchParams), więc bez tego pliku klik w nawigację wisiał na starej
 * stronie bez ŻADNEJ reakcji, aż serwer skończył render — z nim przejście
 * jest natychmiastowe, a treść wjeżdża w miejsce szkieletu.
 */
export default function Loading() {
  return (
    <div aria-busy="true" aria-label="Wczytywanie" className="animate-pulse">
      {/* pas nagłówka sekcji */}
      <div className="mt-2 h-3 w-40 rounded bg-ink/10" />
      <div className="mt-4 h-9 w-72 max-w-full rounded bg-ink/10" />
      <div className="mt-3 h-4 w-96 max-w-full rounded bg-ink/5" />

      {/* rząd zakładek */}
      <div className="mt-10 flex gap-6 border-b border-hairline pb-3">
        <div className="h-3 w-16 rounded bg-ink/10" />
        <div className="h-3 w-20 rounded bg-ink/5" />
        <div className="h-3 w-16 rounded bg-ink/5" />
      </div>

      {/* karty listy */}
      <div className="mt-6 space-y-3">
        {[0, 1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="rounded-(--radius-card) border border-hairline bg-card px-5 py-4 shadow-(--shadow-card)"
          >
            <div className="flex items-center gap-3">
              <div className="h-2 w-2 rounded-full bg-ink/10" />
              <div className="h-4 w-44 max-w-[40%] rounded bg-ink/10" />
              <div className="ml-auto h-6 w-16 rounded bg-ink/5" />
            </div>
            <div className="mt-3 h-3 w-72 max-w-[70%] rounded bg-ink/5" />
          </div>
        ))}
      </div>
    </div>
  );
}
