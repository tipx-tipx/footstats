import { najblizszeMecze } from "@/app/projekt/_dane/najblizsze";
import { NieMaAplikacji } from "@/app/projekt/_ui/systemowe/SystemoweAplikacji";

/** mecz spoza oferty – zwykle już rozegrany; typy z niego zostają w Wynikach */
export default async function MeczaNieMa() {
  const { najblizsze, teraz } = await najblizszeMecze();
  return <NieMaAplikacji wariant="mecz" najblizsze={najblizsze} teraz={teraz} />;
}
