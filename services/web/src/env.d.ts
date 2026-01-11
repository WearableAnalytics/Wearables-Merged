/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_SOCKET_URL?: string;
  readonly VITE_GRAFANA_PROXY_URL?: string;
  readonly VITE_GRAFANA_IFRAME_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
