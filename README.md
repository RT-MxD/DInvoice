# 🧾 Automated Invoice Pipeline

An end-to-end, **fully local & free** financial pipeline that fetches invoices
from an external source, extracts the important fields with a **local Ollama
LLM** (with **OCR** for scanned images), validates them through a configurable
**guardrails** layer, stores clean structured records in a database, and exposes
a **web API + browser UI** — all with **zero paid services**.

```
   invoices        ┌──────────┐   ┌──────────────┐   ┌─────────────┐   ┌──────────────┐   ┌────────────┐
 (folder / email / │  FETCH   │   │   OCR / read  │   │   EXTRACT   │   │  GUARDRAILS  │   │   STORE    │
  web upload)      │  inbox   ├──►│ scans → text  ├──►│   Ollama    ├──►│  validate &  ├──►│  database  │
                   │  / IMAP  │   │ (Tesseract)   │   │ (local LLM) │   │   redact     │   │ (SQLite…)  │
                   └──────────┘   └──────────────┘   └─────────────┘   └──────┬───────┘   └────────────┘
                                                                              │ fails rules
                          Browse / upload / review it all in the web UI  ◄────┴──► data/quarantine/
```

## Architecture

| Stage | File | What it does |
|-------|------|--------------|
| **Fetch** | `src/fetcher.py` | Reads new invoices from a drop folder (`data/inbox/`), an IMAP mailbox, or a web upload. Normalizes to text + a content hash. |
| **OCR** | `src/ocr.py` | Scanned **images** (PNG/JPG/TIFF…) and **image-only PDFs** are read with Tesseract. Text PDFs skip OCR automatically. |
| **Extract** | `src/extractor.py` | Sends text to Ollama in strict JSON mode; validates with Pydantic (`src/schemas.py`). |
| **Guardrails** | `src/guardrails.py` + `guardrails.yaml` | Required fields, numeric bounds, currency allow-list, arithmetic cross-checks, date sanity, confidence thresholds, dedupe, PII redaction. |
| **Store** | `src/database.py` + `src/models.py` | Persists invoices + line items to SQL (SQLite by default). Idempotent via content hash; keeps an audit log. |
| **API + UI** | `src/api.py` + `webapp/index.html` | FastAPI backend and a browser dashboard to upload, process, browse, and triage invoices. |
| **Orchestrate** | `src/pipeline.py`, `main.py` | Wires the stages together with logging, quarantine, and a CLI. |

Everything is driven by config, not code — `requirements.txt`, `guardrails.yaml`,
and `.env`.

---

## Quick start (local)

### 1. Install the free local tools
```bash
# Ollama — the local LLM  (https://ollama.com/download)
ollama serve
ollama pull llama3.2          # ~2 GB. Alternatives: mistral, qwen2.5:3b

# OCR engine + PDF rasterizer (only needed for scanned images / image PDFs)
brew install tesseract poppler          # macOS
# sudo apt-get install tesseract-ocr poppler-utils   # Debian/Ubuntu
```

### 2. Python environment
```bash
cd invoice_pipeline
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # optional — defaults work out of the box
```

### 3a. Run the web UI 🖥️  (recommended)
```bash
python main.py serve          # or: uvicorn src.api:app --reload
# open http://localhost:8000
```
Drag-and-drop a PDF / scanned image / text invoice, hit **Process Inbox**, and
watch invoices appear. Low-confidence ones are flagged **needs review**; ones
that fail a hard rule land in **Quarantine** with the reason shown.

### 3b. …or run the CLI
```bash
python main.py seed           # copies 4 sample invoices (incl. a scanned image) into data/inbox/
python main.py run --no-email
python main.py list           # stored invoices
python main.py stats          # counters + recent audit log
```

Expected: ACME (USD) + Northwind (a **scanned PNG**, read via OCR) store cleanly,
Initech (EUR) stores but is flagged **needs review** (lower confidence), and the
Globex sample is **quarantined** (currency `AED` not allowed + totals don't add
up).

---

## Supported invoice formats

| Type | Extensions | How it's read |
|------|-----------|---------------|
| Text | `.txt` `.md` | Read directly |
| Text PDF | `.pdf` | `pdfplumber` extracts the embedded text |
| **Scanned PDF** | `.pdf` (no text layer) | Auto-detected → **OCR** (rasterize + Tesseract) |
| **Scanned image** | `.png` `.jpg` `.jpeg` `.tif` `.tiff` `.bmp` `.webp` | **OCR** (Tesseract) |

OCR is on by default; set `OCR_ENABLED=false` to disable. If the Tesseract/Poppler
binaries are missing, the pipeline logs a clear, actionable message instead of
crashing.

---

## Web API

