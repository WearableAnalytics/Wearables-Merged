type AppRuntimeConfig = {
  API_BASE_URL?: string;
  GRAFANA_PROXY_URL?: string;
  SOCKET_URL?: string;
};

const readConfigValue = (value: string | undefined): string | undefined => {
  const normalized = value?.trim();
  return normalized ? normalized : undefined;
};

const resolveConfigValue = (
  runtimeValue: string | undefined,
  viteValue: string | undefined,
): string | undefined => readConfigValue(runtimeValue) ?? readConfigValue(viteValue);

const requireConfigValue = (name: keyof AppRuntimeConfig, value: string | undefined): string => {
  if (value) return value;
  throw new Error(
    `[runtime-config] Missing required config "${name}". Set window.__APP_CONFIG__.${name} ` +
      `in /runtime-config.js (Kubernetes) or VITE_${name} in services/web/.env (local).`,
  );
};

const runtimeConfig = (typeof window !== 'undefined'
  ? window.__APP_CONFIG__
  : undefined) as AppRuntimeConfig | undefined;

const apiBaseUrl = resolveConfigValue(runtimeConfig?.API_BASE_URL, import.meta.env.VITE_API_BASE_URL);
const grafanaProxyUrl = resolveConfigValue(
  runtimeConfig?.GRAFANA_PROXY_URL,
  import.meta.env.VITE_GRAFANA_PROXY_URL,
);
const socketUrl = resolveConfigValue(runtimeConfig?.SOCKET_URL, import.meta.env.VITE_SOCKET_URL);

export const appRuntimeConfig = {
  apiBaseUrl: requireConfigValue('API_BASE_URL', apiBaseUrl),
  grafanaProxyUrl: requireConfigValue('GRAFANA_PROXY_URL', grafanaProxyUrl),
  socketUrl: socketUrl ?? '',
} as const;
