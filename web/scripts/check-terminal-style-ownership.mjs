import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourceRoot = join(webRoot, "src");
const ownerPath = join(sourceRoot, "etf-design-system.css");
const ownedSelectors = [
  ".etf-command-row",
  ".etf-global-controls",
  ".etf-selector-toolbar",
  ".etf-agent-link",
  ".etf-utility-button",
  ".etf-list-toggle",
  ".terminal-control",
  ".terminal-select",
];

const violations = [];

for (const filePath of cssFiles(sourceRoot)) {
  if (filePath === ownerPath) {
    continue;
  }

  const lines = readFileSync(filePath, "utf8").split(/\r?\n/u);
  lines.forEach((line, index) => {
    for (const selector of ownedSelectors) {
      if (line.includes(selector)) {
        violations.push(
          `${relative(webRoot, filePath)}:${index + 1} contains ${selector}`,
        );
      }
    }
  });
}

if (violations.length > 0) {
  process.stderr.write(
    [
      "ETF terminal styles must be owned by src/etf-design-system.css.",
      ...violations.map((violation) => `- ${violation}`),
      "",
    ].join("\n"),
  );
  process.exitCode = 1;
} else {
  process.stdout.write("ETF terminal style ownership is valid.\n");
}

function cssFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const entryPath = join(directory, entry.name);
    if (entry.isDirectory()) {
      return cssFiles(entryPath);
    }
    return entry.isFile() && entry.name.endsWith(".css") ? [entryPath] : [];
  });
}
