"""
Utility functions for filename generation.
"""
from datetime import datetime
from pathlib import Path


def build_output_filename(original_name: str) -> str:
    """
    Build safe DOCX filename based on original OpenAPI file name.
    
    Args:
        original_name: Original filename.
        
    Returns:
        Safe filename with timestamp.
    """
    stem = Path(original_name).stem or "openapi"
    safe_stem = "".join(ch for ch in stem if ch.isalnum() or ch in ("-", "_")) or "openapi"
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{safe_stem}_doc_{timestamp}.docx"



