import { notFound } from "next/navigation";

import { StronaAplikacji } from "@/app/projekt/_ui/aplikacja/Strona";
import { przygotujStrony } from "@/app/projekt/_dane/strony";
import { przygotujZawodnika } from "@/app/projekt/_dane/zawodnik";
import { zDanymi, type Surowe } from "@/app/projekt/_dane/zrodlo";
import { getOddsSuperbet, getZawodnikLekki } from "@/lib/data";
import type { Mecz, ValueBet } from "@/lib/types";
import { pobierzSurowe, zKadramiMeczu } from "@/lib/nowe/surowe";
import { czyTelefon } from "@/lib/nowe/telefon";

/**
 * Strona zawodnika (redesign, etap 7.3; 5.7 A zatwierdzone 01.10): jeden
 * zawodnik × wszystkie jego rynki, jego typy, historia naszych typów na niego.
 *
 * 7B: zawodnik z lekkiego koszyka `zaw_kNN` (po numerze, 10 meczów, kursy obu
 * bukmacherów) – kilkadziesiąt KB zamiast dwóch koszyków całych drużyn.
 * Gdy koszyków jeszcze nie ma (pierwszy cykl po wdrożeniu, migracja 0009
 * niewklejona) – stara ścieżka: kadry meczu, w którym ma kurs albo typ.
 */
export default async function ZawodnikPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const zid = Number(id);
  if (!Number.isInteger(zid) || zid <= 0) notFound();
  const [surowe, telefon, lekki] = await Promise.all([pobierzSurowe(), czyTelefon(), getZawodnikLekki(zid)]);
  if (lekki === undefined) notFound();

  let zDanymiZawodnika: Surowe;
  if (lekki) {
    const mecz = (surowe.mecze as Mecz[]).find((m) => m.id === lekki.mecz_id);
    if (!mecz) notFound();
    const { kursy, ...zawodnik } = lekki;
    zDanymiZawodnika = {
      ...surowe,
      pokrycia: { mecze: [{ id: mecz.id, gosp: mecz.gospodarz, gosc: mecz.gosc, zawodnicy: [zawodnik], kursy: { [String(zid)]: kursy } }] },
    };
  } else {
    const kursy = await getOddsSuperbet();
    const meczId =
      Number(Object.entries(kursy ?? {}).find(([, zaw]) => zaw[String(zid)])?.[0]) ||
      (surowe.typy as ValueBet[]).find((t) => t.podmiot_typ !== "druzyna" && t.podmiot_id === zid)?.mecz_id;
    const mecz = (surowe.mecze as Mecz[]).find((m) => m.id === meczId);
    if (!mecz) notFound();
    zDanymiZawodnika = await zKadramiMeczu(surowe, mecz);
  }
  const [dane, zawodnik] = zDanymi(zDanymiZawodnika, () => [przygotujStrony(), przygotujZawodnika(zid)] as const);
  if (!zawodnik) notFound();
  return <StronaAplikacji strona="zawodnik" dane={dane} zawodnik={zawodnik} teraz={surowe.teraz} telefon={telefon} />;
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const z = await getZawodnikLekki(Number(id));
  return { title: z ? `${z.nazwa} – FootStats` : "Zawodnik – FootStats" };
}
