import { przygotujElementy } from "../_dane/elementy";
import { Szkielet, type StartSzkieletu } from "../_ui/szkielet/Szkielet";

export default async function SzkieletPage({ searchParams }: { searchParams: Promise<StartSzkieletu> }) {
  return <Szkielet dane={przygotujElementy()} start={await searchParams} />;
}
