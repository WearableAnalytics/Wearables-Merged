import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

const resolveApiProxyPath = (rawBasePath: string) => {
  const trimmed = rawBasePath.replace(/\/$/, '') || '/api';

  try {
    const url = new URL(trimmed);
    return url.pathname.replace(/\/$/, '') || '/api';
  } catch {
    return trimmed;
  }
};

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const apiPath = resolveApiProxyPath(env.VITE_API_BASE_URL ?? '/api');
  const backendUrl = env.VITE_BACKEND_URL ?? 'http://localhost:3001';

  return {
    base: '/',
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
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