Interactive docs at `http://localhost:8000/docs` (Swagger, auto-generated).

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/` | The browser UI |
| `GET` | `/api/health` | Ollama reachability, OCR status, model, processing flag |
| `GET` | `/api/stats` | Counters (stored / needs_review / quarantined / total value) |
| `POST` | `/api/upload` | Upload an invoice file (multipart); optional `process=true` |
| `POST` | `/api/process` | Run one pipeline pass over the inbox (background task) |
| `GET` | `/api/invoices?status=` | List invoices (filterable) |
| `GET` | `/api/invoices/{id}` | Invoice detail + line items |
| `POST` | `/api/invoices/{id}/approve` | Mark a `needs_review` invoice as `stored` |
| `DELETE` | `/api/invoices/{id}` | Delete an invoice |
| `GET` | `/api/quarantine` | Quarantined files + violation reasons |
| `GET` | `/api/logs` | Recent processing audit log |

**Free by design:** extraction uses your local Ollama model and OCR uses local
Tesseract — no request ever leaves your machine, and there are no API keys or
usage charges anywhere.

---

## Docker 🐳

The included `docker-compose.yml` runs the **whole stack** — the app (with OCR
baked in) *and* an Ollama server — with no host setup beyond Docker:

```bash
docker compose up -d --build
docker compose exec ollama ollama pull llama3.2   # one-time model download
open http://localhost:8000
```

- `tesseract-ocr` + `poppler-utils` are installed in the image, so OCR works out
  of the box.
- The SQLite DB and inbox/processed/quarantine folders are bind-mounted to
  `./data`, so data persists across restarts.
- `guardrails.yaml` is mounted too — tweak rules and just restart the `app`
  container, no rebuild.

Prefer to run Ollama on the host instead? Build only the app image and point it
at the host: `docker build -t invoice-app . && docker run -p 8000:8000 \
-e OLLAMA_HOST=http://host.docker.internal:11434 -v $(pwd)/data:/app/data invoice-app`

---

## Using a real database

Swap SQLite for Postgres/MySQL by setting `DATABASE_URL` in `.env` and installing
the driver (see `requirements.txt`):
```ini
DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/invoices
```
The ORM schema (`src/models.py`) is portable — no code changes needed.

---

## The database schema

- **`invoices`** — one row per invoice, `UNIQUE(vendor_name, invoice_number)` to
  block duplicates. `status` is `stored` or `needs_review`.
- **`line_items`** — child rows (description, qty, unit price, amount).
- **`processing_log`** — audit trail: one row per file per stage.

```sql
SELECT * FROM invoices WHERE status = 'needs_review';   -- triage queue
```

---

## Guardrails reference (`guardrails.yaml`)

Each rule group has an enforcement level: `block` → quarantine, `warn` → store
but flag `needs_review`. Checks: required fields · numeric min/max · currency
allow-list · line-items-sum & subtotal+tax arithmetic (with tolerance) · date
age/future/due-date · model-confidence floor & auto-approve threshold · dedupe by
content hash and vendor+number · regex PII redaction (cards, IBANs).

---

## Testing

```bash
pytest -q          # 13 tests: guardrails logic + API integration (no Ollama needed)
```
Tests run against an isolated temp database (see `tests/conftest.py`) — they never
touch your real invoices.

## Project layout

```
invoice_pipeline/
├── main.py                 # CLI: run / watch / list / stats / seed / serve
├── requirements.txt
├── guardrails.yaml         # all validation rules (edit me)
├── .env.example
├── Dockerfile              # app image (OCR baked in)
├── docker-compose.yml      # app + ollama, one command
├── src/
│   ├── config.py           # env-driven configuration
│   ├── fetcher.py          # folder + IMAP ingestion, routes scans to OCR
│   ├── ocr.py              # Tesseract OCR for images & scanned PDFs
│   ├── extractor.py        # Ollama JSON extraction
│   ├── schemas.py          # Pydantic models (structural validation)
│   ├── guardrails.py       # rule engine (semantic validation)
│   ├── models.py           # SQLAlchemy ORM schema
│   ├── database.py         # persistence + audit log + API read helpers
│   ├── pipeline.py         # orchestration
│   └── api.py              # FastAPI backend
├── webapp/
│   └── index.html          # single-page browser UI (no build step)
├── tests/
│   ├── conftest.py         # isolated temp DB for tests
│   ├── test_guardrails.py
│   └── test_api.py
└── data/
    ├── samples/            # example invoices (incl. a scanned PNG)
    ├── inbox/ · processed/ · quarantine/
```

## Extending it

- **New source** (S3, Drive, webhook): add a function to `fetcher.py` returning
  `FetchedInvoice` objects.
- **New rule**: add a `_check_*` method in `guardrails.py` and a block in
  `guardrails.yaml`.
- **Other languages**: set `OCR_LANGUAGE=eng+deu` (install the Tesseract lang pack).
- **Scale**: point `DATABASE_URL` at Postgres and run multiple workers — the
  content-hash idempotency prevents double-storing.
```
