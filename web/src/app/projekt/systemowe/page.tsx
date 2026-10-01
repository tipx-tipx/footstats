import { przygotujSystemowe } from "../_dane/systemowe";
import { Systemowe, type StartSystemowych } from "../_ui/systemowe/Systemowe";

export default async function SystemowePage({ searchParams }: { searchParams: Promise<StartSystemowych> }) {
  return <Systemowe dane={przygotujSystemowe()} start={await searchParams} />;
}
