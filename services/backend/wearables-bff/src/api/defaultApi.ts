import { CasesApi, HospitalCasesApi, Configuration, PatientsApi } from './openapi-client';
import config from '../config.js';

const sharedConfig = new Configuration({
  basePath: config.apiPrefix,
  credentials: 'include',
});

export class DefaultApi {
  private casesApi = new CasesApi(sharedConfig);
  private hospitalCasesApi = new HospitalCasesApi(sharedConfig);
  private patientsApi = new PatientsApi(sharedConfig);

  // Cases
  casesCaseIdGet = this.casesApi.casesCaseIdGet.bind(this.casesApi);
  casesFromHospitalCasePost = this.casesApi.casesFromHospitalCasePost.bind(this.casesApi);
  casesGet = this.casesApi.casesGet.bind(this.casesApi);
  casesVerifyTokenPost = this.casesApi.casesVerifyTokenPost.bind(this.casesApi);

  // Hospital cases
  hospitalCasesHospitalCaseIdGet = this.hospitalCasesApi.hospitalCasesHospitalCaseIdGet.bind(this.hospitalCasesApi);

  // Patients
  patientsGet = this.patientsApi.patientsGet.bind(this.patientsApi);
  patientsPatientIdCasesGet = this.patientsApi.patientsPatientIdCasesGet.bind(this.patientsApi);
  patientsPatientIdGet = this.patientsApi.patientsPatientIdGet.bind(this.patientsApi);
}

export const defaultApi = new DefaultApi();
