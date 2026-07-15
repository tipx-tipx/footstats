"use client";

import { motion, useReducedMotion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Logo } from "@/components/Logo";

export default function LoginPage() {
  const [haslo, setHaslo] = useState("");
  const [pokaz, setPokaz] = useState(false);
  const [blad, setBlad] = useState(false);
  const [wysylanie, setWysylanie] = useState(false);
  const router = useRouter();
  const reduced = useReducedMotion();

  async function zaloguj(e: React.FormEvent) {
    e.preventDefault();
    if (!haslo || wysylanie) return;
    setWysylanie(true);
    setBlad(false);
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ haslo }),
    }).catch(() => null);
    if (res?.ok) {
      router.replace("/");
      router.refresh();
      return;
    }
    setBlad(true);
    setWysylanie(false);
  }

  return (
    <main className="pitch-grid relative flex min-h-dvh w-full items-center justify-center overflow-hidden px-4">
      {/* poświata marki za kartą */}
      <div
        aria-hidden
        className="glow-brand pointer-events-none absolute left-1/2 top-1/2 h-[36rem] w-[36rem] -translate-x-1/2 -translate-y-1/2"
      />
      <motion.div
        initial={{ opacity: 0, y: 16, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="relative w-full max-w-sm"
      >
        <motion.div
          animate={blad && !reduced ? { x: [0, -8, 8, -5, 5, 0] } : {}}
          transition={{ duration: 0.4 }}
          className="rounded-(--radius-card) border border-hairline bg-card p-8 shadow-(--shadow-pop)"
        >
          <div className="flex flex-col items-center text-center">
            <Logo className="h-20 w-auto" />
            <p className="mt-4 text-[11px] font-semibold uppercase tracking-widest text-brand">
              narzędzie prywatne
            </p>
            <h1 className="mt-1 text-base font-semibold text-ink-soft">
              Podaj hasło, żeby wejść
            </h1>
          </div>

          <form onSubmit={zaloguj} className="mt-6 space-y-3">
            <label className="block">
              <span className="sr-only">Hasło</span>
              <span className="relative block">
                <input
                  type={pokaz ? "text" : "password"}
                  value={haslo}
                  onChange={(e) => {
                    setHaslo(e.target.value);
                    setBlad(false);
                  }}
                  autoFocus
                  autoComplete="current-password"
                  placeholder="Hasło"
                  className={`w-full rounded-xl border bg-paper px-4 py-3 pr-12 text-sm text-ink outline-none transition-colors placeholder:text-faint focus:border-brand ${
                    blad ? "border-data-red" : "border-hairline"
                  }`}
                />
                <button
                  type="button"
                  onClick={() => setPokaz((p) => !p)}
                  aria-label={pokaz ? "Ukryj hasło" : "Pokaż hasło"}
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-lg p-2.5 text-faint transition-colors hover:text-ink"
                >
                  {pokaz ? (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
                      <path d="M3 3l18 18M10.6 5.1A9.8 9.8 0 0 1 12 5c7 0 10 7 10 7a17 17 0 0 1-3.2 4.2M6.6 6.6A16.6 16.6 0 0 0 2 12s3 7 10 7c1.8 0 3.4-.5 4.7-1.2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  ) : (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
                      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" strokeLinejoin="round" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </span>
            </label>

            {blad && (
              <p role="alert" className="text-center text-xs font-medium text-data-red">
                Nieprawidłowe hasło, spróbuj ponownie.
              </p>
            )}

            <button
              type="submit"
              disabled={wysylanie || !haslo}
              className="w-full rounded-(--radius-control) bg-brand px-4 py-3 text-sm font-semibold text-on-brand shadow-(--shadow-card) transition-all hover:bg-brand-strong disabled:cursor-not-allowed disabled:bg-card-soft disabled:text-faint disabled:shadow-none"
            >
              {wysylanie ? "Sprawdzam…" : "Wejdź"}
            </button>
          </form>
        </motion.div>
      </motion.div>
    </main>
  );
}
