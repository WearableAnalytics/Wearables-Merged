# PatientsApi

All URIs are relative to *https://api.example.com/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**patientsGet**](PatientsApi.md#patientsget) | **GET** /patients | List internal patients |
| [**patientsPatientIdCasesGet**](PatientsApi.md#patientspatientidcasesget) | **GET** /patients/{patientId}/cases | List cases for a patient |
| [**patientsPatientIdGet**](PatientsApi.md#patientspatientidget) | **GET** /patients/{patientId} | Get a single patient |



## patientsGet

> Array&lt;Patient&gt; patientsGet()

List internal patients

Returns a list of all internal patients

### Example

```ts
import {
  Configuration,
  PatientsApi,
} from '';
import type { PatientsGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new PatientsApi();

  try {
    const data = await api.patientsGet();
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

[**Array&lt;Patient&gt;**](Patient.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | List of patients retrieved successfully |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## patientsPatientIdCasesGet

> Array&lt;Case&gt; patientsPatientIdCasesGet(patientId)

List cases for a patient

Returns all cases linked to a specific patient

### Example

```ts
import {
  Configuration,
  PatientsApi,
} from '';
import type { PatientsPatientIdCasesGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new PatientsApi();

  const body = {
    // string | Internal patient identifier
    patientId: P-98765,
  } satisfies PatientsPatientIdCasesGetRequest;

  try {
    const data = await api.patientsPatientIdCasesGet(body);
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
| **patientId** | `string` | Internal patient identifier | [Defaults to `undefined`] |

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
| **404** | Patient not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## patientsPatientIdGet

> Patient patientsPatientIdGet(patientId)

Get a single patient

Returns a single internal patient by ID

### Example

```ts
import {
  Configuration,
  PatientsApi,
} from '';
import type { PatientsPatientIdGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new PatientsApi();

  const body = {
    // string | Internal patient identifier
    patientId: P-98765,
  } satisfies PatientsPatientIdGetRequest;

  try {
    const data = await api.patientsPatientIdGet(body);
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
| **patientId** | `string` | Internal patient identifier | [Defaults to `undefined`] |

### Return type

[**Patient**](Patient.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Patient retrieved successfully |  -  |
| **404** | Patient not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)

