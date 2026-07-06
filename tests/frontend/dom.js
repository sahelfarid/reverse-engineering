// Loads the dashboard's plain (non-module, no bundler) static/js files into a
// fresh jsdom Window, the same way the browser does via <script src="...">.
// Kept separate from individual test files so every frontend test starts from
// an identical, isolated DOM.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STATIC_JS_DIR = path.resolve(__dirname, '../../static/js');

function readScript(name) {
  return fs.readFileSync(path.join(STATIC_JS_DIR, name), 'utf-8');
}

// Builds a jsdom window with `bodyHtml` as the body and `sources` (in order)
// executed as classic scripts, so their top-level `function`/`const`
// declarations land on `window` exactly like a real page. Each entry in
// `sources` is either a static/js filename, or `{ code }` for an inline
// script (e.g. a stub replacing a module this test doesn't want to load).
export function buildDom(bodyHtml, sources) {
  const scripts = sources
    .map((src) => `<script>${typeof src === 'string' ? readScript(src) : src.code}</script>`)
    .join('\n');
  const html = `<!doctype html><html><body>${bodyHtml}${scripts}</body></html>`;
  const dom = new JSDOM(html, { runScripts: 'dangerously', url: 'http://localhost/' });
  return dom;
}
