"use client";

import Link from "next/link";
import { createContext, useContext } from "react";

/*
 * Linki w komponentach (etap 7). W warsztacie strony to podglądy – linki
 * zostają atrapami (<a> bez adresu, nic nie przeładowuje ramki). W aplikacji
 * <LinkiAplikacji> włącza prawdziwe przejścia (next/link).
 */

const LinkiContext = createContext(false);

export function LinkiAplikacji({ children }: { children: React.ReactNode }) {
  return <LinkiContext.Provider value>{children}</LinkiContext.Provider>;
}

type Props = Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & { href: string };

export function Lnk({ href, children, ...rest }: Props) {
  const aplikacja = useContext(LinkiContext);
  if (!aplikacja) return <a {...rest}>{children}</a>;
  return (
    <Link href={href} {...rest}>
      {children}
    </Link>
  );
}
