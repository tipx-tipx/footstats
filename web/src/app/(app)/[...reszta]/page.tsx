import { notFound } from "next/navigation";

/** każdy nieznany adres w aplikacji → 404 w menu aplikacji, a nie goła strona bez nawigacji */
export default function Reszta() {
  notFound();
}
