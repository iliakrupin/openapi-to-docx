# Template for API documentation generation based on openapi.json

This file contains the **complete template** that should be used when generating API documentation.  

---

# 📘 **API Documentation Template**

## **INTERACTION INTERFACES — <Group_Name/Tag>**

The document is generated for each tag from OpenAPI.  
If there are no tags — a general header is used:  
**INTERACTION INTERFACES — API**

---

# ## **<Number>. <Method Name (summary / operationId)>**

*(The name is not translated, taken from OpenAPI.)*

---

## **1. Description**

Brief description of the method's purpose.  
Based on `description` from OpenAPI.  
If absent — generated based on URL and operation type.

---

## **2. Interface Requirements**

| Parameter | Value |
|-----------|-------|
| Synchronous/Asynchronous | |
| Technology | REST API (HTTP request–response) |
| Response Time | Not more than 1 second |
| Response Format | JSON |
| Encoding | UTF-8 |
| Authentication | OAuth2PasswordBearer (if different in OpenAPI — specify) |

---

## **3. Request Format**

| Field | Value |
|-------|-------|
| **URL** | `<full path>` |
| **Method** | `<HTTP method>` |

---

## **4. Request Parameters**

General table of all parameters: path, query, header, cookie, body.

| Name | Where | Type | Description | Required |
|------|-------|------|-------------|----------|
| `<field>` | path/query/header/cookie/body | `<type>` | `<description>` | Yes/No |

If the method accepts `requestBody`, add rows:

- `—` | body | object | Request body | Yes/No  
and then — object fields (if needed):

| `<body.field>` | body | `<type>` | `<description>` | Yes/No |

---

## **5. Response Format**

Table of fields of the main response object (`200` or `201`):

| Field | Type | Description |
|-------|------|-------------|
| `<response.field>` | `<type>` | `<description>` |

If the response is an array: the array element object is described.

If absent in OpenAPI — add:

| errorCode | Integer | Error code (0 — no error) |
| errorMessage | String | Error message |

---

## **6. Request Example (JSON)**

```json
{
  "field": "value",
  "another": 123
}
```

If GET and no body — you can provide a query format example:

```json
{
  "limit": 10,
  "offset": 0
}
```

---

## **7. Response Example (JSON)**

```json
{
  "id": 123,
  "name": "example",
  "errorCode": 0,
  "errorMessage": ""
}
```

For arrays:

```json
[
  {
    "id": 1,
    "name": "item1"
  },
  {
    "id": 2,
    "name": "item2"
  }
]
```

---

## **8. Error Examples**

```json
{
  "error": "Invalid request",
  "code": 400
}
```

```json
{
  "error": "Unauthorized",
  "code": 401
}
```

```json
{
  "error": "Internal server error",
  "code": 500
}
```

---

