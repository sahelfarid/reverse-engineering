import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node', // tests build their own jsdom Window per-case (see tests/frontend/dom.js)
    include: ['tests/frontend/**/*.test.js'],
  },
});
