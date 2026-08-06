import Image from "next/image";

/**
 * Logo FootStats – pliki od właściciela marki: logo-light.png (atrament,
 * na jasne tło) i logo-dark.png (biel, na ciemne tło), przełączane motywem
 * przez wariant dark (data-theme na <html>), bez żadnych filtrów.
 * Oba obrazy renderują się zawsze, widoczny jest jeden – zero mignięcia
 * przy zmianie motywu.
 *
 * WYMIARY IDĄ W HTML, NIE TYLKO W CSS (2026-08-06). Wcześniej `<Image>`
 * dostawał naturalne 1254×443 px, a rozmiar docelowy robiła klasa
 * (`h-10 w-auto`). Dopóki arkusz nie zadziałał, przeglądarka rezerwowała
 * 1254 px szerokości — `npm run audyt` łapał na tym trzy strony naraz:
 * „UCIEKA /login — strona ma 1262px zamiast 390px". Najbardziej bolało
 * na ekranie logowania, czyli PIERWSZYM, jaki ktokolwiek widzi: strona
 * potrafiła podskoczyć w bok, zanim logo się doczytało.
 *
 * Teraz wysokość jest liczbą, a szerokość liczy się z proporcji pliku —
 * więc poprawny rozmiar niesie sam HTML i nie ma czego rezerwować.
 */

const PROPORCJA = 1254 / 443;

export function Logo({
  wysokosc = 40,
  className = "",
}: {
  /** wysokość logo w pikselach — szerokość dolicza się z proporcji pliku */
  wysokosc?: number;
  className?: string;
}) {
  const szerokosc = Math.round(wysokosc * PROPORCJA);
  return (
    <span className="inline-flex shrink-0">
      <Image
        src="/logo-light.png"
        alt="FootStats"
        width={szerokosc}
        height={wysokosc}
        priority
        className={`${className} dark:hidden`}
      />
      <Image
        src="/logo-dark.png"
        alt="FootStats"
        width={szerokosc}
        height={wysokosc}
        priority
        className={`hidden ${className} dark:inline`}
      />
    </span>
  );
}
