import { readdirSync, readFileSync, writeFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const GENERATED_DIR = join(process.cwd(), 'src', 'api', 'openapi-client');
const TS_NOCHECK = '// @ts-nocheck';

function addNoCheckHeader(filePath) {
  const content = readFileSync(filePath, 'utf8');
  if (content.startsWith(TS_NOCHECK)) return;
  writeFileSync(filePath, `${TS_NOCHECK}\n${content}`);
}

function walk(dirPath) {
  for (const entry of readdirSync(dirPath)) {
    const fullPath = join(dirPath, entry);
    const stats = statSync(fullPath);
    if (stats.isDirectory()) {
      walk(fullPath);
    } else if (stats.isFile() && entry.endsWith('.ts')) {
      addNoCheckHeader(fullPath);
    }
  }
}

walk(GENERATED_DIR);
