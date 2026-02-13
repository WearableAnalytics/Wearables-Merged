import { CasesApi, CharitCasesApi, Configuration, PatientsApi } from './openapi-client';

const sharedConfig = new Configuration({
  basePath:
    process.env.API_BASE_URL ??
    process.env.VITE_API_BASE_URL ??
    process.env.API_PREFIX ??
    '/api',
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

export const defaultApi = new DefaultApi();
