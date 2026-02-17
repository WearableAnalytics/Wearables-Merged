import { Configuration, CasesApi, HospitalCasesApi, PatientsApi } from './openapi-client';
import { defaultApi, DefaultApi } from './defaultApi';
import { appRuntimeConfig } from '@/config/runtimeConfig';

const config = new Configuration({
  basePath: appRuntimeConfig.apiBaseUrl,
  credentials: 'include',
});

export const casesApi = new CasesApi(config);
export const hospitalCasesApi = new HospitalCasesApi(config);
export const patientsApi = new PatientsApi(config);

export { Configuration, defaultApi, DefaultApi };
