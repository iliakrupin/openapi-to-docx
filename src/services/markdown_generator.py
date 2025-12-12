"""
Markdown documentation generator per documentation.mdc best practices.
Generates structured Markdown from OpenAPI specifications.
Supports both local parsing and LLM-based generation.
"""
import json
import re
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.config import USE_LLM_ENHANCE
from src.services.openapi_parser import (
    group_operations_by_tag, count_endpoints, determine_authentication,
    build_parameter_rows, get_success_response_schema, describe_schema_fields,
    build_request_example, build_response_example, determine_interface_mode,
    select_preferred_media, build_example_from_schema,
)

logger = logging.getLogger(__name__)

def generate_markdown_from_openapi(openapi_spec: Dict[str, Any], use_llm: bool = False, use_llm_enhance: Optional[bool] = None, max_endpoints: Optional[int] = None) -> str:
    """
    Сформировать Markdown-документ в соответствии с шаблоном template_files/api_template.md.
    
    Two modes available:
    1. Fast mode (use_llm_enhance=false): Local parsing only, very fast
    2. Enhanced mode (use_llm_enhance=true): Local parsing + LLM improves descriptions
    
    Args:
        openapi_spec: OpenAPI 3.0+ specification dictionary
        use_llm: Deprecated, always False (full LLM generation removed)
        use_llm_enhance: If True, use LLM to enhance descriptions. If None, uses USE_LLM_ENHANCE from config.
        max_endpoints: Maximum number of endpoints to process
        
    Returns:
        Generated Markdown documentation string
    """
    # Full LLM generation removed - only local parsing with optional enhancement
    should_enhance = use_llm_enhance if use_llm_enhance is not None else USE_LLM_ENHANCE
    
    # Use local parsing with optional LLM enhancement
    mode_name = "enhanced (local + LLM)" if should_enhance else "fast (local only)"
    logger.info(f"Using {mode_name} mode for documentation generation")
    return generate_markdown_local(openapi_spec, enhance_descriptions=should_enhance, max_endpoints=max_endpoints)


def generate_markdown_local(openapi_spec: Dict[str, Any], enhance_descriptions: bool = False, max_endpoints: Optional[int] = None) -> str:
    """
    Сформировать Markdown-документ локальным парсингом (без LLM).
    
    Args:
        openapi_spec: OpenAPI specification
        enhance_descriptions: If True, use LLM to enhance short/missing descriptions
        max_endpoints: Maximum number of endpoints to process. If None, processes all.
    """
    grouped_operations = group_operations_by_tag(openapi_spec)
    
    # Limit endpoints if max_endpoints is specified - APPLY BEFORE BATCH ENHANCEMENT
    if max_endpoints is not None and max_endpoints > 0:
        endpoint_count = 0
        limited_operations = {}
        for tag, operations in grouped_operations.items():
            if endpoint_count >= max_endpoints:
                break
            remaining = max_endpoints - endpoint_count
            limited_operations[tag] = operations[:remaining]
            endpoint_count += len(limited_operations[tag])
        grouped_operations = limited_operations
        logger.info(f"Limited to {endpoint_count} endpoints (max_endpoints={max_endpoints})")
    if not grouped_operations:
        return "# 📘 API-документация\n\nНет доступных эндпоинтов в спецификации."

    total_endpoints = count_endpoints(openapi_spec)
    processed_endpoints = sum(len(ops) for ops in grouped_operations.values())
    endpoint_info = f"{processed_endpoints} эндпоинтов"
    if max_endpoints and processed_endpoints < total_endpoints:
        endpoint_info += f" (из {total_endpoints} по спецификации)"
    else:
        endpoint_info += f" по спецификации OpenAPI версии {openapi_spec.get('openapi', 'unknown')}"
    
    md_lines: List[str] = [
        "# 📘 API-документация",
        "",
        endpoint_info,
        "",
    ]

    # Batch enhance descriptions if enabled - ONLY FOR LIMITED ENDPOINTS
    enhanced_descriptions: Dict[str, str] = {}
    if enhance_descriptions:
        try:
            from src.services.llm_service import enhance_descriptions_batch
            
            # Collect all descriptions that need enhancement - ONLY FROM LIMITED OPERATIONS
            descriptions_to_enhance: List[Tuple[str, Dict[str, Any]]] = []
            for tag, operations in grouped_operations.items():
                for endpoint in operations:
                    operation = endpoint["operation"]
                    description = operation.get("description") or f"{endpoint['method']} запрос к {endpoint['path']}"
                    if len(description or "") >= 160:
                        continue
                    
                    # Enhance all descriptions when enhancement mode is enabled
                    # User explicitly enabled enhancement, so improve all descriptions
                    descriptions_to_enhance.append((
                        description,
                        {
                            "method": endpoint["method"],
                            "path": endpoint["path"],
                            "summary": operation.get("summary") or operation.get("operationId", ""),
                            "tag": tag
                        }
                    ))
            
            logger.info(f"Found {len(descriptions_to_enhance)} descriptions to enhance (from {processed_endpoints} limited endpoints)")
            if descriptions_to_enhance:
                logger.info(f"Batch enhancing {len(descriptions_to_enhance)} descriptions")
                enhanced_descriptions = enhance_descriptions_batch(descriptions_to_enhance)
                logger.info(f"Enhanced {len(enhanced_descriptions)} descriptions")
            else:
                logger.info("No descriptions need enhancement (all descriptions are >= 50 characters)")
        except Exception as e:
            logger.warning(f"Batch enhancement failed, falling back to individual: {str(e)}")
            enhanced_descriptions = {}

    overall_index = 1

    for tag, operations in grouped_operations.items():
        md_lines.append(f"## ИНТЕРФЕЙСЫ ВЗАИМОДЕЙСТВИЯ — {tag}")
        md_lines.append("")
        for index, endpoint in enumerate(operations, start=1):
            md_lines.extend(
                render_endpoint_section(
                    index=overall_index,
                    tag=tag,
                    path=endpoint["path"],
                    method=endpoint["method"],
                    operation=endpoint["operation"],
                    path_parameters=endpoint.get("path_parameters") or [],
                    path_item=endpoint.get("path_item") or {},
                    openapi_spec=openapi_spec,
                    enhance_descriptions=enhance_descriptions,
                    enhanced_descriptions=enhanced_descriptions,
                )
            )
            md_lines.append("---")
            md_lines.append("")
            overall_index += 1

    return "\n".join(md_lines).strip()

