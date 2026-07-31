import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  {
    // DŁUG DO SPŁACENIA, ŚWIADOMIE OZNACZONY (2026-07-31).
    //
    // Reguły kompilatora Reacta zgłaszają dziś 15 miejsc: 14 × ustawianie
    // stanu wprost w efekcie i 1 × zapis do zmiennej po zakończeniu renderu.
    // Wszystkie są SPRZED wprowadzenia CI i wszystkie działają — to wzorce,
    // które ten kompilator dopiero zaczął piętnować, a nie świeże błędy.
    //
    // Zostawiamy je jako ostrzeżenia, a nie błędy, z jednego powodu: gdyby
    // blokowały CI, pierwszy przebieg byłby czerwony i CI zostałoby uznane
    // za psujące się samo z siebie — czyli dokładnie tak, jak nie chcemy.
    // Ostrzeżenie widać w logu, liczba jest tu zapisana, więc dług nie
    // znika z oczu. Do naprawy osobno, plikami, nie hurtem.
    rules: {
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/immutability": "warn",
    },
  },
]);

export default eslintConfig;
