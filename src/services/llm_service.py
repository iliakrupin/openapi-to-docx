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
    
    # Проверяем, что LLM настроен
    if not LM_STUDIO_API_URL or not isinstance(LM_STUDIO_API_URL, str) or not LM_STUDIO_API_URL.strip():
        logger.warning("LLM not configured (LM_STUDIO_API_URL is not set), skipping batch enhancement")
        # Возвращаем оригинальные описания
        for desc, _, _ in to_enhance:
            results[desc] = desc
        return results
    
    # Проверяем, что URL валидный (содержит схему)
    if not LM_STUDIO_API_URL.startswith(('http://', 'https://')):
        logger.warning(f"Invalid LM_STUDIO_API_URL format, skipping batch enhancement")
        # Возвращаем оригинальные описания
        for desc, _, _ in to_enhance:
            results[desc] = desc
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
            
            # Log full LLM response for debugging
            logger.info(f"LLM batch enhancement response (full):\n{content}")
            logger.info(f"Response length: {len(content)} characters")
            
            # Try to parse JSON response
            try:
                # Extract JSON from markdown code blocks if present
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                
                # Try to fix common JSON issues
                import re
                
                # Remove trailing commas before closing brackets/braces
                content = re.sub(r',\s*}', '}', content)
                content = re.sub(r',\s*]', ']', content)
                
                # Try to extract JSON array if there's extra text
                # Look for array pattern
                array_match = re.search(r'\[.*\]', content, re.DOTALL)
                if array_match:
                    content = array_match.group(0)
                
                # Remove any control characters that might break JSON (except newlines, tabs, carriage returns)
                content = ''.join(char for char in content if ord(char) >= 32 or char in '\n\r\t')
                
                # Try to parse JSON
                enhanced_list = json.loads(content)
                
                # Validate that we got a list
                if not isinstance(enhanced_list, list):
                    logger.warning(f"Batch enhancement response is not a list, got {type(enhanced_list)}")
                    raise ValueError("Response is not a list")
                
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
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                logger.warning(f"Failed to parse batch enhancement response: {str(e)}")
                logger.warning(f"Error details: {type(e).__name__}: {str(e)}")
                
                # Log problematic content for debugging (save to variable first to ensure it's captured)
                error_content = content
                logger.warning(f"Response content that failed to parse (length: {len(error_content)}):")
                # Log in chunks to avoid truncation
                chunk_size = 2000
                for i in range(0, len(error_content), chunk_size):
                    chunk = error_content[i:i+chunk_size]
                    logger.warning(f"Content chunk {i//chunk_size + 1}:\n{chunk}")
                
                # Try to extract what we can - maybe some items are valid
                # Try to find individual JSON objects in the response using a more flexible pattern
                try:
                    # Look for individual {"endpoint": "...", "description": "..."} patterns
                    # More flexible pattern that handles multiline and escaped quotes
                    pattern = r'\{\s*"endpoint"\s*:\s*"([^"\\]*(\\.[^"\\]*)*)"\s*,\s*"description"\s*:\s*"([^"\\]*(\\.[^"\\]*)*)"\s*\}'
                    matches = re.finditer(pattern, content, re.DOTALL)
                    found_count = 0
                    for match in matches:
                        try:
                            # Reconstruct the JSON object
                            endpoint_val = match.group(1).replace('\\"', '"')
                            desc_val = match.group(3).replace('\\"', '"')
                            
                            # Find matching description
                            for desc, context, cache_key in to_enhance:
                                expected_key = f"{context.get('method', '')} {context.get('path', '')}"
                                if endpoint_val == expected_key and desc_val:
                                    from src.services.markdown_generator import sanitize_text
                                    enhanced_desc = sanitize_text(desc_val)
                                    results[desc] = enhanced_desc
                                    _description_cache[cache_key] = enhanced_desc
                                    found_count += 1
                                    break
                        except Exception as item_error:
                            logger.debug(f"Failed to process extracted item: {item_error}")
                    
                    if found_count > 0:
                        logger.info(f"Successfully extracted {found_count} valid endpoint descriptions from malformed JSON")
                except Exception as extract_error:
                    logger.debug(f"Failed to extract partial results: {extract_error}")
                
                # Fill in missing results with originals
                for desc, context, cache_key in to_enhance:
                    if desc not in results:
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
        # Проверяем, что LLM настроен
        if not LM_STUDIO_API_URL or not isinstance(LM_STUDIO_API_URL, str) or not LM_STUDIO_API_URL.strip():
            logger.debug("LLM not configured, skipping description enhancement")
            return description or f"{context.get('method', '')} запрос к {context.get('path', '')}"
        
        # Проверяем, что URL валидный (содержит схему)
        if not LM_STUDIO_API_URL.startswith(('http://', 'https://')):
            logger.debug("Invalid LM_STUDIO_API_URL format, skipping description enhancement")
            return description or f"{context.get('method', '')} запрос к {context.get('path', '')}"
        
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


