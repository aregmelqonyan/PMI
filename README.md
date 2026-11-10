# EngiReq-AI interim pilot

Turns text-native engineering PDFs into structured requirement records. Each record is tied to the exact
characters it came from, checked by deterministic rules, and routed to a human reviewer.

Research prototype. Passing the checks means a record is consistent with its source text, not that it is correct
engineering. A qualified engineer remains the authority.

## Run

    ./run.sh

Then open http://127.0.0.1:8000. The first run creates the Python environment and installs the frontend packages.
Needs Python 3.11+ and Node 18+. Data stays in `backend/data/`.

For frontend development, run `uvicorn engireq.api:app --port 8000` from `backend/` and `npm run dev` from `frontend/`.

## Workflow

1. **Documents**: upload a PDF, or load the synthetic sample.
2. **Records**: review each requirement beside the highlighted source page. Keys: `J`/`K` move, `A` accept, `R` reject, `E` correct.
3. **Label passages**: mark passages as requirement or not. These labels are the gold set.
4. **Split**: set each document to Development or Held-out test. Do not tune rules on test documents.
5. **Evaluation**: precision, recall, F1, document-level bootstrap intervals, error examples and review time.
6. **Export**: approved or all records as JSONL or CSV.

## Implemented from the proposal

| Item | Status |
|---|---|
| PDF parsing with page, block and character coordinates | Done |
| B0 rule baseline with the shared record schema | Done |
| Schema, exact-span, value, unit and polarity checks | Done |
| Abstention, human review, audit trail, JSONL and CSV export | Done |
| Measured metrics from human labels, with held-out split | Done, needs your labels |
| DOCX, OCR, table-aware parsing | Not built |
| B1 TF-IDF, B2 encoder, B3 LLM, B4 hybrid | Not built |

## Tests

    cd backend && .venv/bin/python -m pytest -q

The regression fixture was written alongside the rules. It guards behavior and is not an accuracy result.

## Data rights

Publicly readable documents are not automatically redistributable. Keep `backend/data/` out of any public repository.
PyMuPDF is AGPL or commercially licensed, so review its terms before distributing this software.

## Deploy on Render

Create a Blueprint from this repository. Render reads `render.yaml` and builds the `Dockerfile`.

The deployed app has no login, so anyone with the URL can see and delete documents. Upload only documents you may share.
On the free plan the disk is temporary, so documents, labels and reviews are lost on each restart or deploy.
