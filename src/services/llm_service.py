"""
LLM service for enhanced documentation generation via LM Studio API.
Per FastAPI and documentation best practices.
"""
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.config import LM_STUDIO_API_URL, HEADERS, MODEL_NAME, MAX_TOKENS

logger = logging.getLogger(__name__)

# Cache for enhanced descriptions to avoid redundant API calls
_description_cache: Dict[str, str] = {}
_translation_cache: Dict[str, str] = {}


def enhance_descriptions_batch(descriptions: List[Tuple[str, Dict[str, Any]]]) -> Dict[str, str]:
    """
    Enhance multiple descriptions in a single batch request.
    
    Args:
        descriptions: List of (description, context) tuples
        
    Returns:
        Dictionary mapping original descriptions to enhanced versions
    """
    if not descriptions:
        return {}
    
    # Check cache first
    results = {}
    to_enhance = []
    
    for desc, context in descriptions:
        cache_key = f"{desc}_{context.get('method', '')}_{context.get('path', '')}"
        if cache_key in _description_cache:
            results[desc] = _description_cache[cache_key]
            logger.debug(f"Using cached description for {context.get('method')} {context.get('path')}")
        else:
            to_enhance.append((desc, context, cache_key))
    
    logger.info(f"Cache check: {len(results)} from cache, {len(to_enhance)} to enhance")
    if not to_enhance:
        logger.info("All descriptions found in cache, skipping LLM call")
        return results
    
    # Batch enhance remaining descriptions
    try:
        endpoints_list = []
        for desc, context, _ in to_enhance:
            endpoint_info = f"{context.get('method', '')} {context.get('path', '')}"
            endpoints_list.append(f"- {endpoint_info}: {desc or 'отсутствует'}")
        
        prompt = f"""Улучши краткие описания для следующих API эндпоинтов.

Эндпоинты:
{chr(10).join(endpoints_list)}

Для каждого эндпоинта создай краткое (1-2 предложения), понятное описание на русском языке.
ВАЖНО: Если в исходном описании есть блоки "Parameters:", "Returns:", "Raises:" - НЕ включай их в улучшенное описание.
Улучшай только основную часть описания (до этих блоков).
Верни ответ в формате JSON массив, где каждый элемент:
{{"endpoint": "метод путь", "description": "улучшенное описание"}}

Верни только JSON, без дополнительных комментариев."""
        
        url = f"{LM_STUDIO_API_URL}/chat/completions"
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {
                    "role": "system",
                    "content": "Ты эксперт по API документации. Создавай краткие, понятные описания. Всегда отвечай валидным JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": min(150 * len(to_enhance), 2000),  # Scale with batch size
            "temperature": 0.3
        }
        
        logger.info(f"Batch enhancing {len(to_enhance)} descriptions")
        logger.info(f"Calling LM Studio API: {url}")
        response = requests.post(url, json=payload, headers=HEADERS, timeout=60)
        response.raise_for_status()
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0].get("message", {}).get("content", "").strip()
            
            # Try to parse JSON response
            try:
                # Extract JSON from markdown code blocks if present
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                
                enhanced_list = json.loads(content)
                
                # Map results back to original descriptions
                for desc, context, cache_key in to_enhance:
                    endpoint_key = f"{context.get('method', '')} {context.get('path', '')}"
                    enhanced_desc = desc  # Default to original
                    
                    for item in enhanced_list:
                        if isinstance(item, dict) and item.get("endpoint") == endpoint_key:
                            enhanced_desc = item.get("description", desc)
                            break
                    
                    if enhanced_desc and len(enhanced_desc) > 10:
                        # Clean markdown and emojis from LLM response
                        from src.services.markdown_generator import sanitize_text
                        enhanced_desc = sanitize_text(enhanced_desc)
                        results[desc] = enhanced_desc
                        _description_cache[cache_key] = enhanced_desc
                    else:
                        results[desc] = desc
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"Failed to parse batch enhancement response: {str(e)}")
                # Fall back to individual enhancement
                for desc, context, cache_key in to_enhance:
                    results[desc] = desc
    except Exception as e:
        logger.warning(f"Batch enhancement failed: {str(e)}")
        # Return originals on error
        for desc, _, _ in to_enhance:
            results[desc] = desc
    
    return results


