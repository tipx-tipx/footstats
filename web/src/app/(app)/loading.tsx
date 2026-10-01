import { SzkieletStrony } from "@/app/projekt/_ui/systemowe/SzkieletStrony";

/**
 * Ładowanie stron grupy (app). Strony są dynamiczne, więc bez tego pliku klik
 * w menu wisiał na starej stronie bez reakcji, aż serwer skończył render.
 * Menu zostaje (layout), w treści szkielet z kości – dopiero po 300 ms.
 */
export default function Loading() {
  return <SzkieletStrony opozniony />;
}
