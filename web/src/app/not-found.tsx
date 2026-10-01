import { NieMaAplikacji } from "@/app/projekt/_ui/systemowe/SystemoweAplikacji";
import { SamoLogo } from "@/app/projekt/_ui/systemowe/SamoLogo";

export const metadata = { title: "Nie ma takiej strony – FootStats" };

/** 404 poza menu aplikacji (adresy, których nie łapie (app)/[...reszta]) – bez zapytań do danych */
export default function NieMaGlowna() {
  return (
    <SamoLogo>
      <NieMaAplikacji najblizsze={[]} teraz={0} bezSzukania />
    </SamoLogo>
  );
}
