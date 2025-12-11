
# CaseVerified

Response after token verification

## Properties

Name | Type
------------ | -------------
`caseId` | string
`patientVerifier` | string
`status` | string

## Example

```typescript
import type { CaseVerified } from ''

// TODO: Update the object below with actual values
const example = {
  "caseId": IC-54321,
  "patientVerifier": M0212B,
  "status": active,
} satisfies CaseVerified

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as CaseVerified
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


