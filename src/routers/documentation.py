"""
API routes for documentation generation per FastAPI best practices.
"""
import io
import json
import logging
from typing import Dict, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from src.config import HTTP_METHODS, USE_LLM_ENHANCE
from src.services.markdown_generator import generate_markdown_from_openapi
from src.services.docx_builder import build_docx_document
from src.services.openapi_parser import count_endpoints
from src.utils.filename import build_output_filename
from src.utils.validation import validate_openapi_spec
from src.utils.schema_resolver import clear_schema_cache

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/generate-doc",
    summary="Generate API Documentation",
    description="Upload an OpenAPI 3.0+ JSON file and receive comprehensive documentation in DOCX format.",
    response_description="DOCX file with API documentation",
    tags=["Documentation"]
)
async def generate_documentation(
    file: UploadFile = File(
        ...,
        description="OpenAPI 3.0+ JSON specification file",
        media_type="application/json"
    ),
    use_llm_enhance: Optional[bool] = Query(
        False,
        description="Enhanced mode: true = use LLM to improve descriptions (fast, recommended), false = local parsing only (fastest). Default: false."
    ),
    max_endpoints: Optional[int] = Query(
        None,
        description="Maximum number of endpoints to process. If not provided, processes all endpoints. Useful for testing or limiting large specifications.",
        ge=1
    )
) -> StreamingResponse:
    """
    Upload an OpenAPI JSON file and return documentation as a DOCX attachment.

    - **file**: OpenAPI 3.0+ JSON specification file (required)
    - **use_llm**: Full LLM generation (slow but comprehensive). If None, uses USE_LLM from config.
    - **use_llm_enhance**: LLM enhancement of descriptions only (fast, improves short descriptions). If None, uses USE_LLM_ENHANCE from config.

    Returns DOCX file with generated documentation.
    """
    try:
        # Validate file type per FastAPI best practices
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="File must have a filename"
            )
        if not file.filename.lower().endswith(".json"):
            raise HTTPException(
                status_code=400,
                detail="Only JSON files are supported. Please upload a .json file."
            )

        # Read file content
        content = await file.read()
        try:
            openapi_spec = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON: {str(e)}. Please ensure the file is valid JSON."
            )

        # Validate OpenAPI structure per OpenAPI 3.0 spec
        validate_openapi_spec(openapi_spec)
        
        # Clear schema cache before processing new spec (per performance best practices)
        clear_schema_cache()

        # Determine generation mode: only two modes available
        # 1. Fast mode (use_llm_enhance=false): local parsing only
        # 2. Enhanced mode (use_llm_enhance=true): local parsing + LLM improves descriptions
        enhance_mode = use_llm_enhance if use_llm_enhance is not None else False
        
        mode_desc = "enhanced (local + LLM)" if enhance_mode else "fast (local only)"
        logger.info(f"Generating documentation using {mode_desc} mode")
        
        # Generate documentation
        markdown_result = generate_markdown_from_openapi(
            openapi_spec, 
            use_llm=False,  # Full LLM generation removed
            use_llm_enhance=enhance_mode,
            max_endpoints=max_endpoints
        )
        docx_bytes = build_docx_document(markdown_result)
        total_endpoints = count_endpoints(openapi_spec)
        filename = build_output_filename(file.filename)

        # Return DOCX file as download per FastAPI and documentation best practices
        output_stream = io.BytesIO(docx_bytes)
        response = StreamingResponse(
            output_stream,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        # Set proper headers per documentation.mdc
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.headers["X-Total-Endpoints"] = str(total_endpoints)
        response.headers["X-Generation-Mode"] = "enhanced" if enhance_mode else "fast"
        response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return response

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ValueError as e:
        # Validation errors
        logger.warning(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Log full traceback for debugging
        logger.error(f"Error processing file: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error. Please check the logs for details."
        )


@router.get("/health")
def health_check() -> Dict[str, str]:
    """
    Report the current service health and configuration.

    Returns:
        dict: Health status payload with generation mode info.
    """
    current_generation_mode = "enhanced" if USE_LLM_ENHANCE else "fast"
    llm_configured_status = "true" if USE_LLM_ENHANCE else "false"

    return {
        "status": "healthy",
        "service": "openapi-to-docx",
        "generation_mode": current_generation_mode,
        "llm_configured": llm_configured_status
    }
