import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import { loadEnv } from 'vite';

const mode = process.env.NODE_ENV ?? 'development';
const env = loadEnv(mode, process.cwd(), '');
const apiPath = env.VITE_API_BASE_URL ?? '/api';
const backendUrl = env.VITE_BACKEND_URL ?? 'http://localhost:3001';

export default defineConfig({
  integrations: [react()],
  vite: {
    server: {
      proxy: {
        [apiPath]: {
          target: backendUrl,
          changeOrigin: true,
          secure: false,
        },
      },
    },
  },
});
