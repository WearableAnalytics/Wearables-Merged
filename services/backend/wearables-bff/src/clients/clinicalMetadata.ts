import { actorQuery, isUuid } from './caseAccess.js';
import { controlRequest, ControlApiError } from './controlApi.js';
import type { JwtPayload } from '../middleware.js';

export type ClinicalMetadata = {
  id: string;
  patient_id: string;
  status: string;
  patient: { id: string; name: string; dob: string | null };
};

function checked(row: ClinicalMetadata): ClinicalMetadata {
  if (
    !row ||
    !isUuid(row.id) ||
    !isUuid(row.patient_id) ||
    !row.patient ||
    row.patient.id !== row.patient_id ||
    typeof row.patient.name !== 'string' ||
    row.patient.name.length > 256 ||
    !(row.patient.dob === null || typeof row.patient.dob === 'string') ||
    !['PLANNED', 'ONGOING', 'COMPLETED', 'ARCHIVED', 'OTHER'].includes(row.status)
  )
    throw new ControlApiError(503);
  return row;
}

export async function clinicalCase(user: JwtPayload, caseId: string): Promise<ClinicalMetadata> {
  if (!isUuid(caseId)) throw new ControlApiError(422);
  const value = checked(
    await controlRequest<ClinicalMetadata>(`/clinical-cases/${caseId}?${actorQuery(user)}`),
  );
  if (value.id !== caseId) throw new ControlApiError(503);
  return value;
}

export async function clinicalCases(
  user: JwtPayload,
  patientId?: string,
  firstOnly = false,
): Promise<ClinicalMetadata[]> {
  if (patientId !== undefined && !isUuid(patientId)) throw new ControlApiError(422);
  const rows: ClinicalMetadata[] = [];
  let after: string | null = null;
  for (let page = 0; page < 10; page++) {
    const query = new URLSearchParams(actorQuery(user));
    query.set('limit', firstOnly ? '1' : '100');
    if (patientId) query.set('patient_id', patientId);
    if (after) query.set('after', after);
    const value = await controlRequest<{ items: ClinicalMetadata[]; next_cursor: string | null }>(
      `/clinical-cases?${query}`,
    );
    if (
      !value ||
      !Array.isArray(value.items) ||
      value.items.length > (firstOnly ? 1 : 100) ||
      (value.next_cursor !== null &&
        (!isUuid(value.next_cursor) || (after !== null && value.next_cursor <= after)))
    )
      throw new ControlApiError(503);
    for (const item of value.items) {
      checked(item);
      if (
        (patientId && item.patient_id !== patientId) ||
        (after && item.id <= after) ||
        rows.some((row) => row.id === item.id)
      )
        throw new ControlApiError(503);
      rows.push(item);
    }
    if (firstOnly || value.next_cursor === null) return rows;
    after = value.next_cursor;
  }
  throw new ControlApiError(503, 'CASE_LIST_LIMIT');
}
