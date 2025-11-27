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

### 1. Run with Docker

```bash
docker build -t openapi-to-docx .
docker run -p 8000:8000 openapi-to-docx
```

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

### LLM Mode

1. **Sending** OpenAPI spec to Qwen3 model via LM Studio API
2. **Generating** enhanced documentation with LLM assistance
3. **Converting** Markdown to DOCX format
4. **Returning** the DOCX file as a downloadable attachment

LLM mode provides more natural language descriptions and can handle complex documentation requirements. Falls back to local parsing if LLM call fails.

Both modes include:
- Endpoint descriptions and summaries
- Request/response formats and examples
- Parameter tables with types and descriptions
- Authentication requirements
- Interface mode (sync/async) detection

## Generation Modes

The service supports two generation modes:

1. **Local Parsing (default)**: Fast, deterministic parsing of OpenAPI spec without external API calls
2. **LLM Mode**: Enhanced documentation generation using Qwen3 via LM Studio API

### Switching Modes

**Three Generation Modes:**

1. **Local Parsing (default, fastest)**: Direct parsing, 1-2 seconds
2. **LLM Enhancement (recommended, fast)**: Local parsing + LLM improves short descriptions, ~10-30 seconds
3. **Full LLM Generation (slowest)**: Complete LLM generation, 3+ minutes for large files

**Automatic Detection:**
If both `LM_STUDIO_API_URL` and `API_TOKEN` are set, full LLM mode is automatically enabled. Otherwise, local parsing is used.

**Explicit Control via Environment Variables:**
```bash
USE_LLM=true          # Full LLM generation (slow)
USE_LLM_ENHANCE=true  # LLM enhancement only (fast, recommended)
```

**Via API Query Parameters:**
```bash
# Local parsing (fastest)
curl -X POST "http://localhost:8000/generate-doc?use_llm=false" \
  -F "file=@openapi.json" -o doc.docx

# LLM enhancement (recommended - fast + improved descriptions)
curl -X POST "http://localhost:8000/generate-doc?use_llm_enhance=true" \
  -F "file=@openapi.json" -o doc.docx

# Full LLM generation (slow but comprehensive)
curl -X POST "http://localhost:8000/generate-doc?use_llm=true" \
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
- If both `LM_STUDIO_API_URL` and `API_TOKEN` are set, full LLM mode is automatically enabled
- `USE_LLM_ENHANCE=true` uses LLM only to improve short/missing descriptions (much faster than full LLM)
- You can explicitly disable LLM mode by setting `USE_LLM=false`
- The service will fall back to local parsing if LLM generation fails

## Limitations

- Processing is synchronous — full response returned after processing
- Large OpenAPI specs are processed in memory (no chunking for very large files)
- Output format is limited to DOCX (Markdown generation is available internally)

## Future Improvements

- Add LLM integration for enhanced documentation generation (Qwen3 via LM Studio)
- Implement chunked processing for very large OpenAPI specs
- Add caching layer for frequently requested specs
- Support multiple output formats (HTML, PDF)
- Add UI dashboard for file upload and preview

## License

MIT License
"