import { przygotujFundamenty } from "../_dane/przygotuj";
import { Atomy2, type StartAtomow2 } from "../_ui/Atomy2";

export default async function Atomy2Page({ searchParams }: { searchParams: Promise<StartAtomow2> }) {
  return <Atomy2 dane={przygotujFundamenty()} start={await searchParams} />;
}
