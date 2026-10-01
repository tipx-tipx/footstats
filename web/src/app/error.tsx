"use client";

import { BladAplikacji } from "@/app/projekt/_ui/systemowe/SystemoweAplikacji";
import { SamoLogo } from "@/app/projekt/_ui/systemowe/SamoLogo";

/** błąd poza stronami (np. padło menu aplikacji) – sam znak marki i ta sama treść */
export default function BladGlowny({ error, unstable_retry }: { error: Error & { digest?: string }; unstable_retry: () => void }) {
  return (
    <SamoLogo>
      <BladAplikacji blad={error} digest={error.digest} ponow={unstable_retry} />
    </SamoLogo>
  );
}
