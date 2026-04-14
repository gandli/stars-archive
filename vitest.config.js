// vitest.config.js
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,           // describe/it/expect available without imports
    environment: 'node',     // use Node.js environment (not jsdom)
    include: ['tests/**/*.test.js'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.mjs'],
      exclude: ['**/*.test.js'],
    },
    // Run tests serially for file-system integration tests
    singleThread: true,
  },
});
