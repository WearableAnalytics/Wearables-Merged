import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const apiPath = env.VITE_API_BASE_URL ?? '/api';
  const backendUrl = env.VITE_BACKEND_URL ?? 'http://localhost:3001';

  return {
    plugins: [react()],
    server: {
      proxy: {
        [apiPath]: {
          target: backendUrl,
          changeOrigin: true,
          secure: false,
        },
      },
    },
  };
});
