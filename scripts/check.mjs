import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { root, candidateFiles, reviewFile } from './repository-guards.mjs';

const files = candidateFiles();
const failures = files.flatMap(file => reviewFile(file).map(reason => `${file}: ${reason}`));
for (const file of files.filter(f => /\.(?:mjs|js)$/.test(f) && fs.existsSync(path.join(root, f)))) {
  const check = spawnSync(process.execPath, ['--check', path.join(root, file)], { encoding: 'utf8', windowsHide: true });
  if (check.status !== 0) failures.push(`${file}: JavaScript syntax check failed`);
}
try {
  const audit = JSON.parse(fs.readFileSync(path.join(root, 'docs/reports/AIN_Completion_Report.json'), 'utf8'));
  const ids = audit.production_requirements.map(row => row.id);
  if (ids.length !== 24 || new Set(ids).size !== 24) failures.push('Completion report must retain 24 unique requirement IDs.');
  const spec = JSON.parse(fs.readFileSync(path.join(root, 'docs/reports/AIN_Complete_System_Specification.json'), 'utf8'));
  if (Object.keys(spec.workspaces).length !== 64 || Object.keys(spec.functions).length !== 64) failures.push('Workspace specification must preserve all 64 workspaces.');
} catch { failures.push('A required report/specification JSON file is missing or invalid.'); }
if (failures.length) {
  console.error('Source validation blocked:\n' + failures.join('\n'));
  process.exitCode = 1;
} else console.log(`Source checks passed for ${files.length} files. These are source/integrity checks, not backend or production acceptance tests.`);
