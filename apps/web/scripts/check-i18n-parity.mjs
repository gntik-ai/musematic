/* global console, process */

import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const locales = ["de", "es", "fr", "ja", "zh-CN"];

async function readMessages(locale) {
  const filePath = path.join(root, "messages", `${locale}.json`);
  return JSON.parse(await readFile(filePath, "utf8"));
}

function flattenKeys(value, prefix = "") {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return [prefix];
  }

  return Object.entries(value).flatMap(([key, child]) =>
    flattenKeys(child, prefix ? `${prefix}.${key}` : key),
  );
}

const english = await readMessages("en");
const expectedKeys = flattenKeys(english).sort();
const failures = [];

for (const locale of locales) {
  const messages = await readMessages(locale);
  const available = new Set(flattenKeys(messages));
  const missing = expectedKeys.filter((key) => !available.has(key));

  if (missing.length > 0) {
    failures.push({ locale, missing });
  }
}

if (failures.length > 0) {
  console.error("i18n parity failures:");
  for (const failure of failures) {
    console.error(`- ${failure.locale}: missing ${failure.missing.length} keys`);
    for (const key of failure.missing) {
      console.error(`  ${key}`);
    }
  }
  process.exit(1);
}

console.log(`i18n parity check passed for ${locales.length} locale catalogs.`);
