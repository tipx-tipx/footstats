import { najblizszeMecze } from "@/app/projekt/_dane/najblizsze";
import { NieMaAplikacji } from "@/app/projekt/_ui/systemowe/SystemoweAplikacji";

export const metadata = { title: "Nie ma takiej strony – FootStats" };

export default async function NieMa() {
  const { najblizsze, teraz } = await najblizszeMecze();
  return <NieMaAplikacji najblizsze={najblizsze} teraz={teraz} />;
}