def render_endpoint_section(
    index: int,
    tag: str,
    path: str,
    method: str,
    operation: Dict[str, Any],
    path_parameters: List[Dict[str, Any]],
    path_item: Dict[str, Any],
    openapi_spec: Dict[str, Any],
    enhance_descriptions: bool = False,
    enhanced_descriptions: Optional[Dict[str, str]] = None,
) -> List[str]:
    """
    Сформировать блок Markdown для одного метода в рамках выбранного тега.
    
    Args:
        enhance_descriptions: If True, use LLM to enhance short/missing descriptions
        enhanced_descriptions: Pre-enhanced descriptions from batch processing
    """
    summary = (
        operation.get("summary")
        or operation.get("operationId")
        or f"{method} {path}"
    )
    summary = translate_text_if_needed(summary)

    original_description = operation.get("description") or f"{method} запрос к {path}"
    original_description = translate_text_if_needed(original_description)
    description = original_description
    
    # Use pre-enhanced description from batch if available
    if enhanced_descriptions and original_description in enhanced_descriptions:
        enhanced_desc = enhanced_descriptions[original_description]
        # Preserve structured blocks (Parameters/Returns/Raises) from original
        intro_original, structured_original = split_description_content(original_description)
        intro_enhanced, structured_enhanced = split_description_content(enhanced_desc)
        
        # Use enhanced intro, but keep original structured blocks if they exist
        if structured_original:
            description = f"{intro_enhanced}\n\n{structured_original}" if intro_enhanced else structured_original
        else:
            # No structured blocks in original, use enhanced as-is
            description = enhanced_desc
        
        # Clean only markdown formatting, preserve structure
        description = sanitize_text_preserve_structure(description)
        logger.debug(f"Using enhanced description for {method} {path}")
    # Fallback to individual enhancement if batch didn't cover it
    elif enhance_descriptions:
        try:
            from src.services.llm_service import enhance_description_with_llm
            # Split to preserve structured blocks
            intro_original, structured_original = split_description_content(description)
            
            # Enhance only the intro part
            if intro_original:
                enhanced_intro = enhance_description_with_llm(
                    intro_original,
                    context={"method": method, "path": path, "summary": summary}
                )
                # Combine enhanced intro with original structured blocks
                if structured_original:
                    description = f"{enhanced_intro}\n\n{structured_original}"
                else:
                    description = enhanced_intro
            else:
                # No intro, enhance full description
                description = enhance_description_with_llm(
                    description,
                    context={"method": method, "path": path, "summary": summary}
                )
            
            # Clean only markdown formatting, preserve structure
            description = sanitize_text_preserve_structure(description)
        except Exception as e:
            logger.warning(f"Failed to enhance description for {method} {path}: {str(e)}")
            # Continue with original description
    auth_info = determine_authentication(operation, openapi_spec)
    parameter_rows = build_parameter_rows(operation, openapi_spec, path_parameters=path_parameters, enhance_descriptions=enhance_descriptions)
    for row in parameter_rows:
        # Переводим только если описание не было сгенерировано через LLM (LLM уже возвращает русский текст)
        # и описание не пустое и не "Нет описания"
        desc = row.get("description", "")
        if desc and desc != "Нет описания" and desc.strip():
            row["description"] = translate_text_if_needed(desc)

    response_schema = get_success_response_schema(operation, openapi_spec)
    response_fields = describe_schema_fields(response_schema, openapi_spec, enhance_descriptions=enhance_descriptions)
    for field in response_fields:
        # Переводим только если описание не было сгенерировано через LLM (LLM уже возвращает русский текст)
        # и описание не пустое
        desc = field.get("description", "")
        if desc and desc.strip():
            field["description"] = translate_text_if_needed(desc)
    request_example = build_request_example(operation, openapi_spec)
    response_example = build_response_example(operation, openapi_spec)

    interface_mode = determine_interface_mode(operation, openapi_spec, path_item=path_item)

    summary_clean = sanitize_text(summary)
    heading_source = operation.get("description") or operation.get("summary") or summary
    intro_text_raw, detail_text_raw = split_description_content(description or "")
    intro_text = sanitize_text(intro_text_raw or heading_source)
    # Preserve structured blocks in detail_text (Parameters/Returns/Raises)
    detail_text = sanitize_text_preserve_structure(detail_text_raw) if detail_text_raw else ""
    intro_items = format_as_bullet_list(intro_text)
    has_structured_detail = bool(detail_text.strip())
    detail_items = (
        format_as_bullet_list(detail_text) if has_structured_detail else intro_items
    )

    section: List[str] = [f"## {index}. {summary_clean}"]

    if has_structured_detail and intro_items:
        section.extend(intro_items)
        section.append("")

    section.append(f"### {index}.1 Описание")
    section.extend(detail_items)
    section.append("")

    section.extend(
        [
            f"### {index}.2 Требования к интерфейсу",
            "| Параметр | Значение |",
            "|---------|----------|",
            f"| Синхронный/Асинхронный | {interface_mode} |",
            "| Технология | REST API (HTTP request–response) |",
            "| Время ответа | Не более 1 секунды |",
            "| Формат ответа | JSON |",
            "| Кодировка | UTF-8 |",
            f"| Аутентификация | {auth_info} |",
            "",
            f"### {index}.3 Формат запроса",
            "| Поле | Значение |",
            "|------|----------|",
            f"| URL | `{path}` |",
            f"| Метод | `{method}` |",
            "",
            f"### {index}.4 Параметры запроса",
        ]
    )

    section.extend(format_parameters_table(parameter_rows))

    section.extend(
        [
            f"### {index}.5 Формат ответа",
            "| Поле | Тип | Описание |",
            "|------|-----|----------|",
        ]
    )

    if response_fields:
        for field in response_fields:
            section.append(
                f"| {field['name']} | {field['type']} | {field['description']} |"
            )
    else:
        section.extend(
            [
                "| errorCode | Integer | Код ошибки (0 — нет ошибки) |",
                "| errorMessage | String | Сообщение об ошибке |",
            ]
        )

    error_examples = build_error_examples(operation, openapi_spec)
    section.extend(
        [
            "",
            f"### {index}.6 Пример запроса (JSON)",
            format_json_block(request_example),
            "",
            f"### {index}.7 Пример ответа (JSON)",
            format_json_block(response_example),
            "",
            f"### {index}.8 Примеры ошибок",
        ]
    )
    if error_examples:
        for example in error_examples:
            section.append(format_json_block(example))
            section.append("")
    else:
        section.extend(
            [
                "```json",
                '{ "error": "Invalid request", "code": 400 }',
                "```",
                "",
                "```json",
                '{ "error": "Unauthorized", "code": 401 }',
                "```",
                "",
                "```json",
                '{ "error": "Internal server error", "code": 500 }',
                "```",
                "",
            ]
        )

    return section

