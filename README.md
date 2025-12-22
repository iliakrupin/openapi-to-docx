# OpenAPI to Docx Generator

A FastAPI-based service that converts OpenAPI 3.0+ JSON specifications into comprehensive Markdown documentation and exports it as DOCX files.

## Features

- Upload OpenAPI JSON files via HTTP
- Generate structured Markdown documentation of all endpoints
- Automatic parsing and formatting of OpenAPI specifications
- Supports all standard OpenAPI features:
  - Paths and methods
  - Parameters (query, path, header, cookie)
  - Request/response bodies
  - Examples and schemas
  - Security requirements
  - Descriptions and summaries

## API Endpoint

```
POST /generate-doc
```

### Request

- `openapi_file`: Upload an OpenAPI 3.0+ JSON file

### Response

The endpoint returns a DOCX file generated from the template `template_files/api_template.md`.
The file is sent as an attachment (`application/vnd.openxmlformats-officedocument.wordprocessingml.document`),
so it needs to be saved to disk (see example below).

## Usage

### 1. Run with Docker (Recommended)

**Using docker-compose (recommended):**

```bash
docker-compose up -d --build
```

This automatically loads environment variables from `.env` file.

**Using docker run directly:**

```bash
docker build -t openapi-to-docx .
docker run -d --env-file .env -p 8000:8000 --name api-doc-generator openapi-to-docx
```

**Note:** When using `docker run`, you must pass `--env-file .env` to load environment variables. Without it, LLM features will be disabled.

### 1a. Local setup with uv

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
uv run uvicorn src.main:app --reload
```

### 2. Send request

```bash
curl -X POST http://localhost:8000/generate-doc \
  -F "file=@openapi.json" \
  -o documentation.docx
```

#### Synchronous/Asynchronous Mode Configuration

If you set the `x-interface-mode` extension at the operation or global level
(`sync`, `async`, `synchronous`, `asynchronous`, etc.), it will automatically appear
in the "Synchronous/Asynchronous" table. If the extension is not present, the value is taken
from the text (by keywords `async`/`asynchronous`) or defaults to
"Synchronous".

## How It Works

The service supports two generation modes:

### Local Parsing Mode (Default)

1. **Parsing** the OpenAPI spec to extract endpoints, methods, parameters, and schemas
2. **Grouping** operations by tags for organized documentation
3. **Generating** Markdown content following the template structure (`template_files/api_template.md`)
4. **Converting** Markdown to DOCX format using python-docx library
5. **Returning** the DOCX file as a downloadable attachment

All processing is done locally without external API calls. Fast and deterministic.

### LLM Enhancement Mode

1. **Parsing** the OpenAPI spec locally (fast)
2. **Enhancing** descriptions using LLM:
   - Improves short or missing endpoint descriptions
   - Generates descriptions for fields without descriptions (based on field name and type)
   - Translates English text to Russian
3. **Generating** Markdown content with enhanced descriptions
4. **Converting** Markdown to DOCX format
5. **Returning** the DOCX file as a downloadable attachment

LLM enhancement provides better descriptions while maintaining fast processing speed. Falls back to local parsing if LLM calls fail.

Both modes include:
- Endpoint descriptions and summaries
- Request/response formats and examples
- Parameter tables with types and descriptions
- Authentication requirements
- Interface mode (sync/async) detection

## Generation Modes

The service supports two generation modes:

1. **Local Parsing (default)**: Fast, deterministic parsing of OpenAPI spec without external API calls
2. **LLM Enhancement Mode**: Local parsing + LLM improves descriptions and generates missing field descriptions

### Switching Modes

**Two Generation Modes:**

1. **Local Parsing (default, fastest)**: Direct parsing, 1-2 seconds
   - No external API calls
   - Fast and deterministic
   - Fields without descriptions will show "Нет описания" or empty

2. **LLM Enhancement (recommended, fast)**: Local parsing + LLM improves descriptions, ~10-30 seconds
   - Improves short or missing endpoint descriptions
   - **Generates descriptions for fields without descriptions** based on field name and type
   - Translates English text to Russian
   - Falls back to local parsing if LLM is unavailable

**Explicit Control via Environment Variables:**
```bash
USE_LLM_ENHANCE=true  # LLM enhancement mode (fast, recommended)
```

**Via API Query Parameters:**
```bash
# Local parsing (fastest)
curl -X POST "http://localhost:8000/generate-doc?use_llm_enhance=false" \
  -F "file=@openapi.json" -o doc.docx

# LLM enhancement (recommended - fast + improved descriptions)
# Automatically generates descriptions for fields without descriptions
curl -X POST "http://localhost:8000/generate-doc?use_llm_enhance=true" \
  -F "file=@openapi.json" -o doc.docx
```

Query parameters override environment variable settings.

## Environment Variables

| Variable | Purpose | Required | Default |
|----------|--------|----------|---------|
| `USE_LLM` | Full LLM generation mode (`true`/`false`). If not set, auto-detected from LM_STUDIO vars | No | Auto-detect |
| `USE_LLM_ENHANCE` | LLM enhancement mode - improve descriptions only (`true`/`false`) | No | `false` |
| `LM_STUDIO_API_URL` | Base URL for LM Studio | Yes (if LLM mode enabled) | None |
| `LM_STUDIO_API_TOKEN` | API token for LM Studio | Yes (if LLM mode enabled) | None |
| `LM_STUDIO_MODEL_NAME` | Model name | No | `Qwen/Qwen3-30B-A3B-FP8` |
| `LM_STUDIO_MAX_TOKENS` | Token limit | No | `28000` |
| `LM_STUDIO_CHUNK_SIZE` | Chunk size | No | `10000` |
| `TEMP_DIR` | Directory for temporary files | No | `temp` |

**Note:** 
- `USE_LLM_ENHANCE=true` uses LLM to:
  - Improve short or missing endpoint descriptions
  - **Generate descriptions for fields without descriptions** (based on field name and type)
  - Translate English text to Russian
- The service will fall back to local parsing if LLM is unavailable or fails
- When using `docker run`, pass `--env-file .env` to load environment variables
- When using `docker-compose`, environment variables are automatically loaded from `.env` file

## Limitations

- Processing is synchronous — full response returned after processing
- Large OpenAPI specs are processed in memory (no chunking for very large files)
- Output format is limited to DOCX (Markdown generation is available internally)

## Features

- **Automatic field description generation**: When `use_llm_enhance=true`, fields without descriptions automatically get descriptions generated by LLM based on field name and type
- **Smart description enhancement**: Improves short or missing endpoint descriptions
- **Translation support**: Automatically translates English text to Russian
- **Flexible deployment**: Works with docker-compose or docker run

## Future Improvements

- Implement chunked processing for very large OpenAPI specs
- Add caching layer for frequently requested specs
- Support multiple output formats (HTML, PDF)
- Add UI dashboard for file upload and preview

## License

MIT License
"