"""
OpenAPI specification parser per OpenAPI 3.0 spec.
Extracts and processes operations, parameters, schemas, and examples.
"""
import logging
from typing import Any, Dict, List, Optional

from src.config import HTTP_METHODS
from src.utils.schema_resolver import resolve_schema, get_schema_type

logger = logging.getLogger(__name__)

def group_operations_by_tag(openapi_spec: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group operations by tags per OpenAPI 3.0 spec section 3.1.0.
    Operations without tags use default tag "API".
    """
    paths = openapi_spec.get("paths", {})
    if not paths:
        return {}

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    default_tag = "API"

    for path, path_item in paths.items():
        # Validate path format per OpenAPI 3.0 spec section 3.1.0
        if not isinstance(path_item, dict):
            logger.warning(f"Skipping invalid path item for '{path}': expected object")
            continue
        
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS:
                continue
            
            if not isinstance(operation, dict):
                logger.warning(f"Skipping invalid operation for {method.upper()} {path}: expected object")
                continue

            tags = operation.get("tags") or [default_tag]
            for tag in tags:
                grouped.setdefault(tag, []).append(
                    {"path": path, "method": method.upper(), "operation": operation}
                )

    return grouped

def count_endpoints(openapi_spec: Dict[str, Any]) -> int:
    """
    Count every HTTP method defined in the OpenAPI specification.
    Per OpenAPI 3.0 spec section 3.1.0, supports all standard HTTP methods.

    Args:
        openapi_spec: Parsed OpenAPI specification.

    Returns:
        int: Total number of endpoints.
    """
    count = 0
    paths = openapi_spec.get("paths", {})
    for path_data in paths.values():
        for method in HTTP_METHODS:
            if method in path_data:
                count += 1
    return count

def determine_authentication(operation: Dict[str, Any], openapi_spec: Dict[str, Any]) -> str:
    """
    Определить схему аутентификации из операции или глобального раздела security.
    """
    security = operation.get("security")
    if security is None:
        security = openapi_spec.get("security")

    if not security:
        return "OAuth2PasswordBearer"

    scheme_name = next(iter(security[0].keys()), None)
    if not scheme_name:
        return "OAuth2PasswordBearer"

    security_schemes = openapi_spec.get("components", {}).get("securitySchemes", {})
    scheme = security_schemes.get(scheme_name, {})
    return scheme.get("scheme") or scheme.get("type") or scheme_name

def determine_interface_mode(operation: Dict[str, Any], openapi_spec: Dict[str, Any]) -> str:
    """
    Определить режим интерфейса (синхронный/асинхронный) на основе расширений или описания.
    """
    candidates = [
        operation.get("x-interface-mode"),
        operation.get("x_interface_mode"),
        operation.get("x-interface-type"),
        operation.get("x-interface"),
        operation.get("x-mode"),
        openapi_spec.get("x-interface-mode"),
        openapi_spec.get("info", {}).get("x-interface-mode"),
    ]

    for candidate in candidates:
        normalized = normalize_interface_mode(candidate)
        if normalized:
            return normalized

    text_blob = " ".join(
        filter(
            None,
            [
                operation.get("description", ""),
                operation.get("summary", ""),
                operation.get("operationId", ""),
            ],
        )
    ).lower()

    if any(keyword in text_blob for keyword in ("async", "асинхрон")):
        return "Асинхронный"

    return "Синхронный"

def normalize_interface_mode(value: Optional[Any]) -> Optional[str]:
    """
    Привести произвольное значение режима к ожидаемому формату.
    """
    if value is None:
        return None

    raw = str(value).strip().lower()
    if not raw:
        return None

    sync_aliases = {"sync", "synchronous", "синхронный", "синхрон"}
    async_aliases = {"async", "asynchronous", "асинхронный", "асинхрон"}

    if raw in sync_aliases:
        return "Синхронный"
    if raw in async_aliases:
        return "Асинхронный"

    return raw.capitalize()

def build_parameter_rows(operation: Dict[str, Any], openapi_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Собрать сведения о параметрах пути, запроса, заголовков и тела.
    """
    rows: List[Dict[str, Any]] = []

    for parameter in operation.get("parameters", []):
        schema = resolve_schema(parameter.get("schema", {}), openapi_spec)
        rows.append(
            {
                "name": parameter.get("name", "-"),
                "in": parameter.get("in", "-"),
                "type": get_schema_type(schema),
                "description": parameter.get("description", "Нет описания"),
                "required": parameter.get("required", False),
            }
        )

    request_body = operation.get("requestBody")
    if request_body:
        required = request_body.get("required", False)
        content = request_body.get("content", {})
        for media_type, media in content.items():
            schema = resolve_schema(media.get("schema", {}), openapi_spec)
            rows.append(
                {
                    "name": "—",
                    "in": "body",
                    "type": get_schema_type(schema),
                    "description": media.get("description", "Тело запроса"),
                    "required": required,
                }
            )
            rows.extend(
                extract_schema_properties(
                    schema=schema,
                    openapi_spec=openapi_spec,
                    location="body",
                    parent_name="body",
                )
            )

    return rows

def get_success_response_schema(operation: Dict[str, Any], openapi_spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Извлечь схему основного успешного ответа (200/201/2xx).
    """
    responses = operation.get("responses", {})
    response = None
    for status in ("200", "201", "202"):
        if status in responses:
            response = responses[status]
            break

    if response is None:
        for status_code, resp in responses.items():
            if status_code.startswith("2"):
                response = resp
                break

    if not response:
        return None

    content = response.get("content", {})
    for media in content.values():
        schema = resolve_schema(media.get("schema", {}), openapi_spec)
        if schema:
            return schema

    return None

def describe_schema_fields(schema: Optional[Dict[str, Any]], openapi_spec: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Описать поля схемы ответа для таблицы.
    """
    if not schema:
        return []

    resolved = resolve_schema(schema, openapi_spec)
    schema_type = get_schema_type(resolved)

    if schema_type == "object":
        properties = resolved.get("properties", {})
        if not properties:
            return [{"name": "result", "type": "object", "description": resolved.get("description", "Ответ сервиса")}]

        fields = []
        for name, prop_schema in properties.items():
            resolved_prop = resolve_schema(prop_schema, openapi_spec)
            fields.append(
                {
                    "name": name,
                    "type": get_schema_type(resolved_prop),
                    "description": resolved_prop.get("description", "Нет описания"),
                }
            )
        return fields

    if schema_type == "array":
        item_schema = resolve_schema(resolved.get("items", {}), openapi_spec)
        return [
            {
                "name": "items[]",
                "type": f"array<{get_schema_type(item_schema)}>",
                "description": resolved.get("description", "Список элементов"),
            }
        ]

    return [
        {
            "name": "value",
            "type": schema_type,
            "description": resolved.get("description", "Ответ сервиса"),
        }
    ]

def extract_schema_properties(
    schema: Dict[str, Any],
    openapi_spec: Dict[str, Any],
    location: str,
    parent_name: str,
) -> List[Dict[str, Any]]:
    """
    Получить список полей схемы (используется для описания requestBody).
    """
    resolved = resolve_schema(schema, openapi_spec)
    schema_type = get_schema_type(resolved)

    if schema_type != "object":
        return []

    properties = resolved.get("properties", {})
    required_fields = set(resolved.get("required", []))
    rows: List[Dict[str, Any]] = []

    for name, prop_schema in properties.items():
        resolved_prop = resolve_schema(prop_schema, openapi_spec)
        rows.append(
            {
                "name": f"{parent_name}.{name}",
                "in": location,
                "type": get_schema_type(resolved_prop),
                "description": resolved_prop.get("description", "Нет описания"),
                "required": name in required_fields,
            }
        )

    return rows

def build_request_example(operation: Dict[str, Any], openapi_spec: Dict[str, Any]) -> Any:
    """
    Build request example per OpenAPI 3.0 spec section 3.1.0.
    Prefers 'examples' over deprecated 'example' field.
    """
    request_body = operation.get("requestBody")
    if request_body:
        content = request_body.get("content", {})
        for media in content.values():
            # Prefer 'examples' over deprecated 'example' (per OpenAPI spec)
            examples = media.get("examples")
            if examples:
                example_value = next(iter(examples.values()))
                if isinstance(example_value, dict):
                    return example_value.get("value")
                return example_value
            
            # Fallback to deprecated 'example' field
            if "example" in media:
                logger.debug("Using deprecated 'example' field. Consider using 'examples' instead.")
                return media["example"]
            
            # Generate from schema if no examples provided
            schema = resolve_schema(media.get("schema", {}), openapi_spec)
            if schema:
                return build_example_from_schema(schema, openapi_spec)

    params_example = {}
    for parameter in operation.get("parameters", []):
        schema = resolve_schema(parameter.get("schema", {}), openapi_spec)
        params_example[parameter.get("name", "param")] = build_example_from_schema(schema, openapi_spec)

    return params_example or {"example": "value"}

def build_response_example(operation: Dict[str, Any], openapi_spec: Dict[str, Any]) -> Any:
    """
    Build response example per OpenAPI 3.0 spec section 3.1.0.
    Prioritizes 2xx status codes and prefers 'examples' over deprecated 'example'.
    """
    responses = operation.get("responses", {})
    # Prioritize 2xx status codes per OpenAPI best practices
    for status in ("200", "201", "202"):
        if status in responses:
            response = responses[status]
            break
    else:
        # Fallback to any 2xx response
        for status_code, resp in responses.items():
            if status_code.startswith("2"):
                response = resp
                break
        else:
            response = next(iter(responses.values()), None)

    if not response:
        return {"errorCode": 0, "errorMessage": ""}

    content = response.get("content", {})
    for media in content.values():
        # Prefer 'examples' over deprecated 'example' (per OpenAPI spec)
        examples = media.get("examples")
        if examples:
            example_value = next(iter(examples.values()))
            if isinstance(example_value, dict):
                return example_value.get("value")
            return example_value
        
        # Fallback to deprecated 'example' field
        if "example" in media:
            logger.debug("Using deprecated 'example' field. Consider using 'examples' instead.")
            return media["example"]
        
        # Generate from schema if no examples provided
        schema = resolve_schema(media.get("schema", {}), openapi_spec)
        if schema:
            return build_example_from_schema(schema, openapi_spec)

    return {"errorCode": 0, "errorMessage": ""}

def build_example_from_schema(schema: Optional[Dict[str, Any]], openapi_spec: Dict[str, Any]) -> Any:
    """
    Построить пример значения на основе схемы.
    """
    resolved = resolve_schema(schema or {}, openapi_spec)
    if "example" in resolved:
        return resolved["example"]

    schema_type = get_schema_type(resolved)

    if schema_type == "object":
        example = {}
        for name, prop_schema in resolved.get("properties", {}).items():
            example[name] = build_example_from_schema(prop_schema, openapi_spec)
        return example or {}

    if schema_type == "array":
        item_schema = resolved.get("items", {})
        return [build_example_from_schema(item_schema, openapi_spec)]

    if "enum" in resolved:
        return resolved["enum"][0]

    defaults = {
        "string": "string",
        "integer": 0,
        "number": 0,
        "boolean": True,
    }
    return defaults.get(schema_type, "value")

