"use client";

import { usePathname } from "next/navigation";

/**
 * Kontener treści: zwykłe strony dostają wyśrodkowaną kolumnę,
 * ekran logowania — pełną szerokość i wysokość (tło na cały ekran).
 */
export function MainShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/login") {
    return <div className="flex-1">{children}</div>;
  }
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-24 sm:px-6">
      {children}
    </main>
  );
}
