import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const expectedRemote = 'https://github.com/zenithdevelopers7-source/aviation-intelligence-nexus.git';
export function git(args) {
  const result = spawnSync('git', args, { cwd: root, encoding: 'utf8', windowsHide: true, maxBuffer: 16 * 1024 * 1024 });
  if (result.error) throw result.error;
  return result;
}
export function candidateFiles() {
  const result = git(['ls-files', '--cached', '--others', '--exclude-standard', '-z']);
  if (result.status !== 0) throw new Error('A Git repository is required.');
  return [...new Set(result.stdout.split('\0').filter(Boolean))];
}
const allowedRoots = new Set(['apps','services','pipelines','ml','rag','agents','optimization','contracts','db','infra','tests','scripts','docs','.github','.vscode']);
const allowedRootFiles = new Set(['README.md','AGENTS.md','CHANGELOG.md','LICENSE','LICENSE.md','package.json','package-lock.json','pyproject.toml','uv.lock','requirements.txt','Makefile','Dockerfile','compose.yaml','compose.yml','.gitignore','.gitattributes','.env.example']);
const allowedExtensions = new Set(['.js','.mjs','.cjs','.ts','.tsx','.jsx','.html','.css','.json','.md','.yml','.yaml','.toml','.sql','.py','.txt','.ps1','.sh','.lock','.jpg','.jpeg','.png','.webp','.svg']);
const secretRules = [
  ['github-token', /gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}/],
  ['aws-access-id', /AKIA[0-9A-Z]{16}/],
  ['private-key', /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/],
  ['provider-secret', /sk-(?:proj-)?[A-Za-z0-9_-]{24,}/]
];
export function reviewFile(relative) {
  const errors = [];
  const normalized = relative.replaceAll('\\', '/');
  const parts = normalized.split('/');
  const basename = parts.at(-1);
  const extension = path.extname(basename).toLowerCase();
  if (parts.includes('..') || path.isAbsolute(relative)) return ['Path escapes repository'];
  if (parts.length === 1 ? !allowedRootFiles.has(basename) : !allowedRoots.has(parts[0])) errors.push('Path needs manual scope review');
  if ((basename.startsWith('.env') && basename !== '.env.example') || /(?:^|\/)(?:secrets?|credentials)(?:[./]|$)/i.test(normalized)) errors.push('Credential-related path');
  if (extension === '.csv' ? !normalized.startsWith('docs/reports/') : (!allowedExtensions.has(extension) && !allowedRootFiles.has(basename))) errors.push('File type needs manual review');
  const absolute = path.resolve(root, relative);
  if (!fs.existsSync(absolute)) return errors; // A reviewed deletion has no current bytes to scan.
  const stat = fs.lstatSync(absolute);
  if (!stat.isFile() || stat.isSymbolicLink()) return [...errors, 'Only ordinary source files are eligible'];
  if (stat.size > 5 * 1024 * 1024) errors.push('File exceeds 5 MiB automatic-publication limit');
  if (!['.jpg','.jpeg','.png','.webp'].includes(extension) && stat.size <= 5 * 1024 * 1024) {
    const content = fs.readFileSync(absolute, 'utf8');
    for (const [name, pattern] of secretRules) if (pattern.test(content)) errors.push(`Potential sensitive value (${name}); inspect privately`);
    if (/(?:C:\\Users\\|C:\/Users\/|\\\\192\.168\.)/i.test(content)) errors.push('Local personal path should be removed before publication');
  }
  return errors;
}
