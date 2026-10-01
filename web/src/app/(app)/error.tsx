"use client";

import { BladAplikacji } from "@/app/projekt/_ui/systemowe/SystemoweAplikacji";

/** błąd strony – menu aplikacji zostaje, treść zastępuje „Spróbuj ponownie” */
export default function Blad({ error, unstable_retry }: { error: Error & { digest?: string }; unstable_retry: () => void }) {
  return <BladAplikacji blad={error} digest={error.digest} ponow={unstable_retry} />;
}
