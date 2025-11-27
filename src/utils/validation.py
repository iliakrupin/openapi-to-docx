"""
OpenAPI specification validation per OpenAPI 3.0 spec.
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def validate_openapi_spec(openapi_spec: Dict[str, Any]) -> None:
    """
    Validate OpenAPI specification structure per OpenAPI 3.0 spec.
    
    Args:
        openapi_spec: Parsed OpenAPI specification dictionary.
        
    Raises:
        ValueError: If the specification is invalid.
    """
    # Check required 'openapi' field (section 3.0.0)
    if "openapi" not in openapi_spec:
        raise ValueError(
            "Invalid OpenAPI specification: missing required 'openapi' field. "
            "Per OpenAPI 3.0 spec section 3.0.0, this field is required."
        )
    
    # Validate OpenAPI version (must be 3.0.0 or higher)
    openapi_version = openapi_spec.get("openapi", "")
    try:
        version_parts = openapi_version.split(".")
        major = int(version_parts[0])
        minor = int(version_parts[1]) if len(version_parts) > 1 else 0
        
        if major < 3 or (major == 3 and minor < 0):
            raise ValueError(
                f"Unsupported OpenAPI version: {openapi_version}. "
                "This service requires OpenAPI 3.0.0 or higher."
            )
    except (ValueError, IndexError):
        raise ValueError(
            f"Invalid OpenAPI version format: {openapi_version}. "
            "Expected format: '3.0.0' or higher."
        )
    
    # Check required 'info' field (section 3.1.0)
    if "info" not in openapi_spec:
        raise ValueError(
            "Invalid OpenAPI specification: missing required 'info' field. "
            "Per OpenAPI 3.0 spec section 3.1.0, this field is required."
        )
    
    # Check required 'paths' field (section 3.0.0)
    if "paths" not in openapi_spec:
        raise ValueError(
            "Invalid OpenAPI specification: missing required 'paths' field. "
            "Per OpenAPI 3.0 spec section 3.0.0, this field is required."
        )
    
    # Validate paths object
    paths = openapi_spec.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError(
            "Invalid OpenAPI specification: 'paths' must be an object. "
            "Per OpenAPI 3.0 spec section 3.1.0."
        )
    
    # Validate each path starts with '/'
    for path in paths.keys():
        if not path.startswith("/"):
            logger.warning(
                f"Path '{path}' does not start with '/'. "
                "Per OpenAPI 3.0 spec section 3.1.0, paths should start with '/'."
            )