def format_parameters_table(rows: List[Dict[str, Any]]) -> List[str]:
    """
    Представить параметры в виде таблицы Markdown.
    """
    table = [
        "| Имя | Где | Тип | Описание | Обязательный |",
        "|-----|-----|-----|-----------|--------------|",
    ]

    if not rows:
        table.append("| — | — | — | Нет параметров | — |")
        table.append("")
        return table

    for row in rows:
        table.append(
            f"| {row['name']} | {row['in']} | {row['type']} | {row['description']} | {'Да' if row.get('required') else 'Нет'} |"
        )

    table.append("")
    return table

def format_json_block(payload: Any) -> str:
    """
    Преобразовать Python-структуру в форматированный JSON-блок.
    """
    json_text = json.dumps(payload or {}, ensure_ascii=False, indent=2)
    return f"```json\n{json_text}\n```"


def build_error_examples(operation: Dict[str, Any], openapi_spec: Dict[str, Any]) -> List[Any]:
    """
    Собрать примеры ошибок из 4xx/5xx ответов, если они есть в спецификации.
    """
    responses = operation.get("responses", {})
    error_codes = [code for code in responses.keys() if str(code).startswith(("4", "5"))]
    examples: List[Any] = []

    for status in sorted(error_codes)[:3]:
        response = responses.get(status, {})
        content = response.get("content", {})
        _, media = select_preferred_media(content)
        if not media:
            continue

        media_examples = media.get("examples")
        if media_examples:
            example_value = next(iter(media_examples.values()))
            if isinstance(example_value, dict):
                examples.append(example_value.get("value", {}))
            else:
                examples.append(example_value)
            continue

        if "example" in media:
            examples.append(media["example"])
            continue

        schema = media.get("schema")
        if schema:
            examples.append(build_example_from_schema(schema, openapi_spec))

    return examples

