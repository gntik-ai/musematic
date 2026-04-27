import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import js from "@eslint/js";
import tseslint from "typescript-eslint";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const noHardcodedJsxStrings = require("./eslint/no-hardcoded-jsx-strings.js");

export default [
  {
    ignores: [
      "build/**",
      "dist/**",
      ".next/**",
      "coverage/**",
      "eslint.config.mjs",
      "eslint/**",
      "next-env.d.ts",
      "next.config.mjs",
      "node_modules/**",
      "playwright.config.ts",
      "postcss.config.js",
      "playwright-report/**",
      "test-results/**"
    ]
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: {
      "musematic-i18n": {
        rules: {
          "no-hardcoded-jsx-strings": noHardcodedJsxStrings
        }
      }
    },
    rules: {
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { "prefer": "type-imports" }
      ],
      "musematic-i18n/no-hardcoded-jsx-strings": [
        "error",
        {
          "allowlist": [
            "app/",
            "components/",
            "lib/",
            "__tests__/",
            "tests/"
          ]
        }
      ]
    }
  }
];
