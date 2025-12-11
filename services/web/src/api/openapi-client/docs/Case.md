
# Case

Internal case

## Properties

Name | Type
------------ | -------------
`caseId` | string
`patientId` | string
`cCaseId` | string
`status` | string
`caseToken` | string

## Example

```typescript
import type { Case } from ''

// TODO: Update the object below with actual values
const example = {
  "caseId": IC-54321,
  "patientId": P-98765,
  "cCaseId": C-123456,
  "status": active,
  "caseToken": eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...,
} satisfies Case

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as Case
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


