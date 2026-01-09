import { Configuration, CasesApi, CharitCasesApi, PatientsApi } from './openapi-client';
import { defaultApi, DefaultApi } from './defaultApi';

const config = new Configuration({
  basePath: import.meta.env.VITE_API_BASE_URL ?? '/api',
  credentials: 'include',
});

export const casesApi = new CasesApi(config);
export const charitCasesApi = new CharitCasesApi(config);
export const patientsApi = new PatientsApi(config);

export { Configuration, defaultApi, DefaultApi };
