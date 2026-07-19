import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/static/spa/',
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  define: {
    'global': 'globalThis',
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
