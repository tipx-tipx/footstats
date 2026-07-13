/**
 * Kontener treści: wyśrodkowana kolumna. Renderowany WYŁĄCZNIE w
 * app/(app)/layout.tsx — /login żyje poza tą grupą tras i tego nie widzi,
 * więc nie trzeba już w czasie działania sprawdzać pathname (server component).
 */
export function MainShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-24 sm:px-6">
      {children}
    </main>
  );
}
