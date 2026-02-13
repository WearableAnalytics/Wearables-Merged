import { nanoid } from 'nanoid';
import type { Case, HospitalCase, Patient } from './api/openapi-client/models';

export type CaseStatus = Case['status'];
export type CaseRecord = Case;

interface HospitalCaseWithUUID extends HospitalCase {
  uuid: string;
}

const hospitalCases: HospitalCaseWithUUID[] = [
  { 
    hospitalCaseId: 'C-123456', 
    uuid: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    firstName: 'Max', 
    lastName: 'Mustermann', 
    birthDate: new Date('1980-01-01'),
  },
  { 
    hospitalCaseId: 'C-654321', 
    uuid: 'b2c3d4e5-f6a7-8901-bcde-f12345678901',
    firstName: 'Jane', 
    lastName: 'Doe', 
    birthDate: new Date('1975-05-20'),
  },
    { 
    hospitalCaseId: 'C-000000', 
    uuid: 'd2c3d4e5-f6a7-8901-bbbb-f12345678901',
    firstName: 'Blubb', 
    lastName: 'Doe', 
    birthDate: new Date('1975-05-20'),
  },
];

const patients: Patient[] = [
  { patientId: 'P-98765', firstName: 'Max', lastName: 'Mustermann', birthDate: new Date('1980-01-01') },
  { patientId: 'P-24680', firstName: 'Mia', lastName: 'Muster', birthDate: new Date('1985-12-03') },
];

const cases: CaseRecord[] = [
  {
    caseId: 'IC-54321',
    patientId: 'P-98765',
    hospitalCaseId: 'C-123456',
    status: 'active',
    caseToken: 'token-12345',
  },
  { caseId: 'IC-13579', patientId: 'P-24680', status: 'inactive', caseToken: 'token-24680' },
];

export function findHospitalCase(hospitalCaseId: string): HospitalCaseWithUUID | undefined {
  return hospitalCases.find((item) => item.hospitalCaseId === hospitalCaseId);
}

export function listPatients() {
  return patients;
}

export function findPatient(patientId: string) {
  return patients.find((item) => item.patientId === patientId);
}

export function listCases() {
  return cases;
}

export function findCase(caseId: string) {
  return cases.find((item) => item.caseId === caseId);
}

export function findCaseByToken(caseToken: string) {
  return cases.find((item) => item.caseToken === caseToken);
}

export function casesForPatient(patientId: string) {
  return cases.filter((item) => item.patientId === patientId);
}

function ensurePatientForHospitalCase(hospitalCase: HospitalCaseWithUUID): Patient {
  const existing = patients.find(
    (patient) =>
      patient.firstName === hospitalCase.firstName &&
      patient.lastName === hospitalCase.lastName &&
      patient.birthDate === hospitalCase.birthDate,
  );

  if (existing) {
    return existing;
  }

  const patient: Patient = {
    patientId: `P-${nanoid(6)}`,
    firstName: hospitalCase.firstName,
    lastName: hospitalCase.lastName,
    birthDate: hospitalCase.birthDate,
  };

  patients.push(patient);
  return patient;
}

export function buildPatientVerifier(patient: Patient) {
  const birthDateString = patient.birthDate.toISOString().split('T')[0];
  const [year, month, day] = birthDateString.split('-');
  const initials = `${patient.firstName.charAt(0)}${patient.lastName.charAt(0)}`.toUpperCase();
  const birthPortion = `${day ?? '01'}${month ?? '01'}`;

  return `${initials.charAt(0)}${birthPortion}${initials.charAt(1) || 'X'}`;
}

export function createCaseFromHospital(hospitalCaseId: string) {
  const hospitalCase = findHospitalCase(hospitalCaseId);
  if (!hospitalCase) {
    return undefined;
  }

  const existingCase = cases.find((item) => item.hospitalCaseId === hospitalCaseId);
  if (existingCase) {
    const patient = findPatient(existingCase.patientId);
    return { created: false, caseRecord: existingCase, patient: patient ?? null, hospitalCase };
  }

  const patient = ensurePatientForHospitalCase(hospitalCase);

  const caseRecord: CaseRecord = {
    caseId: `IC-${nanoid(6)}`,
    patientId: patient.patientId,
    hospitalCaseId,
    status: 'active',
    caseToken: `case-token-${nanoid(10)}`,
  };

  cases.push(caseRecord);

  return { created: true, caseRecord, patient, hospitalCase };
}

export function verifyCaseToken(caseToken: string) {
  const caseRecord = findCaseByToken(caseToken);
  if (!caseRecord) {
    return undefined;
  }

  const patient = findPatient(caseRecord.patientId);
  if (!patient) {
    return undefined;
  }

  const patientVerifier = buildPatientVerifier(patient);

  return { caseRecord, patientVerifier };
}
