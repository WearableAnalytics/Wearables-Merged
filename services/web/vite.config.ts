import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

const resolveProxyPath = (rawBasePath: string, fallbackPath: string) => {
  const fallback = fallbackPath.replace(/\/$/, '') || '/';
  const trimmed = rawBasePath.replace(/\/$/, '') || fallback;

  try {
    const url = new URL(trimmed);
    return url.pathname.replace(/\/$/, '') || fallback;
  } catch {
    return trimmed;
  }
};

const resolveProxyTarget = (rawUrl: string | undefined, fallbackTarget: string) => {
  if (!rawUrl) return fallbackTarget;

  try {
    const parsed = new URL(rawUrl);
    return `${parsed.protocol}//${parsed.host}`;
  } catch {
    return fallbackTarget;
  }
};

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const apiPath = resolveProxyPath(env.VITE_API_BASE_URL ?? '/api', '/api');
  const backendUrl = env.VITE_BACKEND_URL ?? 'http://localhost:3001';
  const grafanaProxyPath = resolveProxyPath(env.VITE_GRAFANA_PROXY_URL ?? '/grafana', '/grafana');
  const grafanaProxyTarget = resolveProxyTarget(
    env.VITE_GRAFANA_PROXY_URL,
    env.VITE_GRAFANA_PROXY_BACKEND_URL ?? 'http://localhost:3002',
  );

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
        [grafanaProxyPath]: {
          target: grafanaProxyTarget,
          changeOrigin: true,
          secure: false,
        },
      },
    },
  };
});
