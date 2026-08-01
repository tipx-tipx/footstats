"use client";

import Link from "next/link";

/**
 * „Pokaż jak widzi klient" – tylko dla admina.
 *
 * Bez tego przygotowanie strony pod sprzedaż jest zgadywanką: trzeba by się
 * wylogować, żeby zobaczyć własny produkt. Przełącznik chodzi po adresie
 * (`?widok=klient`), a nie po stanie w przeglądarce, więc widok da się
 * podesłać linkiem i renderuje się na serwerze tak samo jak u klienta.
 */
export function PrzelacznikWidoku({ podglad }: { podglad: boolean }) {
  return (
    <div className="mb-5 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-(--radius-card) border border-dashed border-hairline-strong bg-card-soft/60 px-4 py-2.5 text-xs">
      <span className="font-semibold uppercase tracking-widest text-faint">
        widok
      </span>
      <div className="flex gap-1">
        <Link
          href="/model"
          aria-current={!podglad ? "page" : undefined}
          className={`rounded-(--radius-control) px-2.5 py-1 transition-colors ${
            !podglad
              ? "bg-brand-wash font-semibold text-brand-deep"
              : "text-muted hover:text-ink"
          }`}
        >
          pełny
        </Link>
        <Link
          href="/model?widok=klient"
          aria-current={podglad ? "page" : undefined}
          className={`rounded-(--radius-control) px-2.5 py-1 transition-colors ${
            podglad
              ? "bg-brand-wash font-semibold text-brand-deep"
              : "text-muted hover:text-ink"
          }`}
        >
          jak widzi klient
        </Link>
      </div>
      <p className="text-muted">
        {podglad
          ? "Oglądasz to, co widzi klient: bez kuchni modelu, liczby w złotówkach."
          : "Widzisz komplet, razem z diagnostyką, której klient nie dostaje."}
      </p>
    </div>
  );
}
