# CasesApi

All URIs are relative to *https://api.example.com/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**casesCaseIdGet**](CasesApi.md#casescaseidget) | **GET** /cases/{caseId} | Get a single case |
| [**casesFromHospitalCasePost**](CasesApi.md#casesfromhospitalcasepostoperation) | **POST** /cases/from-hospital-case | Create internal case from Hospital case |
| [**casesGet**](CasesApi.md#casesget) | **GET** /cases | List all internal cases |
| [**casesVerifyTokenPost**](CasesApi.md#casesverifytokenpostoperation) | **POST** /cases/verify-token | Verify a case token |



## casesCaseIdGet

> Case casesCaseIdGet(caseId)

Get a single case

Returns a single internal case by ID

### Example

```ts
import {
  Configuration,
  CasesApi,
} from '';
import type { CasesCaseIdGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new CasesApi();

  const body = {
    // string | Internal case identifier
    caseId: IC-54321,
  } satisfies CasesCaseIdGetRequest;

  try {
    const data = await api.casesCaseIdGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **caseId** | `string` | Internal case identifier | [Defaults to `undefined`] |

### Return type

[**Case**](Case.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Case retrieved successfully |  -  |
| **404** | Case not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## casesFromHospitalCasePost

> CaseCreated casesFromHospitalCasePost(casesFromHospitalCasePostRequest)

Create internal case from Hospital case

Creates an internal case from an external Hospital case with the specified conflict-resolution rules.

### Example

```ts
import {
  Configuration,
  CasesApi,
} from '';
import type { CasesFromHospitalCasePostOperationRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new CasesApi();

  const body = {
    // CasesFromHospitalCasePostRequest
    casesFromHospitalCasePostRequest: ...,
  } satisfies CasesFromHospitalCasePostOperationRequest;

  try {
    const data = await api.casesFromHospitalCasePost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **casesFromHospitalCasePostRequest** | [CasesFromHospitalCasePostRequest](CasesFromHospitalCasePostRequest.md) |  | |

### Return type

[**CaseCreated**](CaseCreated.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Case already exists |  -  |
| **201** | Case created successfully |  -  |
| **400** | Invalid input |  -  |
| **404** | Hospital case not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## casesGet

> Array&lt;Case&gt; casesGet()

List all internal cases

Returns a list of all internal cases

### Example

```ts
import {
  Configuration,
  CasesApi,
} from '';
import type { CasesGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new CasesApi();

  try {
    const data = await api.casesGet();
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters

This endpoint does not need any parameter.

### Return type

[**Array&lt;Case&gt;**](Case.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | List of cases retrieved successfully |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## casesVerifyTokenPost

> CaseVerified casesVerifyTokenPost(casesVerifyTokenPostRequest)

Verify a case token

Verifies a case token and returns the linked case information

### Example

```ts
import {
  Configuration,
  CasesApi,
} from '';
import type { CasesVerifyTokenPostOperationRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new CasesApi();

  const body = {
    // CasesVerifyTokenPostRequest
    casesVerifyTokenPostRequest: ...,
  } satisfies CasesVerifyTokenPostOperationRequest;

  try {
    const data = await api.casesVerifyTokenPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **casesVerifyTokenPostRequest** | [CasesVerifyTokenPostRequest](CasesVerifyTokenPostRequest.md) |  | |

### Return type

[**CaseVerified**](CaseVerified.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Token verified successfully |  -  |
| **401** | Invalid or expired token |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)

