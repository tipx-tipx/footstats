import { przygotujSystemowe } from "../_dane/systemowe";
import { LogowaniePelne } from "../_ui/systemowe/LogowaniePelne";

export default async function LogowaniePage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  return <LogowaniePelne dane={przygotujSystemowe()} start={await searchParams} />;
}
