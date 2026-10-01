import { przygotujFundamenty } from "../_dane/przygotuj";
import { Atomy, type StartAtomow } from "../_ui/Atomy";

export default async function AtomyPage({ searchParams }: { searchParams: Promise<StartAtomow> }) {
  return <Atomy dane={przygotujFundamenty()} start={await searchParams} />;
}