def sanitize_text(value: Optional[str]) -> str:
    """
    Удалить простые Markdown-выделения, заголовки, эмоджи и лишние пробелы.
    """
    if not value:
        return ""

    text = str(value).strip()
    # Remove markdown headers (####, ###, ##, #) - anywhere in text, including standalone
    text = re.sub(r"#{1,6}\s*", "", text)
    # Remove markdown bold/italic (**text**, *text*, __text__, _text_)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)  # **bold**
    text = re.sub(r"\*([^*]+)\*", r"\1", text)     # *italic*
    text = re.sub(r"__([^_]+)__", r"\1", text)     # __bold__
    text = re.sub(r"_([^_]+)_", r"\1", text)       # _italic_
    # Remove remaining markdown markers
    text = re.sub(r"[*_]{1,2}", "", text)
    # Remove emojis (Unicode emoji ranges)
    text = re.sub(r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251]+", "", text)
    # Remove markdown code blocks and inline code
    text = re.sub(r"```[^`]*```", "", text)  # Code blocks
    text = re.sub(r"`[^`]+`", "", text)      # Inline code
    # Remove markdown links [text](url)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Remove markdown lists markers at start of line
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def sanitize_text_preserve_structure(value: Optional[str]) -> str:
    """
    Удалить Markdown-выделения, но сохранить структурированные блоки (Parameters/Returns/Raises).
    """
    if not value:
        return ""

    # Split into intro and structured blocks
    intro, structured = split_description_content(value)
    
    # Clean intro part
    intro_clean = sanitize_text(intro) if intro else ""
    
    # Keep structured blocks as-is (they contain important information)
    if structured:
        # Clean markdown formatting in structured blocks, but preserve structure
        structured_clean = structured
        # Remove headers
        structured_clean = re.sub(r"#{1,6}\s*", "", structured_clean)
        # Remove emojis
        structured_clean = re.sub(r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251]+", "", structured_clean)
        # Remove markdown bold/italic (**text**, *text*, __text__, _text_)
        # First remove **bold** patterns
        structured_clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", structured_clean)  # **bold**
        # Then remove __bold__ patterns
        structured_clean = re.sub(r"__([^_]+)__", r"\1", structured_clean)     # __bold__
        # Remove *italic* but preserve list markers (lines starting with - or *)
        structured_clean = re.sub(r"(?<!^)\*([^*\n]+)\*(?!\s*-)", r"\1", structured_clean)  # *italic* not in lists
        structured_clean = re.sub(r"(?<!^)_([^_\n]+)_(?!\s*-)", r"\1", structured_clean)  # _italic_ not in lists
        # Remove any remaining standalone ** or * (but not list markers)
        structured_clean = re.sub(r"\*\*", "", structured_clean)  # Remove remaining **
        structured_clean = re.sub(r"(?<!^)\*(?!\s*-)", "", structured_clean)  # Remove * not at start of line/list
        # Remove markdown links
        structured_clean = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", structured_clean)
        # Remove inline code markers (but preserve code blocks if needed)
        structured_clean = re.sub(r"`([^`]+)`", r"\1", structured_clean)
        
        if intro_clean:
            return f"{intro_clean}\n\n{structured_clean}"
        else:
            return structured_clean
    
    return intro_clean

