// Compatibility fix for OpenAPI Generator 7.14 nullable Date serialization.
// Keep the older generator; do not regenerate unrelated clients with another version.
const fs = require('node:fs');
const path = require('node:path');
const directory = path.join(process.argv[2], 'models');
for (const name of fs.readdirSync(directory)) {
  if (!name.endsWith('.ts')) continue;
  const file = path.join(directory, name);
  const source = fs.readFileSync(file, 'utf8');
  const fixed = source.replace(/\(\(value\['(\w+)'\] as any\)\.toISOString\(\)\.substring\(0,10\)\)/g,
    (_, key) => `value['${key}'] == null ? value['${key}'] : value['${key}'].toISOString().substring(0,10)`);
  if (fixed !== source) fs.writeFileSync(file, fixed);
}
