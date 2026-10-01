import { przygotujStrony } from "../_dane/strony";
import { Ruch } from "../_ui/ruch/Ruch";

export default function RuchPage() {
  return <Ruch dane={przygotujStrony()} />;
}
