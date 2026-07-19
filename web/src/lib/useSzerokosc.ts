"use client";

import { useEffect, useRef, useState } from "react";

/** Zmierzona szerokość elementu (ResizeObserver) — 0 przed pierwszym pomiarem. */
export function useSzerokosc() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    setW(el.offsetWidth);
    const ro = new ResizeObserver((wpisy) => {
      const cw = wpisy[0]?.contentRect.width;
      if (cw) setW(cw);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, w };
}
