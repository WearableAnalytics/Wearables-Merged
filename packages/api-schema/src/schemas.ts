import { z } from 'zod';
import {
  extendZodWithOpenApi,
  OpenAPIRegistry,
  OpenApiGeneratorV3,
} from '@asteasolutions/zod-to-openapi';

extendZodWithOpenApi(z);

export const registry = new OpenAPIRegistry();

// Components
export const ChariteCaseSchema = registry.register(
  'ChariteCase',
  z
    .object({
      cCaseId: z.string().describe('Charité case identifier').openapi({ example: 'C-123456' }),
      firstName: z.string().describe('Patient first name').openapi({ example: 'Max' }),
      lastName: z.string().describe('Patient last name').openapi({ example: 'Mustermann' }),
      birthDate: z
        .string()
        .describe('Patient date of birth')
        .openapi({ format: 'date', example: '1980-01-01' }),
    })
    .describe('External read-only Charité case')
    .strict(),
);

export const PatientSchema = registry.register(
  'Patient',
  z
    .object({
      patientId: z.string().describe('Internal patient identifier').openapi({ example: 'P-98765' }),
      firstName: z.string().describe('Patient first name').openapi({ example: 'Max' }),
      lastName: z.string().describe('Patient last name').openapi({ example: 'Mustermann' }),
      birthDate: z
        .string()
        .describe('Patient date of birth')
        .openapi({ format: 'date', example: '1980-01-01' }),
    })
    .describe('Internal patient')
    .strict(),
);

const caseStatusSchema = z.enum(['active', 'inactive']).describe('Case status').openapi({
  example: 'active',
});

