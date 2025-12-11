# API Schema

`src/schemas.ts` is the single source of truth (Zod + zod-to-openapi). Generate OpenAPI output from it when needed.

## Generate OpenAPI schema

From this package directory:

```bash
npm run generate:api-schema
```

This writes `openapi.json` (update the script if you prefer YAML). Commit the generated file only if something downstream consumes it from git; otherwise keep it ignored and regenerate on demand.***
