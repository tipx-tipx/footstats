import Image from "next/image";

/**
 * Logo FootStats — pliki od właściciela marki: logo-light.png (atrament,
 * na jasne tło) i logo-dark.png (biel, na ciemne tło), przełączane motywem
 * przez wariant dark (data-theme na <html>), bez żadnych filtrów.
 * Oba obrazy renderują się zawsze, widoczny jest jeden — zero mignięcia
 * przy zmianie motywu.
 */
export function Logo({ className = "h-10 w-auto" }: { className?: string }) {
  return (
    <span className="inline-flex shrink-0">
      <Image
        src="/logo-light.png"
        alt="FootStats"
        width={1254}
        height={443}
        priority
        className={`${className} dark:hidden`}
      />
      <Image
        src="/logo-dark.png"
        alt="FootStats"
        width={1254}
        height={443}
        priority
        className={`hidden ${className} dark:inline`}
      />
    </span>
  );
}
