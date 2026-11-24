import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import {runtimeConfig} from './runtime-config.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export function portNumber(value) {
  const port = Number(value);
  if (!/^[0-9]{1,5}$/.test(String(value)) || !Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Choose a valid local port (1–65535).');
  return port;
}

export async function inspectPort(port, service) {
  const free = await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', error => error.code === 'EADDRINUSE' ? resolve(false) : reject(error));
    server.listen(port, '127.0.0.1', () => server.close(() => resolve(true)));
  });
  if (free) return 'free';
  try {
    const endpoint = service === 'ain-api' ? '/health/live' : '/__ain/health';
    const response = await fetch(`http://127.0.0.1:${port}${endpoint}`, {signal:AbortSignal.timeout(2000),redirect:'error'});
    const data = await response.json();
    if (response.ok && data.service === service) return 'existing';
  } catch { /* An unidentified occupied port must remain untouched. */ }
  throw new Error(`Port ${port} is occupied by another or older service. Stop it yourself or choose another port; no process was terminated.`);
}

async function start() {
  const config=runtimeConfig();
  if(config.container)throw new Error('The native launcher cannot run in container mode.');
  const apiPort=config.apiPort,webPort=config.webPort;
  if (apiPort === webPort) throw new Error('API and dashboard need different ports.');
  const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  if (!fs.existsSync(python)) throw new Error('Create .venv and install requirements first. See docs/BACKEND_SETUP.md.');
  const apiState = await inspectPort(apiPort, 'ain-api');
  const webState = await inspectPort(webPort, 'ain-dashboard');
  const children = [];
  let stopping = false;
  function stop(code = 0) {
    if (stopping) return;
    stopping = true; process.exitCode = code;
    for (const child of children) if (child.exitCode === null) child.kill();
  }
  process.on('SIGINT', () => stop()); process.on('SIGTERM', () => stop());
  function launch(command, args, name) {
    const child = spawn(command, args, {cwd:root,stdio:'inherit',windowsHide:true,
      env:{...process.env,AIN_AGENT_JOBS:process.env.AIN_AGENT_JOBS??'1',PORT:String(webPort),AIN_API_PORT:String(apiPort)}});
    children.push(child);
    child.once('error', () => { console.error(`${name} could not start. Check its environment and dependencies.`); stop(1); });
    child.once('exit', code => { if (!stopping) { console.error(`${name} stopped (exit ${code}).`); stop(1); } });
  }
  if (apiState === 'free') launch(python, ['-m','uvicorn','services.api.main:app','--host','127.0.0.1','--port',String(apiPort),'--log-config',path.join(root,'infra/request-logging.json'),'--no-access-log'], 'API');
  else console.log(`Reusing the existing AIN API on ${apiPort}.`);
  if (webState === 'free') launch(process.execPath, ['scripts/dev.mjs'], 'Dashboard');
  else console.log(`Reusing the existing AIN dashboard on ${webPort}.`);
  console.log(`Dashboard: http://127.0.0.1:${webPort}`);
  console.log(children.length ? 'Keep this terminal open. Ctrl+C stops only services started by this command.' : 'Both services are already running; nothing new was started.');
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  start().catch(error => { console.error(error.message); process.exitCode = 1; });
}
