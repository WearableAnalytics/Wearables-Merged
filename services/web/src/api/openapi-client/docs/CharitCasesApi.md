# CharitCasesApi

All URIs are relative to *https://api.example.com/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**chariteCasesCCaseIdGet**](CharitCasesApi.md#charitecasesccaseidget) | **GET** /charite/cases/{cCaseId} | Get a Charité case |



## chariteCasesCCaseIdGet

> ChariteCase chariteCasesCCaseIdGet(cCaseId)

Get a Charité case

Returns a read-only Charité case by ID

### Example

```ts
import {
  Configuration,
  CharitCasesApi,
} from '';
import type { ChariteCasesCCaseIdGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new CharitCasesApi();

  const body = {
    // string | Charité case identifier
    cCaseId: C-123456,
  } satisfies ChariteCasesCCaseIdGetRequest;

  try {
    const data = await api.chariteCasesCCaseIdGet(body);
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
| **cCaseId** | `string` | Charité case identifier | [Defaults to `undefined`] |

### Return type

[**ChariteCase**](ChariteCase.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Charité case retrieved successfully |  -  |
| **404** | Charité case not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)

