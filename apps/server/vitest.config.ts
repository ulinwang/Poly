import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    // Run test files serially: they share a single SQLite (WAL) db, and
    // parallel files intermittently hit "database is locked".
    fileParallelism: false,
  },
});
