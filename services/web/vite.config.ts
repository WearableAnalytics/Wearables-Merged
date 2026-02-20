import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

const readEnvValue = (rawValue: string | undefined): string | undefined => {
  const trimmed = rawValue?.trim();
  return trimmed ? trimmed : undefined;
};

const resolveProxyPath = (rawBasePath: string) => {
  const trimmed = rawBasePath.replace(/\/$/, '') || '/';

  try {
    const url = new URL(trimmed);
    return url.pathname.replace(/\/$/, '') || '/';
  } catch {
    return trimmed;
  }
};

const resolveProxyTarget = (rawUrl: string, fallbackTarget: string) => {
  try {
    const parsed = new URL(rawUrl);
    return `${parsed.protocol}//${parsed.host}`;
  } catch {
    return fallbackTarget;
  }
};

export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const isServeCommand = command === 'serve';
  const apiBaseUrl = readEnvValue(env.VITE_API_BASE_URL);
  const backendUrl = readEnvValue(env.VITE_BACKEND_URL);
  const grafanaProxyUrl = readEnvValue(env.VITE_GRAFANA_PROXY_URL);
  const grafanaProxyBackendUrl = readEnvValue(env.VITE_GRAFANA_PROXY_BACKEND_URL);

  return {
    base: '/',
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: isServeCommand
      ? (() => {
          const proxy: Record<string, { target: string; changeOrigin: boolean; secure: boolean }> = {};

          if (apiBaseUrl && backendUrl) {
            proxy[resolveProxyPath(apiBaseUrl)] = {
              target: backendUrl,
              changeOrigin: true,
              secure: false,
            };
          }

          if (grafanaProxyUrl && grafanaProxyBackendUrl) {
            proxy[resolveProxyPath(grafanaProxyUrl)] = {
              target: resolveProxyTarget(grafanaProxyUrl, grafanaProxyBackendUrl),
              changeOrigin: true,
              secure: false,
            };
          }

          return {
            proxy,
          };
        })()
      : undefined,
  };
});
