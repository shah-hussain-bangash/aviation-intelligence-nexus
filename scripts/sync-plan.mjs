import fs from 'node:fs';
import path from 'node:path';
import { root, expectedRemote, git, reviewFile } from './repository-guards.mjs';

const failures = [];
const branch = git(['branch','--show-current']).stdout.trim();
const remote = git(['remote','get-url','origin']).stdout.trim();
if (branch !== 'main') failures.push('Automatic sync is restricted to main.');
if (remote !== expectedRemote) failures.push('Origin is missing or does not match the approved destination.');
if (git(['diff','--cached','--quiet']).status !== 0) failures.push('User-staged changes exist; preserve them for manual review.');
if (git(['diff','--name-only','--diff-filter=U']).stdout.trim()) failures.push('Resolve conflicts manually.');
const gitDir = git(['rev-parse','--git-dir']).stdout.trim();
if (gitDir) for (const marker of ['MERGE_HEAD','CHERRY_PICK_HEAD','REVERT_HEAD','rebase-merge','rebase-apply','index.lock']) {
  if (fs.existsSync(path.resolve(root, gitDir, marker))) failures.push('Another Git operation is in progress.');
}
const changed = git(['diff','--name-only','HEAD','-z']);
if (changed.status !== 0) failures.push('Initial commit is required before daily sync.');
const untracked = git(['ls-files','--others','--exclude-standard','-z']);
const files = [...new Set((changed.stdout + untracked.stdout).split('\0').filter(Boolean))];
for (const file of files) for (const reason of reviewFile(file)) failures.push(`${file}: ${reason}`);
console.log(JSON.stringify({ mode:'read-only local plan; no commit or push performed',branch,approvedRemote:expectedRemote,eligibleForDiffReview:failures.length===0,changedFiles:files,blockers:failures },null,2));
if (failures.length) process.exitCode = 1;
