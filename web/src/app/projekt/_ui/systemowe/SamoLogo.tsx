"use client";

import Link from "next/link";

import "../../szkielet.css";

import { LogoPoziome } from "../LogoPoziome";
import { useCiemny } from "../motyw";

/** strona systemowa bez menu aplikacji: sam znak marki u góry, prowadzi na start */
export function SamoLogo({ children }: { children: React.ReactNode }) {
  const ciemny = useCiemny();
  return (
    <div className="nowa ap-samo">
      <header className="ap-samo-glowa">
        <Link href="/" aria-label="FootStats – strona główna">
          <LogoPoziome jasne={ciemny} wysokosc={26} />
        </Link>
      </header>
      {children}
    </div>
  );
}