def split_into_sentences(text: str) -> List[str]:
    """
    Разбить текст на предложения.
    """
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [sentence.strip() for sentence in sentences if sentence.strip()]

def translate_header(header: str) -> str:
    """
    Перевести заголовок на русский язык.
    """
    # Убираем двоеточие и пробелы для проверки
    clean_header = header.rstrip(":").strip().lower()
    translations = {
        "parameters": "Параметры",
        "parameter": "Параметры",
        "returns": "Возвращает",
        "return": "Возвращает",
        "raises": "Вызывает",
        "raise": "Вызывает",
    }
    translated = translations.get(clean_header, header)
    # Если исходный заголовок заканчивался на двоеточие, добавляем его обратно
    if header.rstrip().endswith(":"):
        return translated + ":"
    return translated

def format_as_bullet_list(text: str) -> List[str]:
    """
    Представить текст в виде маркерного списка, учитывая структурированные блоки.
    """
    clean_text = text.strip()
    if not clean_text:
        return []

    pattern = re.compile(r"(Parameters?|Returns?|Raises?):", re.IGNORECASE)
    parts = pattern.split(clean_text)

    if len(parts) == 1:
        sentences = split_into_sentences(clean_text)
        return [f"- {sentence}" for sentence in sentences] or [f"- {clean_text}"]

    items: List[str] = []
    leading = parts[0].strip()
    if leading:
        for sentence in split_into_sentences(leading):
            items.append(f"- {sentence}")

    seen_keys = set()
    for index in range(1, len(parts), 2):
        key = parts[index].strip()
        key_lower = key.lower().rstrip(":").strip()
        if key_lower in seen_keys:
            continue
        seen_keys.add(key_lower)
        
        # Переводим заголовок на русский - сначала пробуем прямой перевод
        translated_key = None
        for eng, rus in [("parameters", "Параметры"), ("returns", "Возвращает"), ("raises", "Вызывает")]:
            if key_lower == eng or key_lower == eng + ":":
                translated_key = rus + ":"
                break
        
        # Если прямой перевод не сработал, используем функцию translate_header
        if translated_key is None:
            translated_key = translate_header(key)
            # Если и это не сработало, пробуем еще раз без двоеточия
            if translated_key.lower().rstrip(":") == key_lower:
                for eng, rus in [("parameters", "Параметры"), ("returns", "Возвращает"), ("raises", "Вызывает")]:
                    if key_lower.startswith(eng):
                        translated_key = rus + ":"
                        break
        
        value = parts[index + 1] if index + 1 < len(parts) else ""
        # Добавляем отступ перед Returns и Raises (но не перед Parameters)
        if translated_key and any(keyword in translated_key for keyword in ["Возвращает", "Вызывает", "Returns", "Raises"]):
            items.append("")
        
        # Всегда используем обычный список вместо таблицы
        items.append(f"{translated_key}")
        # Парсим элементы для списка
        nested_items = parse_structured_items(value)
        if nested_items:
            items.extend([f"- {entry}" for entry in nested_items])
        else:
            # Если не удалось распарсить структурированно, разбиваем по строкам
            text_lines = value.split('\n')
            for text_line in text_lines:
                text_line = text_line.strip()
                if not text_line:
                    continue
                # Убираем маркеры списка, если они уже есть
                clean_line = re.sub(r'^[•\-\*]\s+', '', text_line).strip()
                if clean_line:
                    items.append(f"- {clean_line}")

    return items

