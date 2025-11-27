"""
Schema resolution utilities for OpenAPI specifications.
Handles $ref resolution with caching per OpenAPI 3.0 spec section 3.0.3.
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Cache for resolved schemas to improve performance
_schema_cache: Dict[str, Dict[str, Any]] = {}


def clear_schema_cache() -> None:
    """
    Clear the schema resolution cache.
    Should be called between processing different OpenAPI specs to avoid memory leaks.
    """
    global _schema_cache
    _schema_cache.clear()


def resolve_schema(schema: Dict[str, Any], openapi_spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve $ref references per OpenAPI 3.0 spec section 3.0.3.
    Handles local references (#/components/schemas/User) with caching for performance.
    
    Args:
        schema: Schema object that may contain $ref.
        openapi_spec: Full OpenAPI specification.
        
    Returns:
        Resolved schema dictionary.
    """
    if not schema:
        return {}

    ref = schema.get("$ref")
    if not ref:
        return schema
    
    # Check cache first
    cache_key = f"{id(openapi_spec)}:{ref}"
    if cache_key in _schema_cache:
        return _schema_cache[cache_key]
    
    # Handle external references (not supported yet, return original)
    if not ref.startswith("#/"):
        logger.warning(
            f"External reference '{ref}' is not supported. "
            "Only local references (#/components/...) are supported."
        )
        return schema
    
    # Resolve local reference
    parts = ref.lstrip("#/").split("/")
    resolved: Any = openapi_spec
    
    for part in parts:
        if not isinstance(resolved, dict):
            logger.warning(f"Failed to resolve $ref '{ref}': expected object at '{part}'")
            return schema
        resolved = resolved.get(part)
        if resolved is None:
            logger.warning(f"Failed to resolve $ref '{ref}': missing key '{part}'")
            return schema

    if not isinstance(resolved, dict):
        logger.warning(f"Failed to resolve $ref '{ref}': resolved value is not an object")
        return schema

    # Recursively resolve nested references
    resolved_schema = resolve_schema(resolved, openapi_spec)
    
    # Cache the result
    _schema_cache[cache_key] = resolved_schema
    
    return resolved_schema


def get_schema_type(schema: Dict[str, Any]) -> str:
    """
    Get human-readable type designation for a schema.
    
    Args:
        schema: Schema dictionary.
        
    Returns:
        Type string (string, integer, object, array, enum, etc.).
    """
    if not schema:
        return "object"

    if "type" in schema:
        return schema["type"]

    if "enum" in schema:
        return "enum"

    if "properties" in schema:
        return "object"

    if "items" in schema:
        return "array"

    ref = schema.get("$ref")
    if ref:
        return ref.split("/")[-1]

    return "object"



