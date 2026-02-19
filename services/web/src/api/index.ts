import { Configuration, CasesApi, HospitalCasesApi, PatientsApi } from './openapi-client';
import { defaultApi, DefaultApi } from './defaultApi';

const config = new Configuration({
  basePath: import.meta.env.VITE_API_BASE_URL ?? '/api',
  credentials: 'include',
});

export const casesApi = new CasesApi(config);
export const hospitalCasesApi = new HospitalCasesApi(config);
export const patientsApi = new PatientsApi(config);

export { Configuration, defaultApi, DefaultApi };