def enhance_description_with_llm(description: str, context: Dict[str, Any]) -> str:
    """
    Enhance a description using LLM (optional enhancement).
    Only enhances short or missing descriptions to save tokens and time.
    
    Args:
        description: Original description
        context: Additional context (endpoint, method, path, etc.)
        
    Returns:
        Enhanced description or original if enhancement not needed/failed
    """
    # Check cache first
    cache_key = f"{description}_{context.get('method', '')}_{context.get('path', '')}"
    if cache_key in _description_cache:
        return _description_cache[cache_key]
    
    if not description or len(description.strip()) < 10:
        # Only enhance if description is missing or very short
        try:
            endpoint_info = f"{context.get('method', '')} {context.get('path', '')}"
            prompt = f"""Улучши краткое описание для API эндпоинта.

Эндпоинт: {endpoint_info}
Текущее описание: {description or 'отсутствует'}

Создай краткое (1-2 предложения), понятное описание на русском языке, объясняющее что делает этот эндпоинт.
ВАЖНО: Если в исходном описании есть блоки "Parameters:", "Returns:", "Raises:" - НЕ включай их в улучшенное описание.
Улучшай только основную часть описания (до этих блоков).
Верни только улучшенное описание, без дополнительных комментариев."""
            
            url = f"{LM_STUDIO_API_URL}/chat/completions"
            payload = {
                "model": MODEL_NAME,
                "messages": [
                    {
                        "role": "system",
                        "content": "Ты эксперт по API документации. Создавай краткие, понятные описания."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": 150,  # Short response
                "temperature": 0.3
            }
            
            response = requests.post(url, json=payload, headers=HEADERS, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if "choices" in result and len(result["choices"]) > 0:
                enhanced = result["choices"][0].get("message", {}).get("content", "").strip()
                if enhanced and len(enhanced) > 10:
                    # Clean markdown and emojis from LLM response
                    from src.services.markdown_generator import sanitize_text
                    enhanced = sanitize_text(enhanced)
                    logger.debug(f"Enhanced description for {endpoint_info}")
                    _description_cache[cache_key] = enhanced
                    return enhanced
        except Exception as e:
            logger.warning(f"Failed to enhance description: {str(e)}")
            # Return original on error
            return description or f"{context.get('method', '')} запрос к {context.get('path', '')}"
    
    # Return original if description is already good
    return description


def translate_to_russian(text: str) -> str:
    """
    Перевести произвольный текст на русский язык через LM Studio API.
    Возвращает исходную строку при отсутствии конфигурации или ошибке.
    """
    if not text:
        return ""

    # Нет настроек — возвращаем оригинал
    if not LM_STUDIO_API_URL or not HEADERS:
        return text

    if text in _translation_cache:
        return _translation_cache[text]

    url = f"{LM_STUDIO_API_URL}/chat/completions"
    prompt = (
        "Переведи текст на русский, сохраняя технические термины и идентификаторы. "
        "Не добавляй ничего, только перевод.\n\n"
        f"Текст: {text}"
    )

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": "Ты профессиональный технический переводчик. Переводи кратко, без лишних пояснений."
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": min(MAX_TOKENS, 400),
        "temperature": 0.2,
    }

    try:
        response = requests.post(url, json=payload, headers=HEADERS, timeout=60)
        response.raise_for_status()
        result = response.json()
        translated = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if translated:
            _translation_cache[text] = translated
            return translated
    except Exception as exc:  # noqa: B902
        logger.debug(f"Translation failed, returning original: {exc}")

    return text


def clear_description_cache():
    """Clear the description enhancement cache."""
    global _description_cache
    _description_cache.clear()
    logger.debug("Description cache cleared")


def clear_translation_cache():
    """Clear translation cache."""
    global _translation_cache
    _translation_cache.clear()
    logger.debug("Translation cache cleared")
