import { Configuration, CasesApi, CharitCasesApi, PatientsApi } from './openapi-client';

// Shared configuration for all generated API classes.
export const API_BASE_PATH = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:3001/api';

const sharedConfig = new Configuration({
  basePath: API_BASE_PATH,
  credentials: 'include',
});

export class DefaultApi {
  private casesApi = new CasesApi(sharedConfig);
  private charitCasesApi = new CharitCasesApi(sharedConfig);
  private patientsApi = new PatientsApi(sharedConfig);

  // Cases
  casesCaseIdGet = this.casesApi.casesCaseIdGet.bind(this.casesApi);
  casesFromChariteCasePost = this.casesApi.casesFromChariteCasePost.bind(this.casesApi);
  casesGet = this.casesApi.casesGet.bind(this.casesApi);
  casesVerifyTokenPost = this.casesApi.casesVerifyTokenPost.bind(this.casesApi);

  // Charité cases
  chariteCasesCCaseIdGet = this.charitCasesApi.chariteCasesCCaseIdGet.bind(this.charitCasesApi);

  // Patients
  patientsGet = this.patientsApi.patientsGet.bind(this.patientsApi);
  patientsPatientIdCasesGet = this.patientsApi.patientsPatientIdCasesGet.bind(this.patientsApi);
  patientsPatientIdGet = this.patientsApi.patientsPatientIdGet.bind(this.patientsApi);
}

// Singleton instance that mirrors the prior "defaultApi" pattern.
export const defaultApi = new DefaultApi();
