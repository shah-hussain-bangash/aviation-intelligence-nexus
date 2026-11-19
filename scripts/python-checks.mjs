import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
if (!fs.existsSync(python)) {
  console.error('Create the project .venv and install requirements first. See docs/BACKEND_SETUP.md.');
  process.exitCode = 1;
} else {
  const result = spawnSync(python, ['-m', 'unittest', 'discover', '-s', 'tests', '-v'], {
    cwd: root, stdio: 'inherit', windowsHide: true, env: { ...process.env, OMP_NUM_THREADS: '2' }
  });
  process.exitCode = result.status ?? 1;
}
