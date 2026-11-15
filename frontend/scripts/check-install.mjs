import { statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// npm's dependency metadata can remain intact after an interrupted installation.
// Check the actual development runtimes before handing control to Vite.
const files = [
  '../node_modules/react/cjs/react.development.js',
  '../node_modules/react-dom/cjs/react-dom.development.js',
  '../node_modules/react-dom/client.js',
];
for (const file of files) {
  try {
    if (statSync(fileURLToPath(new URL(file, import.meta.url))).size > 0) continue;
  } catch {
    // Report the same recovery step for missing and partially written packages.
  }
  console.error('Frontend dependency installation is incomplete. Run npm ci from frontend/, then restart npm run dev -- --force.');
  process.exit(1);
}
