"""
OpenAPI specification parser per OpenAPI 3.0 spec.
Extracts and processes operations, parameters, schemas, and examples.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

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

        path_parameters = path_item.get("parameters", [])

        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS:
                continue
            
            if not isinstance(operation, dict):
                logger.warning(f"Skipping invalid operation for {method.upper()} {path}: expected object")
                continue

            tags = operation.get("tags") or [default_tag]
            for tag in tags:
                grouped.setdefault(tag, []).append(
                    {
                        "path": path,
                        "method": method.upper(),
                        "operation": operation,
                        "path_item": path_item,
                        "path_parameters": path_parameters,
                    }
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
        return "Нет аутентификации"

    scheme_name = next(iter(security[0].keys()), None)
    if not scheme_name:
        return "OAuth2PasswordBearer"

    security_schemes = openapi_spec.get("components", {}).get("securitySchemes", {})
    scheme = security_schemes.get(scheme_name, {})
    return scheme.get("scheme") or scheme.get("type") or scheme_name

def determine_interface_mode(
    operation: Dict[str, Any],
    openapi_spec: Dict[str, Any],
    path_item: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Определить режим интерфейса (синхронный/асинхронный) на основе расширений или описания.
    """
    candidates = [
        operation.get("x-interface-mode"),
        operation.get("x_interface_mode"),
        operation.get("x-interface-type"),
        operation.get("x-interface"),
        operation.get("x-mode"),
        path_item.get("x-interface-mode") if path_item else None,
        path_item.get("x_interface_mode") if path_item else None,
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

    if any(keyword in text_blob for keyword in ("async", "асинхрон", "asynchronous")):
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

def build_parameter_rows(
    operation: Dict[str, Any],
    openapi_spec: Dict[str, Any],
    path_parameters: Optional[List[Dict[str, Any]]] = None,
    enhance_descriptions: bool = False,
) -> List[Dict[str, Any]]:
    """
    Собрать сведения о параметрах пути, запроса, заголовков и тела.
    
    Args:
        enhance_descriptions: Если True, использовать LLM для генерации описаний для полей без описания
    """
    rows: List[Dict[str, Any]] = []

    all_parameters: List[Dict[str, Any]] = []
    if path_parameters:
        all_parameters.extend(path_parameters)
    all_parameters.extend(operation.get("parameters", []))

    for parameter in deduplicate_parameters(all_parameters):
        schema = extract_parameter_schema(parameter, openapi_spec)
        description = parameter.get("description") or schema.get("description") or ""
        
        # Генерируем описание через LLM, если оно пустое и включен режим улучшения
        if not description and enhance_descriptions:
            field_name = parameter.get("name", "-")
            field_type = get_schema_type(schema)
            try:
                from src.services.llm_service import generate_field_description
                generated = generate_field_description(
                    field_name=field_name,
                    field_type=field_type,
                    context={"location": parameter.get("in", "-")}
                )
                if generated:
                    description = generated
            except Exception as e:
                logger.debug(f"Failed to generate description for parameter '{field_name}': {e}")
        
        extras = []
        if "default" in schema:
            extras.append(f"По умолчанию: {schema['default']}")
        if "enum" in schema:
            extras.append(f"Допустимые значения: {', '.join(map(str, schema['enum']))}")
        if parameter.get("style"):
            extras.append(f"Стиль: {parameter['style']}")
        if parameter.get("explode") is not None:
            extras.append(f"explode: {parameter['explode']}")
        if "example" in schema:
            extras.append(f"Пример: {schema['example']}")
        if extras:
            description = f"{description}. " + "; ".join(extras)
        required = parameter.get("required", False) or parameter.get("in") == "path"
        rows.append(
            {
                "name": parameter.get("name", "-"),
                "in": parameter.get("in", "-"),
                "type": get_schema_type(schema),
                "description": description,
                "required": required,
            }
        )

    request_body = operation.get("requestBody")
    if request_body:
        required = request_body.get("required", False)
        content = request_body.get("content", {})
        media_type, media = select_preferred_media(content)
        if media is None:
            return rows

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
                enhance_descriptions=enhance_descriptions,
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
        if response is None:
            response = responses.get("default")

    if not response:
        return None

    content = response.get("content", {})
    _, media = select_preferred_media(content)
    if media:
        schema = resolve_schema(media.get("schema", {}), openapi_spec)
        if schema:
            return schema

    return None

def describe_schema_fields(schema: Optional[Dict[str, Any]], openapi_spec: Dict[str, Any], enhance_descriptions: bool = False) -> List[Dict[str, str]]:
    """
    Описать поля схемы ответа для таблицы.
    
    Args:
        enhance_descriptions: Если True, использовать LLM для генерации описаний для полей без описания
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
            # Получаем description из исходной схемы или из resolved схемы
            original_description = prop_schema.get("description") if isinstance(prop_schema, dict) else None
            resolved_prop = resolve_schema(prop_schema, openapi_spec)
            resolved_description = resolved_prop.get("description") if isinstance(resolved_prop, dict) else None
            description = original_description or resolved_description or ""
            
            # Генерируем описание через LLM, если оно пустое и включен режим улучшения
            if not description and enhance_descriptions:
                field_type = get_schema_type(resolved_prop)
                try:
                    from src.services.llm_service import generate_field_description
                    generated = generate_field_description(
                        field_name=name,
                        field_type=field_type,
                        context={"location": "response"}
                    )
                    if generated:
                        description = generated
                except Exception as e:
                    logger.debug(f"Failed to generate description for response field '{name}': {e}")
            
            fields.append(
                {
                    "name": name,
                    "type": get_schema_type(resolved_prop),
                    "description": description,
                }
            )
        return fields

    if schema_type == "array":
        item_schema = resolve_schema(resolved.get("items", {}), openapi_spec)
        item_type = get_schema_type(item_schema)

        # Раскрываем поля объекта внутри массива
        if item_type == "object" and item_schema.get("properties"):
            fields = []
            for name, prop_schema in item_schema.get("properties", {}).items():
                # Получаем description из исходной схемы или из resolved схемы
                original_description = prop_schema.get("description") if isinstance(prop_schema, dict) else None
                resolved_prop = resolve_schema(prop_schema, openapi_spec)
                resolved_description = resolved_prop.get("description") if isinstance(resolved_prop, dict) else None
                description = original_description or resolved_description or ""
                
                # Генерируем описание через LLM, если оно пустое и включен режим улучшения
                if not description and enhance_descriptions:
                    field_type = get_schema_type(resolved_prop)
                    try:
                        from src.services.llm_service import generate_field_description
                        generated = generate_field_description(
                            field_name=name,
                            field_type=field_type,
                            context={"location": "response", "parent": "array item"}
                        )
                        if generated:
                            description = generated
                    except Exception as e:
                        logger.debug(f"Failed to generate description for array item field '{name}': {e}")
                
                fields.append(
                    {
                        "name": f"items.{name}",
                        "type": get_schema_type(resolved_prop),
                        "description": description,
                    }
                )
            return fields

        return [
            {
                "name": "items[]",
                "type": f"array<{item_type}>",
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
    enhance_descriptions: bool = False,
) -> List[Dict[str, Any]]:
    """
    Получить список полей схемы (используется для описания requestBody).
    
    Args:
        enhance_descriptions: Если True, использовать LLM для генерации описаний для полей без описания
    """
    resolved = resolve_schema(schema, openapi_spec)
    schema_type = get_schema_type(resolved)

    if schema_type != "object":
        return []

    properties = resolved.get("properties", {})
    required_fields = set(resolved.get("required", []))
    rows: List[Dict[str, Any]] = []

    for name, prop_schema in properties.items():
        # Получаем description из исходной схемы или из resolved схемы
        original_description = prop_schema.get("description") if isinstance(prop_schema, dict) else None
        resolved_prop = resolve_schema(prop_schema, openapi_spec)
        resolved_description = resolved_prop.get("description") if isinstance(resolved_prop, dict) else None
        description = original_description or resolved_description or "Нет описания"
        
        # Генерируем описание через LLM, если оно "Нет описания" или пустое и включен режим улучшения
        if (description == "Нет описания" or not description) and enhance_descriptions:
            field_type = get_schema_type(resolved_prop)
            try:
                from src.services.llm_service import generate_field_description
                generated = generate_field_description(
                    field_name=name,
                    field_type=field_type,
                    context={"location": location, "parent": parent_name}
                )
                if generated:
                    description = generated
            except Exception as e:
                logger.debug(f"Failed to generate description for field '{name}': {e}")
        
        rows.append(
            {
                "name": f"{parent_name}.{name}",
                "in": location,
                "type": get_schema_type(resolved_prop),
                "description": description,
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
        _, media = select_preferred_media(content)
        if media:
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
            response = responses.get("default") or next(iter(responses.values()), None)

    if not response:
        return {"errorCode": 0, "errorMessage": ""}

    content = response.get("content", {})
    _, media = select_preferred_media(content)
    if media:
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

def build_example_from_schema(
    schema: Optional[Dict[str, Any]], 
    openapi_spec: Dict[str, Any],
    visited: Optional[set] = None,
    depth: int = 0
) -> Any:
    """
    Построить пример значения на основе схемы.
    """
    if visited is None:
        visited = set()
    
    # Ограничение глубины рекурсии для защиты от бесконечных циклов
    MAX_DEPTH = 20
    if depth > MAX_DEPTH:
        logger.warning(f"Maximum recursion depth ({MAX_DEPTH}) exceeded in schema example generation. Returning empty object/array.")
        return {}
    
    original_schema = schema or {}
    original_ref = original_schema.get("$ref")
    
    # КРИТИЧНО: Проверяем цикл ДО разрешения, используя $ref из исходной схемы
    # Это работает, потому что $ref стабилен и не меняется при разрешении
    if original_ref:
        if original_ref in visited:
            logger.warning(f"Circular reference detected for '{original_ref}' in schema example generation. Returning empty object/array.")
            resolved = resolve_schema(original_schema, openapi_spec)
            schema_type = get_schema_type(resolved) if isinstance(resolved, dict) else "unknown"
            if schema_type == "array":
                return []
            return {}
        schema_key = original_ref
        visited.add(schema_key)
        resolved = resolve_schema(original_schema, openapi_spec)
    else:
        # Для схем без $ref разрешаем сначала
        resolved = resolve_schema(original_schema, openapi_spec)
        # Пытаемся найти $ref в resolved схеме (может быть, если это была вложенная ссылка)
        resolved_ref = resolved.get("$ref") if isinstance(resolved, dict) else None
        if resolved_ref:
            if resolved_ref in visited:
                logger.warning(f"Circular reference detected for '{resolved_ref}' in schema example generation. Returning empty object/array.")
                schema_type = get_schema_type(resolved) if isinstance(resolved, dict) else "unknown"
                if schema_type == "array":
                    return []
                return {}
            schema_key = resolved_ref
            visited.add(schema_key)
        else:
            # Нет $ref ни в исходной, ни в resolved схеме
            # Для таких схем полагаемся только на ограничение глубины (MAX_DEPTH)
            # Не добавляем в visited, чтобы не блокировать легитимные вложенные структуры
            schema_key = None
    
    try:
        if "example" in resolved:
            return resolved["example"]
        
        schema_type = get_schema_type(resolved)

        if schema_type == "object":
            example = {}
            for name, prop_schema in resolved.get("properties", {}).items():
                # Проверяем цикл по $ref из исходной схемы свойства
                prop_ref = prop_schema.get("$ref") if isinstance(prop_schema, dict) else None
                if prop_ref and prop_ref in visited:
                    logger.warning(f"Skipping property '{name}' due to circular reference '{prop_ref}'")
                    continue
                # Также проверяем resolved схему свойства на наличие $ref
                if isinstance(prop_schema, dict):
                    prop_resolved = resolve_schema(prop_schema, openapi_spec)
                    prop_resolved_ref = prop_resolved.get("$ref") if isinstance(prop_resolved, dict) else None
                    if prop_resolved_ref and prop_resolved_ref in visited:
                        logger.warning(f"Skipping property '{name}' due to circular reference in resolved schema '{prop_resolved_ref}'")
                        continue
                example[name] = build_example_from_schema(prop_schema, openapi_spec, visited, depth + 1)
            return example or {}

        if schema_type == "array":
            item_schema = resolved.get("items", {})
            # Проверяем цикл по $ref из исходной схемы элемента
            item_ref = item_schema.get("$ref") if isinstance(item_schema, dict) else None
            if item_ref and item_ref in visited:
                logger.warning(f"Skipping array item due to circular reference '{item_ref}'")
                return []
            # Также проверяем resolved схему элемента на наличие $ref
            if isinstance(item_schema, dict):
                item_resolved = resolve_schema(item_schema, openapi_spec)
                item_resolved_ref = item_resolved.get("$ref") if isinstance(item_resolved, dict) else None
                if item_resolved_ref and item_resolved_ref in visited:
                    logger.warning(f"Skipping array item due to circular reference in resolved schema '{item_resolved_ref}'")
                    return []
            
            # Генерируем пример элемента массива
            item_example = build_example_from_schema(item_schema, openapi_spec, visited, depth + 1)
            
            # Если элемент массива - это пустой объект {}, это обычно означает,
            # что тип не был определен правильно. Для массивов в контексте ошибок
            # (например, loc в FastAPI validation errors) это должны быть строки.
            if isinstance(item_example, dict) and not item_example:
                # Проверяем тип элемента в схеме
                resolved_item = resolve_schema(item_schema, openapi_spec) if isinstance(item_schema, dict) else {}
                item_type = resolved_item.get("type") if isinstance(resolved_item, dict) else None
                
                # Если тип явно указан как string, или не указан вообще (пустой объект),
                # возвращаем строку (типично для loc в ошибках валидации)
                if item_type == "string" or item_type is None:
                    return ["string"]
                # Для других типов возвращаем значение по умолчанию
                return [item_example if item_example else "value"]
            
            return [item_example]

        if "enum" in resolved:
            return resolved["enum"][0]

        defaults = {
            "string": "string",
            "integer": 0,
            "number": 0,
            "boolean": True,
            "uuid": "123e4567-e89b-12d3-a456-426614174000",
            "date-time": "2024-01-01T00:00:00Z",
            "date": "2024-01-01",
            "email": "user@example.com",
        }

        # Учитываем nullable
        if resolved.get("nullable"):
            return None

        # Формат важнее базового типа
        fmt = resolved.get("format")
        if fmt and fmt in defaults:
            return defaults[fmt]

        return defaults.get(schema_type, "value")
    finally:
        # Удаляем из visited только если schema_key был установлен
        if schema_key is not None:
            visited.discard(schema_key)


def deduplicate_parameters(parameters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Объединить параметры path-уровня и operation-уровня, оставляя приоритет operation.
    """
    seen: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for param in parameters:
        name = param.get("name")
        where = param.get("in")
        if not name or not where:
            continue
        key = (name, where)
        seen[key] = param
    return list(seen.values())


def extract_parameter_schema(parameter: Dict[str, Any], openapi_spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Получить схему параметра, учитывая вариант с content (OpenAPI 3).
    """
    if "schema" in parameter:
        return resolve_schema(parameter.get("schema", {}), openapi_spec)

    content = parameter.get("content")
    if not content:
        return {}

    _, media = select_preferred_media(content)
    if not media:
        return {}
    return resolve_schema(media.get("schema", {}), openapi_spec)


def select_preferred_media(content: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Выбрать media type с приоритетом на JSON.
    """
    if not content:
        return None, None

    # Прямой приоритет application/json
    if "application/json" in content:
        return "application/json", content["application/json"]

    # Приоритет на *+json
    for media_type, media in content.items():
        if media_type.endswith("+json"):
            return media_type, media

    # Иначе первый попавшийся
    media_type, media = next(iter(content.items()))
    return media_type, media