export const CaseSchema = registry.register(
  'Case',
  z
    .object({
      caseId: z.string().describe('Internal case identifier').openapi({ example: 'IC-54321' }),
      patientId: z.string().describe('Associated patient identifier').openapi({ example: 'P-98765' }),
      cCaseId: z
        .string()
        .describe('Original Charité case identifier')
        .openapi({ example: 'C-123456' })
        .optional(),
      status: caseStatusSchema,
      caseToken: z
        .string()
        .nullable()
        .describe('JWT token for case access')
        .openapi({ example: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...' })
        .optional(),
    })
    .describe('Internal case')
    .strict(),
);

export const CaseCreatedSchema = registry.register(
  'CaseCreated',
  z
    .object({
      patientId: z.string().describe('Internal patient identifier').openapi({ example: 'P-98765' }),
      caseId: z.string().describe('Internal case identifier').openapi({ example: 'IC-54321' }),
      caseToken: z
        .string()
        .describe('JWT token for case access')
        .openapi({ example: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...' }),
    })
    .describe('Response after case creation')
    .strict(),
);

export const CaseVerifiedSchema = registry.register(
  'CaseVerified',
  z
    .object({
      caseId: z.string().describe('Internal case identifier').openapi({ example: 'IC-54321' }),
      patientVerifier: z
        .string()
        .describe(
          'Patient verification string built from first letter of first name, birthdate (DDMM), and first letter of last name.',
        )
        .openapi({ example: 'M0212B' }),
      status: caseStatusSchema,
    })
    .describe('Response after token verification')
    .strict(),
);

export const ErrorSchema = registry.register(
  'Error',
  z
    .object({
      message: z.string().describe('Error message').openapi({ example: 'Resource not found' }),
      code: z.string().describe('Error code').openapi({ example: 'NOT_FOUND' }).optional(),
    })
    .describe('Error response')
    .strict(),
);

// Request bodies
const CreateCaseFromChariteBodySchema = z
  .object({
    cCaseId: z
      .string()
      .describe('Charité case identifier')
      .openapi({ example: 'C-123456' }),
  })
  .describe('Create internal case from Charité case payload')
  .strict();

const VerifyCaseTokenBodySchema = z
  .object({
    caseToken: z
      .string()
      .describe('JWT case token')
      .openapi({ example: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpX...' }),
  })
  .describe('Verify case token payload')
  .strict();

// Paths
registry.registerPath({
  method: 'get',
  path: '/charite/cases/{cCaseId}',
  tags: ['Charité Cases'],
  summary: 'Get a Charité case',
  description: 'Returns a read-only Charité case by ID',
  request: {
    params: z.object({
      cCaseId: z
        .string()
        .describe('Charité case identifier')
        .openapi({ example: 'C-123456' }),
    }),
  },
  responses: {
    200: {
      description: 'Charité case retrieved successfully',
      content: { 'application/json': { schema: ChariteCaseSchema } },
    },
    404: {
      description: 'Charité case not found',
      content: { 'application/json': { schema: ErrorSchema } },
    },
  },
});

registry.registerPath({
  method: 'get',
  path: '/patients',
  tags: ['Patients'],
  summary: 'List internal patients',
  description: 'Returns a list of all internal patients',
  responses: {
    200: {
      description: 'List of patients retrieved successfully',
      content: { 'application/json': { schema: z.array(PatientSchema) } },
    },
  },
});

registry.registerPath({
  method: 'get',
  path: '/patients/{patientId}',
  tags: ['Patients'],
  summary: 'Get a single patient',
  description: 'Returns a single internal patient by ID',
  request: {
    params: z.object({
      patientId: z
        .string()
        .describe('Internal patient identifier')
        .openapi({ example: 'P-98765' }),
    }),
  },
  responses: {
    200: {
      description: 'Patient retrieved successfully',
      content: { 'application/json': { schema: PatientSchema } },
    },
    404: {
      description: 'Patient not found',
      content: { 'application/json': { schema: ErrorSchema } },
    },
  },
});

registry.registerPath({
  method: 'get',
  path: '/patients/{patientId}/cases',
  tags: ['Patients'],
  summary: 'List cases for a patient',
  description: 'Returns all cases linked to a specific patient',
  request: {
    params: z.object({
      patientId: z
        .string()
        .describe('Internal patient identifier')
        .openapi({ example: 'P-98765' }),
    }),
  },
  responses: {
    200: {
      description: 'List of cases retrieved successfully',
      content: { 'application/json': { schema: z.array(CaseSchema) } },
    },
    404: {
      description: 'Patient not found',
      content: { 'application/json': { schema: ErrorSchema } },
    },
  },
});

registry.registerPath({
  method: 'get',
  path: '/cases',
  tags: ['Cases'],
  summary: 'List all internal cases',
  description: 'Returns a list of all internal cases',
  responses: {
    200: {
      description: 'List of cases retrieved successfully',
      content: { 'application/json': { schema: z.array(CaseSchema) } },
    },
  },
});

registry.registerPath({
  method: 'get',
  path: '/cases/{caseId}',
  tags: ['Cases'],
  summary: 'Get a single case',
  description: 'Returns a single internal case by ID',
  request: {
    params: z.object({
      caseId: z
        .string()
        .describe('Internal case identifier')
        .openapi({ example: 'IC-54321' }),
    }),
  },
  responses: {
    200: {
      description: 'Case retrieved successfully',
      content: { 'application/json': { schema: CaseSchema } },
    },
    404: {
      description: 'Case not found',
      content: { 'application/json': { schema: ErrorSchema } },
    },
  },
});

registry.registerPath({
  method: 'post',
  path: '/cases/from-charite-case',
  tags: ['Cases'],
  summary: 'Create internal case from Charité case',
  description:
    'Creates an internal case from an external Charité case with the specified conflict-resolution rules.',
  request: {
    body: {
      required: true,
      content: {
        'application/json': {
          schema: CreateCaseFromChariteBodySchema,
        },
      },
    },
  },
  responses: {
    201: {
      description: 'Case created successfully',
      content: { 'application/json': { schema: CaseCreatedSchema } },
    },
    200: {
      description: 'Case already exists',
      content: { 'application/json': { schema: CaseCreatedSchema } },
    },
    400: {
      description: 'Invalid input',
      content: { 'application/json': { schema: ErrorSchema } },
    },
    404: {
      description: 'Charité case not found',
      content: { 'application/json': { schema: ErrorSchema } },
    },
  },
});

registry.registerPath({
  method: 'post',
  path: '/cases/verify-token',
  tags: ['Cases'],
  summary: 'Verify a case token',
  description: 'Verifies a case token and returns the linked case information',
  request: {
    body: {
      required: true,
      content: {
        'application/json': {
          schema: VerifyCaseTokenBodySchema,
        },
      },
    },
  },
  responses: {
    200: {
      description: 'Token verified successfully',
      content: { 'application/json': { schema: CaseVerifiedSchema } },
    },
    401: {
      description: 'Invalid or expired token',
      content: { 'application/json': { schema: ErrorSchema } },
    },
  },
});

export function generateOpenApiDocument() {
  const generator = new OpenApiGeneratorV3(registry.definitions);
  return generator.generateDocument({
    openapi: '3.0.3',
    info: {
      title: 'Patient & Case API',
      version: '1.0.0',
      description: `Endpoints for fetching read-only Charité cases and managing internal patients/cases.

## Frontend Flow
1. Enter a Charité case ID (cCaseId)
2. Fetch and display the external Charité case
3. User clicks "Create Case" to create an internal case
4. Show that patient/case was created and store the caseId
5. Display the case token as QR code for scanning in the Charité app

## Existing Patient Access
1. Fetch all internal patients/cases
2. User selects a patient/case to view details
3. Display case details and show case token as QR code

## App Flow
1. Receive a caseToken scanned from Charité app
2. Fetch the internal case using POST /cases/verify-token
3. Display case details
4. Allow user to proceed with further actions`,
      contact: { name: 'API Support' },
    },
    servers: [{ url: 'https://api.example.com/v1', description: 'Production server' }],
    tags: [
      { name: 'Charité Cases', description: 'Read-only external Charité cases' },
      { name: 'Patients', description: 'Internal patient management' },
      { name: 'Cases', description: 'Internal case management' },
    ],
  });
}