# Cache for generated field descriptions
_field_description_cache: Dict[str, str] = {}


def generate_field_description(field_name: str, field_type: str, context: Optional[Dict[str, Any]] = None) -> str:
    """
    Сгенерировать описание для поля на основе его названия и типа через LLM.
    
    Args:
        field_name: Название поля (например, "userId", "email", "created_at")
        field_type: Тип поля (например, "string", "integer", "array<string>")
        context: Дополнительный контекст (например, {"location": "body", "parent": "User"})
        
    Returns:
        Сгенерированное описание на русском языке или пустая строка при ошибке
    """
    if not field_name:
        return ""
    
    # Проверяем кэш
    cache_key = f"{field_name}_{field_type}_{context.get('location', '') if context else ''}"
    if cache_key in _field_description_cache:
        return _field_description_cache[cache_key]
    
    # Нет настроек LLM — возвращаем пустую строку
    # Проверяем, что URL установлен и не пустой
    if not LM_STUDIO_API_URL or not isinstance(LM_STUDIO_API_URL, str) or not LM_STUDIO_API_URL.strip():
        logger.debug(f"LLM not configured (LM_STUDIO_API_URL is not set), skipping field description generation for '{field_name}'")
        return ""
    
    # Проверяем, что URL валидный (содержит схему)
    if not LM_STUDIO_API_URL.startswith(('http://', 'https://')):
        logger.debug(f"Invalid LM_STUDIO_API_URL format, skipping field description generation for '{field_name}'")
        return ""
    
    try:
        # Формируем промпт для генерации описания
        context_info = ""
        if context:
            if context.get("location"):
                context_info += f"Расположение: {context['location']}. "
            if context.get("parent"):
                context_info += f"Родительский объект: {context['parent']}. "
        
        prompt = f"""Сгенерируй краткое описание для поля API на русском языке.

Название поля: {field_name}
Тип поля: {field_type}
{context_info}

Создай краткое (1 предложение, максимум 50 символов), понятное описание на русском языке, объясняющее назначение этого поля.
Описание должно быть техническим и точным.
Верни только описание, без дополнительных комментариев и кавычек."""

        url = f"{LM_STUDIO_API_URL}/chat/completions"
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {
                    "role": "system",
                    "content": "Ты эксперт по API документации. Создавай краткие, технические описания полей."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 100,
            "temperature": 0.3
        }
        
        response = requests.post(url, json=payload, headers=HEADERS, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            raw_description = result["choices"][0].get("message", {}).get("content", "").strip()
            
            # Log full LLM response for debugging
            logger.info(f"LLM field description response for '{field_name}': {raw_description}")
            
            # Убираем кавычки, если они есть
            description = raw_description.strip('"').strip("'").strip()
            if description:
                # Очищаем markdown форматирование
                from src.services.markdown_generator import sanitize_text
                description = sanitize_text(description)
                _field_description_cache[cache_key] = description
                logger.info(f"Generated description for field '{field_name}': {description}")
                return description
    except Exception as exc:
        logger.debug(f"Failed to generate field description for '{field_name}': {exc}")
    
    return ""


def clear_field_description_cache():
    """Clear the field description cache."""
    global _field_description_cache
    _field_description_cache.clear()
    logger.debug("Field description cache cleared")
