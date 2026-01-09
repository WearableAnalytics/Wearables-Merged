// scripts/generate-openapi.ts
import { writeFileSync } from 'fs';
import { resolve } from 'path';
import { generateOpenApiDocument } from '../src/schemas';

const doc = generateOpenApiDocument();
const out = resolve(process.cwd(), 'openapi.json');
writeFileSync(out, JSON.stringify(doc, null, 2));
console.log('Wrote', out);
