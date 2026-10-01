import { notFound } from "next/navigation";

import { StronaAplikacji } from "@/app/projekt/_ui/aplikacja/Strona";
import { przygotujMecze } from "@/app/projekt/_dane/mecz";
import { najblizszeMecze } from "@/app/projekt/_dane/najblizsze";
import { przygotujStrony } from "@/app/projekt/_dane/strony";
import { meczZakonczony } from "@/app/projekt/_dane/zakonczony";
import { NieMaAplikacji } from "@/app/projekt/_ui/systemowe/SystemoweAplikacji";
import { zDanymi } from "@/app/projekt/_dane/zrodlo";
import { getMecze } from "@/lib/data";
import { pobierzSurowe, zKadramiMeczu } from "@/lib/nowe/surowe";
import { czyTelefon } from "@/lib/nowe/telefon";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const mecz = (await getMecze()).find((m) => m.id === Number(id));
  return { title: mecz ? `${mecz.gospodarz} – ${mecz.gosc} · FootStats` : "Mecz · FootStats" };
}

/**
 * Strona meczu (redesign, etap 7.3; 5.4 A zatwierdzone 01.10): narzędzie
 * pokryć jak Statshub – wszyscy zawodnicy z kursem, linie, okno 10/5,
 * znacznik „na liście”. Kadry z koszyków jak na starej stronie (ten sam transfer).
 */
export default async function MeczPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const meczId = Number(id);
  const [surowe, telefon] = await Promise.all([pobierzSurowe(), czyTelefon()]);
  const mecz = (surowe.mecze as { id: number; gospodarz: string; gosc: string }[]).find((m) => m.id === meczId);
  if (!mecz) {
    // rozegrany mecz z naszymi typami (7B: `mecz_id` w rozliczeniach) – typy i jak wyszły;
    // bez typów (albo mecz spoza oferty) – 404 „nie ma już w ofercie”
    const zakonczony = zDanymi(surowe, () => meczZakonczony(meczId));
    if (!zakonczony) notFound();
    const { najblizsze, teraz } = await najblizszeMecze();
    return <NieMaAplikacji wariant="mecz" zakonczony={zakonczony} najblizsze={najblizsze} teraz={teraz} />;
  }
  const zKadrami = await zKadramiMeczu(surowe, mecz as Parameters<typeof zKadramiMeczu>[1]);
  const [dane, mecze] = zDanymi(zKadrami, () => [przygotujStrony(), przygotujMecze()] as const);
  const m = mecze.find((x) => x.id === meczId);
  if (!m) notFound();
  return <StronaAplikacji strona="mecz" dane={dane} mecz={m} teraz={surowe.teraz} telefon={telefon} />;
}
