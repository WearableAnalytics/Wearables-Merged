# HospitalCasesApi

All URIs are relative to *https://api.example.com/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**hospitalCasesHospitalCaseIdGet**](HospitalCasesApi.md#hospitalcaseshospitalcaseidget) | **GET** /hospital/cases/{hospitalCaseId} | Get a Hospital case |



## hospitalCasesHospitalCaseIdGet

> HospitalCase hospitalCasesHospitalCaseIdGet(hospitalCaseId)

Get a Hospital case

Returns a read-only Hospital case by ID

### Example

```ts
import {
  Configuration,
  HospitalCasesApi,
} from '';
import type { HospitalCasesHospitalCaseIdGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new HospitalCasesApi();

  const body = {
    // string | Hospital case identifier
    hospitalCaseId: C-123456,
  } satisfies HospitalCasesHospitalCaseIdGetRequest;

  try {
    const data = await api.hospitalCasesHospitalCaseIdGet(body);
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
| **hospitalCaseId** | `string` | Hospital case identifier | [Defaults to `undefined`] |

### Return type

[**HospitalCase**](HospitalCase.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Hospital case retrieved successfully |  -  |
| **404** | Hospital case not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)

