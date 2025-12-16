
# Patient


## Properties

Name | Type
------------ | -------------
`patientId` | string
`firstName` | string
`lastName` | string
`birthDate` | Date

## Example

```typescript
import type { Patient } from ''

// TODO: Update the object below with actual values
const example = {
  "patientId": P-98765,
  "firstName": Max,
  "lastName": Mustermann,
  "birthDate": Tue Jan 01 01:00:00 CET 1980,
} satisfies Patient

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as Patient
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


