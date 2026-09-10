import eslint from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["node_modules/**", "runtime-data/**", "dist/**"] },
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{js,ts,tsx}"],
    languageOptions: { globals: globals.node },
    rules: { "no-console": "off" },
  },
  {
    files: ["src/app/*.{ts,tsx}"],
    languageOptions: { globals: globals.browser },
  },
  {
    files: ["src/app/preload.cjs"],
    languageOptions: { globals: { ...globals.node, ...globals.commonjs } },
    rules: { "@typescript-eslint/no-require-imports": "off" },
  },
);
