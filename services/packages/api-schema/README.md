# API Schema

`src/schemas.ts` is the single source of truth (Zod + zod-to-openapi). Generate OpenAPI output from it when needed.

## Generate OpenAPI schema

From this package directory:

```bash
npm run generate:api-schema
```

This writes `openapi.json` (update the script if you prefer YAML). Commit the generated file only if something downstream consumes it from git; otherwise keep it ignored and regenerate on demand.



# Patient & Case API

Endpoints for fetching read-only Hospital cases and managing internal patients/cases.

---

## External Case (read-only)

**GET `/hospital/cases/{hospitalCaseId}`** — returns a Hospital case.

```json
{
  "hospitalCaseId": "C-123456",
  "firstName": "Max",
  "lastName": "Mustermann",
  "birthDate": "1980-01-01",
  ... other case details ...
}
```

---

## Patients

**POST `/patients`** — 

**GET `/patients`** — list internal patients.  
**GET `/patients/{patientId}`** — fetch a single internal patient.
**GET `/patients/{patientId}/cases`** — list cases linked to a patient.  


---

## Cases (internal)

**POST /cases/from-hospital-case** create an internal case from an external case. 
 -  If the patient already exists but not the case: 
    - creates new case
    - links to existing patient
-  If the patient does not exist:
    - creates new patient
    - creates new case
- If both patient and case exist: 
    - return existing case
- Else: return error

Request

```json
{
  "hospitalCaseId": "C-123456"
}
```

Response

```json
{
  "patientId": "P-98765",
  "caseId": "IC-54321",
  "caseToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }
```

**GET `/cases`** — list all internal cases.  
**GET `/cases/{caseId}`** — fetch a single internal case.

**POST `/cases/verify-token`** — verify a case token and return the linked case.
Request

```json
{
  "caseToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
``` 
Response

```json
{
  "caseId": "IC-54321",
  "patientVerifier": "M0212B",
  "status": "active"
}
``` 

the patient verifier is build in the following way: 
assuming we have a patient called Max Bauer with birthdate 02.12.2000, the patient verifier would be "M0212B".

status can either be "active" or "inactive".

---

## Frontend Flow

### New Patient Creation from Hospital Case
1. Enter a Hospital case ID (`hospitalCaseId`).
2. Fetch and display the external Hospital case.
3. User clicks "Create Case" to create an internal case.
4. Show that patient/case was created and store the `caseId`.
5. Display the case token as qr code for scanning in the Hospital app.


### Existing Patient Access

1. Fetch all internal patients/cases (to be decided yet).
2. User selects a patient/case to view details.
    If from patient list: Display their internal cases.
    Let user select a case to view details.
3. Display case details. Show case token as qr code for scanning in the Hospital app.


## App Flow

1. Receive a caseToken scanned from Hospital app.
2. Fetch the internal case using `POST /cases/verify-token` with the caseToken.
3. Display some case details.
4. Allow user to proceed with further actions (out of scope).
