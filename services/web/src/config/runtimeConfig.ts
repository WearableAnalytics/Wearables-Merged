type AppRuntimeConfig = {
  API_BASE_URL?: string;
  GRAFANA_PROXY_URL?: string;
  SOCKET_URL?: string;
};

const readConfigValue = (value: string | undefined): string | undefined => {
  const normalized = value?.trim();
  return normalized ? normalized : undefined;
};

const runtimeConfig = (typeof window !== 'undefined'
  ? window.__APP_CONFIG__
  : undefined) as AppRuntimeConfig | undefined;

export const appRuntimeConfig = {
  apiBaseUrl: readConfigValue(runtimeConfig?.API_BASE_URL) ?? import.meta.env.VITE_API_BASE_URL ?? '/api',
  grafanaProxyUrl:
    readConfigValue(runtimeConfig?.GRAFANA_PROXY_URL) ??
    import.meta.env.VITE_GRAFANA_PROXY_URL ??
    '/grafana-proxy',
  socketUrl: readConfigValue(runtimeConfig?.SOCKET_URL) ?? import.meta.env.VITE_SOCKET_URL ?? '',
} as const;
