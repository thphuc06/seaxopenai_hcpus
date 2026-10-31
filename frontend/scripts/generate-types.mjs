import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';

const python = resolve('..', 'backend', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const commands = [
  [python, ['scripts/export_openapi.py']],
  [process.execPath, ['node_modules/openapi-typescript/bin/cli.js', 'node_modules/.cache/contract-openapi.json', '-o', 'src/api/schema.d.ts']],
];
for (const [command, args] of commands) {
  const result = spawnSync(command, args, { stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
