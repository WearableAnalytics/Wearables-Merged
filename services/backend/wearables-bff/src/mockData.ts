import { nanoid } from 'nanoid';
import type { Case, ChariteCase, Patient } from './api/openapi-client/models';

export type CaseStatus = Case['status'];
export type CaseRecord = Case;

interface ChariteCaseWithUUID extends ChariteCase {
  uuid: string;
}

const chariteCases: ChariteCaseWithUUID[] = [
  { 
    cCaseId: 'C-123456', 
    uuid: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    firstName: 'Max', 
    lastName: 'Mustermann', 
    birthDate: new Date('1980-01-01'), 
    sex: 'male', 
    weight: 82.5 
  },
  { 
    cCaseId: 'C-654321', 
    uuid: 'b2c3d4e5-f6a7-8901-bcde-f12345678901',
    firstName: 'Jane', 
    lastName: 'Doe', 
    birthDate: new Date('1975-05-20'), 
    sex: 'female', 
    weight: 68.0 
  },
    { 
    cCaseId: 'C-000000', 
    uuid: 'd2c3d4e5-f6a7-8901-bbbb-f12345678901',
    firstName: 'Blubb', 
    lastName: 'Doe', 
    birthDate: new Date('1975-05-20'), 
    sex: 'female', 
    weight: 68.0 
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
    cCaseId: 'C-123456',
    status: 'active',
    caseToken: 'token-12345',
  },
  { caseId: 'IC-13579', patientId: 'P-24680', status: 'inactive', caseToken: 'token-24680' },
];

export function findChariteCase(cCaseId: string): ChariteCaseWithUUID | undefined {
  return chariteCases.find((item) => item.cCaseId === cCaseId);
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

function ensurePatientForChariteCase(chariteCase: ChariteCaseWithUUID): Patient {
  const existing = patients.find(
    (patient) =>
      patient.firstName === chariteCase.firstName &&
      patient.lastName === chariteCase.lastName &&
      patient.birthDate === chariteCase.birthDate,
  );

  if (existing) {
    return existing;
  }

  const patient: Patient = {
    patientId: `P-${nanoid(6)}`,
    firstName: chariteCase.firstName,
    lastName: chariteCase.lastName,
    birthDate: chariteCase.birthDate,
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

export function createCaseFromCharite(cCaseId: string) {
  const chariteCase = findChariteCase(cCaseId);
  if (!chariteCase) {
    return undefined;
  }

  const existingCase = cases.find((item) => item.cCaseId === cCaseId);
  if (existingCase) {
    const patient = findPatient(existingCase.patientId);
    return { created: false, caseRecord: existingCase, patient: patient ?? null, chariteCase };
  }

  const patient = ensurePatientForChariteCase(chariteCase);

  const caseRecord: CaseRecord = {
    caseId: `IC-${nanoid(6)}`,
    patientId: patient.patientId,
    cCaseId,
    status: 'active',
    caseToken: `case-token-${nanoid(10)}`,
  };

  cases.push(caseRecord);

  return { created: true, caseRecord, patient, chariteCase };
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
