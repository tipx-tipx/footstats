import { przygotujElementy } from "../_dane/elementy";
import { Elementy, type StartElementow } from "../_ui/Elementy";

export default async function ElementyPage({ searchParams }: { searchParams: Promise<StartElementow> }) {
  return <Elementy dane={przygotujElementy()} start={await searchParams} />;
}