def parse_structured_items(text: str) -> List[str]:
    """
    Разобрать строку вида \"- item1 - item2\" в отдельные пункты.
    """
    if not text or "-" not in text:
        return []

    chunks = re.split(r"\s*-\s+", text.strip())
    entries = []
    for chunk in chunks:
        cleaned = chunk.strip(" .")
        if cleaned:
            entries.append(cleaned)
    return entries

def parse_items_for_table(text: str) -> List[Dict[str, str]]:
    """
    Разобрать текст со списком элементов для создания таблицы.
    Ожидает формат: "- name (type): description" или "- name: description" или "• name (type): description"
    """
    if not text:
        return []
    
    rows = []
    # Сначала разбиваем на строки по переносам
    text_lines = text.split('\n')
    
    for text_line in text_lines:
        text_line = text_line.strip()
        if not text_line:
            continue
        
        # Убираем маркеры списка (•, -, *) в начале строки (может быть Unicode символ •)
        line = re.sub(r'^[•\-\*]\s+', '', text_line).strip()
        # Также убираем маркеры, если они идут после пробелов
        line = re.sub(r'^\s*[•\-\*]\s+', '', line).strip()
        if not line:
            continue
        
        # Пытаемся найти паттерн "name (type): description" или "name: description"
        # Сначала пробуем с типом в скобках - более гибкий паттерн
        match_with_type = re.match(r'^(.+?)\s*\(([^)]+)\)\s*:\s*(.+)$', line)
        if match_with_type:
            name = match_with_type.group(1).strip()
            type_info = match_with_type.group(2).strip()
            description = match_with_type.group(3).strip()
            rows.append({
                'name': f"{name} ({type_info})",
                'description': description
            })
            continue
        
        # Пробуем без типа: "name: description"
        match_simple = re.match(r'^(.+?)\s*:\s*(.+)$', line)
        if match_simple:
            name = match_simple.group(1).strip()
            description = match_simple.group(2).strip()
            # Проверяем, что это не просто случайное двоеточие в тексте
            if len(name) > 0 and len(description) > 0:
                rows.append({
                    'name': name,
                    'description': description
                })
                continue
        
        # Если строка содержит ":" но не соответствует паттернам выше, пробуем разбить по первому ":"
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2:
                name_part = parts[0].strip()
                desc_part = parts[1].strip()
                # Если первая часть короткая (вероятно имя), а вторая длинная (описание)
                if len(name_part) < 50 and len(desc_part) > 0:
                    rows.append({
                        'name': name_part,
                        'description': desc_part
                    })
                    continue
    
    # Возвращаем только если нашли хотя бы один элемент
    return rows if len(rows) > 0 else []

def split_description_content(text: str) -> Tuple[str, str]:
    """
    Разделить описание на общую часть и структурированные блоки (Parameters/Returns/Raises).
    """
    pattern = re.compile(r"(Parameters?|Returns?|Raises?):", re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return text, ""
    return text[: match.start()].strip(), text[match.start():].strip()


def contains_cyrillic(text: str) -> bool:
    """Проверка наличия кириллицы, чтобы не переводить уже русские тексты."""
    return bool(re.search(r"[а-яА-ЯёЁ]", text or ""))


def translate_text_if_needed(text: Optional[str]) -> str:
    """
    Перевести английский текст на русский через LLM, если возможно.
    Не трогаем русские/пустые строки, при ошибке возвращаем оригинал.
    """
    if not text or contains_cyrillic(text):
        return text or ""

    try:
        from src.services.llm_service import translate_to_russian
    except Exception:
        return text

    try:
        translated = translate_to_russian(text)
        return translated or text
    except Exception as exc:  # noqa: B902
        logger.debug(f"Translation skipped: {exc}")
        return text
