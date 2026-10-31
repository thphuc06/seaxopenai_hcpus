import { cpSync, copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const site = path.resolve(process.argv[2] ?? path.join(root, 'sites/passport'));
const frontend = path.join(root, 'frontend');
const manifest = path.join(site, '.openai/hosting.json');
if (!existsSync(manifest) || !JSON.parse(readFileSync(manifest, 'utf8')).project_id) {
  throw new Error('Register Site and persist project_id before preparing source');
}
if (!existsSync(path.join(frontend, 'dist/index.html'))) throw new Error('Build frontend in API mode first');

// Explicit allowlist: no backend, fixtures, credentials or Git metadata enters Site source.
const source = path.join(site, 'passport-source');
mkdirSync(source, { recursive: true });
for (const name of ['src', 'public', 'index.html', 'package.json', 'package-lock.json', 'tsconfig.json', 'vite.config.ts']) {
  if (existsSync(path.join(frontend, name))) cpSync(path.join(frontend, name), path.join(source, name), { recursive: true });
}
mkdirSync(path.join(site, 'public'), { recursive: true });
cpSync(path.join(frontend, 'dist'), path.join(site, 'public'), { recursive: true });
copyFileSync(path.join(frontend, 'dist/index.html'), path.join(site, 'public/passport.html'));
copyFileSync(path.join(root, 'scripts/dev/sites/proxy.mts'), path.join(site, 'worker/proxy.mts'));
const commit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim();
writeFileSync(path.join(site, 'passport-source/SOURCE.json'), JSON.stringify({
  repository: 'https://github.com/thphuc06/seaxopenai_hcpus',
  commit, frontend_path: 'frontend', build_mode: 'VITE_USE_MOCK=0',
  backend: 'https://product-truth-passport-demo.onrender.com',
}, null, 2) + '\n', 'utf8');
console.log('Prepared frontend assets and sanitized source from ' + commit);
