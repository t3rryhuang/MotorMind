# Car-Hoot

Car-Hoot is a hackathon-style **automotive electronics education** prototype built with **Django** and **Django REST Framework**. Teachers manage courses, training videos (with sections and transcripts), quizzes, and AR-style practical tasks. Students watch videos (with timestamp jumps), take quizzes, and update AR task progress. JSON APIs are included for a future iOS AR companion app.

Teachers can also maintain a **Resource Library**: upload PDFs / notes / manuals / transcripts, associate them with **one or many courses** (ManyToMany), ingest them into a **local ChromaDB** vector index, and run **semantic retrieval tests** (RAG-ready, without storing per-chunk rows in SQLite).

## Requirements

- Python 3.10+ recommended
- pip

## Quick start

```bash
cd CarHoot
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # optional; set SECRET_KEY, and GOOGLE_API_KEY if you use “AI write description”
python3 manage.py migrate
python3 manage.py check_trainingvideo_schema   # optional: verify TrainingVideo columns exist
python3 manage.py seed_demo
python3 manage.py runserver
```

Open http://127.0.0.1:8000/

### YouTube auto-fill (training videos)

On **Add / Edit training video**, teachers paste a YouTube URL first, then use **Auto-fill title and transcript**:

- **Title and thumbnail** come from YouTube **oEmbed** (`https://www.youtube.com/oembed`) — **no YouTube Data API key**.
- **Transcript** comes from **`youtube-transcript-api`**, preferring **manually created English** captions, then **auto-generated English** captions. Sources are labeled in the UI as **YouTube captions** or **Auto-generated YouTube captions** (not AI transcription).
- If no captions exist, the transcript field is left empty and the UI shows a clear warning: add a transcript manually or configure **audio transcription** later (not implemented yet; **`yt-dlp`** is listed in requirements for future metadata / pipeline work — see TODO in `courses/services/youtube.py`).
- **AI write description** calls Google **Generative AI** when **`GOOGLE_API_KEY`** is set in `.env` (from [Google AI Studio](https://aistudio.google.com/app/apikey)). Model name defaults to **`GOOGLE_MODEL_NAME=gemma-3-27b-it`**; override if your project uses another supported model. If the key is missing, the UI shows a clear “not configured” message instead of crashing.
- **Never commit API keys.** Keep secrets in `.env` (gitignored). If a key was ever exposed in chat or a ticket, **rotate it** in Google Cloud / AI Studio.

After pulling changes that touch `courses.models.TrainingVideo`, always run:

```bash
python manage.py makemigrations   # if you changed models locally
python manage.py migrate
python manage.py check_trainingvideo_schema
```

If you see `OperationalError: no such column ... thumbnail_url`, the database is behind the models — `migrate` (and migration `0003_repair_trainingvideo_columns` if history is inconsistent) brings SQLite in sync **without** deleting `db.sqlite3`.

### Demo logins (from `seed_demo`)

| Role    | Username  | Password    |
|---------|-----------|-------------|
| Teacher | `teacher` | `teacher123` |
| Student | `student1` | `student123` |
| Student | `student2` | `student123` |

Django admin: http://127.0.0.1:8000/admin/ — create a superuser with `python3 manage.py createsuperuser` if you need full admin access.

## Project layout

- `carhoot/` — project settings and root URLconf
- `accounts/` — login/logout, dashboard, teacher **admin panel** (courses + resource library; course editor nests videos/sections, quizzes, AR tasks), `Profile` (teacher/student)
- `courses/` — `Course`, `TrainingVideo`, `VideoSection`, landing page, course/video views
- `quizzes/` — quiz models, take quiz / results
- `ar_tasks/` — AR task models, task detail, progress updates (web POST)
- `resources/` — **Resource library**, ingestion jobs, retrieval logs, Chroma vector services
- `api/` — DRF serializers and read-mostly endpoints for mobile clients
- `templates/` — Bootstrap 5 base layout and page templates

## URLs (web)

| Path | Description |
|------|-------------|
| `/` | Landing |
| `/login/`, `/logout/` | Auth |
| `/dashboard/` | Role-aware dashboard |
| `/courses/` | Course cards |
| `/courses/<id>/` | Course detail (videos, quizzes, AR tasks) |
| `/courses/<id>/videos/<video_id>/` | Video + sections; use `?t=90` to start near 90s (YouTube embed) |
| `/admin-panel/` | Teacher-only custom panel (your courses, resources; `/admin-panel/manage/course/<id>/` edits a course) |
| `/admin-panel/resources/` | **Teacher-only** resource dashboard (upload + table) |
| `/admin-panel/resources/test/` | **Teacher-only** retrieval test UI |
| `/admin-panel/videos/youtube-autofill/` | **Teacher-only** POST JSON — oEmbed + captions for the video form |
| `/admin-panel/videos/ai-description/` | **Teacher-only** POST JSON — optional Gemini/Gemma description |

## Resource library / vector database

### Book upload workflow (ISBN PDFs)

1. **Rename** the PDF to its ISBN (hyphens/spaces allowed), for example `9780415725774.pdf` or `978-0-415-72577-4.pdf`.
2. Open **Resource Library** (`/admin-panel/resources/`) and upload the file.
3. Optionally select **one or more courses** (checkboxes).
4. Leave **Resource type** on **Auto** for PDFs (defaults to **book**) or pick a type explicitly.
5. Car-Hoot **validates ISBN-10 / ISBN-13 checksums**, then tries **Open Library** and **Google Books** to auto-fill title/author/publisher/year/description when possible.
6. If lookup fails, the resource is still created with the ISBN as the working title; use **Retry metadata lookup** on the detail page, **Edit metadata**, or `python3 manage.py lookup_resource_metadata <id>` after fixing data.
7. **Scanned/image-only PDFs** may not contain extractable text — ingestion may fail until OCR is applied (outside this prototype).

**ISBN notes**

- **ISBN-13** and **ISBN-10** (including `X` check digit) are supported.
- Hyphens/spaces in the filename are ignored for validation.
- A filename like `bad_book.pdf` will be rejected for **book** uploads because it does not contain a valid ISBN.
- **Checksums are enforced**: a string that “looks like” an ISBN but fails the ISBN-10/ISBN-13 check digit rules will be rejected.

Invalid ISBN upload (HTTP 400 JSON):

```json
{ "error": "Book PDF filenames must be valid ISBNs, for example 9780415725774.pdf" }
```

Minimal multipart upload (teacher):

```bash
curl -u teacher:teacher123 -X POST http://127.0.0.1:8000/api/resources/upload/ \
  -F "uploaded_file=@/path/to/9780415725774.pdf" \
  -F "course_ids=1"
```

### ISBN metadata lookup

- **Book PDFs** should be named with a valid ISBN, for example `9780080969459.pdf` (hyphens allowed in the stem).
- Car-Hoot calls **Open Library** first (`GET https://openlibrary.org/isbn/{ISBN}.json`, 10s timeout). Many editions list authors only on the linked **work** record; the app follows `/works/...` and `/authors/...` links to resolve names.
- If Open Library is missing useful fields, **Google Books** is used as **fallback and enrichment** (`GET https://www.googleapis.com/books/v1/volumes?q=isbn:{ISBN}`).
- Lookup can **fail** if the ISBN is unknown, an API error occurs, or the server has **no outbound internet** — the `Resource` is still created, `title` falls back to the ISBN, `metadata_lookup_status` is set to **failed**, and **ingestion / ChromaDB** still runs.
- Teachers can **retry** lookup from the resource detail page (**Retry metadata lookup**) or run:
  - `python3 manage.py lookup_isbn 9780080969459` — prints normalized JSON and `metadata_source`
  - `python3 manage.py lookup_resource_metadata <resource_id>` — updates the row and prints before/after title, author, publisher, year
- Teachers can **manually edit** metadata (including ISBN) on the edit form if lookup is incomplete.

### What is stored where

- **SQLite** stores only **high-level metadata** (`Resource`), **ingestion jobs** (`ResourceIngestionJob`), **retrieval logs** (`ResourceRetrievalLog`), and the **ManyToMany** link between `Resource` and `Course`.
- **ChromaDB** (on disk under `vector_db/`) stores **one vector per text chunk**, including the **full chunk text** as the Chroma **document**, embeddings, and rich **metadata** (resource id/title/type, course ids/titles, page number, chunk index, char offsets, etc.).
- `Resource.chunk_count` is a **UI counter** mirrored from ingestion; there is **no** `ResourceChunk` table and **no** per-chunk SQLite rows.

### Many-to-many courses

`Resource.courses` is a **ManyToManyField** to `courses.Course` (no `ForeignKey` from `Resource` → `Course`). A resource can belong to **zero, one, or many** courses, and a course can have many resources.

When course associations change, Car-Hoot **updates Chroma metadata only** (`course_ids_csv`, `course_titles_csv`, JSON mirrors) on existing chunk vectors — **no** full re-extraction, re-chunking, or re-embedding. Use **Re-ingest** on the resource detail page when you actually need to rebuild vectors from the file.

### Embeddings (local)

The project tries **`sentence-transformers`** first, but many developer machines have broken global TensorFlow/Keras stacks that can break `import sentence_transformers`. In that case Car-Hoot **falls back** to Chroma’s bundled **ONNX MiniLM** embedding function (still `all-MiniLM-L6-v2`-class, 384-dim).

- TODO: swap in `OpenAIEmbeddingFunction` (see `resources/services/embeddings.py`) for hosted embeddings.

### Chroma metadata filtering note

Chroma metadata values are scalars. Course membership is stored as:

- `course_ids_csv` like `1,2,3` (simple `$contains` / Python filtering)
- `course_ids_json` as a JSON string list (debuggable / future filtering)

Course-filtered retrieval uses **Python-side filtering** after vector search when needed (hackathon-friendly, avoids brittle list-metadata queries).

### Reset / wipe vectors

```bash
python3 manage.py clear_vector_db
```

This deletes the `carhoot_resources` Chroma collection and recreates an empty one. It does **not** delete Django `Resource` rows; re-run **Re-ingest** from the UI (or `python3 manage.py ingest_resource <id>`) to rebuild vectors.

### Management commands

- `python3 manage.py seed_demo` — demo users/content + optional demo text resource ingest (skips vector ingest if dependencies fail).
- `python3 manage.py ingest_resource <resource_id>` — run ingestion synchronously.
- `python3 manage.py lookup_resource_metadata <resource_id>` — re-fetch book metadata using `Resource.isbn`.
- `python3 manage.py clear_vector_db` — drop/recreate the Chroma collection.
- `python3 manage.py test_vector_search "your query"` — quick CLI vector search.

## JSON API (authenticated)

All routes are under **`/api/`** and require authentication (session or basic auth in development).

### Existing course / AR endpoints

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/courses/` | Course list |
| GET | `/api/courses/<id>/` | Course detail (nested videos w/ sections, quizzes, AR tasks) |
| GET | `/api/courses/<id>/videos/` | Videos for a course |
| GET | `/api/videos/<id>/sections/` | Sections for a video |
| GET | `/api/courses/<id>/quizzes/` | Quizzes for a course |
| GET | `/api/quizzes/<id>/` | Quiz + nested questions + choices |
| GET | `/api/courses/<id>/ar-tasks/` | AR tasks for a course |
| GET | `/api/ar-tasks/<id>/` | AR task + steps + linked section |
| POST | `/api/ar-tasks/<id>/progress/` | Body: `status`, `notes` — **student** role (staff exempt) |

### Teacher-only resource endpoints

These require a **teacher** profile (or Django staff/superuser):

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/resources/` | List resources + linked courses |
| GET | `/api/resources/<id>/` | Detail + `chunk_count` + courses |
| POST | `/api/resources/upload/` | **Multipart**: `uploaded_file` (required), optional `course_ids`, optional `resource_type`. **No manual title/author required** — book PDFs must use an ISBN filename. Returns `{ "resource": { ... } }` |
| POST | `/api/resources/<id>/ingest/` | Re-run ingestion |
| DELETE | `/api/resources/<id>/` | Deletes SQLite row, uploaded file, and Chroma vectors |
| POST | `/api/resources/search/` | Semantic search JSON body `{ "query": "...", "top_k": 5, "course_id": 1, "resource_type": "notes", "resource_id": 2 }` (filters optional except `query`) |

Example (teacher basic auth):

```bash
curl -u teacher:teacher123 -X POST http://127.0.0.1:8000/api/resources/search/ \
  -H "Content-Type: application/json" \
  -d '{"query":"how do you test a car fuse?","top_k":3,"course_id":1}'
```

Example (student AR progress):

```bash
curl -u student1:student123 -X POST http://127.0.0.1:8000/api/ar-tasks/1/progress/ \
  -H "Content-Type: application/json" \
  -d '{"status":"completed","notes":"Simulated fault isolated"}'
```

## Notes

- **Large PDF uploads**: there is no app-enforced file size cap. Django’s `DATA_UPLOAD_MAX_MEMORY_NUMBER` is raised (default **200 MB** request body; override with `DATA_UPLOAD_MAX_MEMORY_MB` in `.env`). Very large books produce more Chunks → longer CPU time during synchronous ingest.
- **SQLite** is used for development (`db.sqlite3`).
- **Bootstrap 5** is loaded from a CDN in `templates/base.html`.
- AR tasks are **virtual fault simulations** on a healthy vehicle; readings are instructional, not live OBD.
- Uploaded files are stored under `MEDIA_ROOT/resources/` (served in `DEBUG` mode from `/media/`).
