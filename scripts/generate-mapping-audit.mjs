import { readFileSync, writeFileSync } from 'node:fs';

const catalog = JSON.parse(readFileSync(new URL('../tests/liftosaur-exercises.json', import.meta.url), 'utf8'));
const source = JSON.parse(readFileSync(new URL('../shared/exercise-mappings.json', import.meta.url), 'utf8'));
const mappings = new Map();

for (const entry of source.mappings) {
  for (const name of entry.names) {
    if (mappings.has(name)) throw new Error(`Duplicate exercise mapping: ${name}`);
    mappings.set(name, entry);
  }
}

const names = [...catalog.names].sort((a, b) => a.localeCompare(b));
const missing = names.filter(name => !mappings.has(name));
if (missing.length) throw new Error(`Unmapped catalog exercises:\n${missing.join('\n')}`);

const escapeCell = value => String(value ?? '').replaceAll('|', '\\|').replaceAll('\n', ' ');
const sections = ['exact', 'generic', 'category', 'unsupported'];
const lines = [
  '# Liftosaur exercise mapping coverage',
  '',
  `Catalog snapshot: ${catalog.date}, from Liftosaur MCP \`list_exercises\`.`,
  `Garmin FIT profile: ${source.fitProfileVersion}. Equipment variants count separately.`,
  'This report is generated from [the shared mappings](../shared/exercise-mappings.json)',
  'and [the catalog snapshot](../tests/liftosaur-exercises.json).',
  '',
  '| Decision | Built-in names |',
  '| --- | ---: |',
];

for (const section of sections) {
  lines.push(`| ${section} | ${names.filter(name => mappings.get(name).quality === section).length} |`);
}
lines.push(
  `| Total | ${names.length} |`,
  '',
  'Every built-in name has an explicit decision. Exact and generic entries include',
  'a Garmin category and subtype. Generic entries lose the detail stated below.',
  'Category-only and unsupported entries may still display as Unknown in Garmin.',
  'Unknown custom names also remain unknown; no fuzzy matching is used.',
  '',
  'Defaults were checked against [Liftosaur exercise definitions](https://github.com/astashov/liftosaur/blob/master/src/models/exercise.ts).',
  'FIT symbols are resolved by the .NET Garmin FIT SDK when FIT files are generated.',
  'This validates FIT metadata, not Garmin Connect display behavior for every exercise.',
  '',
);

for (const section of sections) {
  lines.push(`## ${section}`, '', '| Liftosaur name | Garmin category | Garmin subtype | Limitation |', '| --- | --- | --- | --- |');
  for (const name of names) {
    const entry = mappings.get(name);
    if (entry.quality !== section) continue;
    lines.push(`| ${escapeCell(name)} | ${escapeCell(entry.category)} | ${escapeCell(entry.subtype)} | ${escapeCell(entry.note)} |`);
  }
  lines.push('');
}

writeFileSync(new URL('../docs/exercise-catalog-audit.md', import.meta.url), `${lines.join('\n')}\n`);
