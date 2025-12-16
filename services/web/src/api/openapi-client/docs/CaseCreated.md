
# CaseCreated


## Properties

Name | Type
------------ | -------------
`patientId` | string
`caseId` | string
`caseToken` | string

## Example

```typescript
import type { CaseCreated } from ''

// TODO: Update the object below with actual values
const example = {
  "patientId": P-98765,
  "caseId": IC-54321,
  "caseToken": eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...,
} satisfies CaseCreated

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as CaseCreated
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


