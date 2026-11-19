import assert from 'node:assert/strict';
import http from 'node:http';
import { test } from 'node:test';
import { inspectPort, portNumber } from '../scripts/start-local.mjs';

test('startup rejects invalid and out-of-range port values', () => {
  assert.equal(portNumber('8002'), 8002);
  for (const value of [0, -1, 65536, 'invalid', '2.5']) assert.throws(() => portNumber(value));
});

test('startup recognizes an existing AIN service without taking ownership', async () => {
  const server = http.createServer((req, res) => { res.end('{"service":"ain-api"}'); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try { assert.equal(await inspectPort(server.address().port, 'ain-api'), 'existing'); }
  finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});

test('startup preserves unknown occupied ports and recognizes released ports', async () => {
  const server = http.createServer((req, res) => { res.end('{"service":"unrelated"}'); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  try { await assert.rejects(inspectPort(port, 'ain-dashboard'), /occupied by another or older service/); }
  finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
  assert.equal(await inspectPort(port, 'ain-dashboard'), 'free');
});
