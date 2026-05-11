# MotorMind

MotorMind is an **automotive electronics education** prototype built with **Django** and **Django REST Framework**. Teachers manage **courses** (with optional icons), **training videos** (transcripts, paragraph timestamps, **learning sections**), **quizzes** and a **resource library** with vector search. Students browse courses, watch embedded video with section-based navigation, take quizzes (with leaderboards and optional **Solana Devnet** skill badges) and use an **AI tutor** on each course page.

**AR tasks:** the `ar_tasks` app (models + `/api/` endpoints) remains for a possible future companion app, but **AR task pages and navigation were removed from the public web UI** so the shipped teacher/student experience focuses on video, quizzes, reading and tutor.

Teachers can maintain a **Resource Library**: upload PDFs / notes / manuals / transcripts, associate them with **one or many courses** (ManyToMany), ingest them into a **local ChromaDB** vector index and run **semantic retrieval tests** (RAG-ready, without storing per-chunk rows in SQLite).

## Requirements

- Python 3.10+ recommended
- pip

## Quick start

```bash
cd MotorMind
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # optional; set SECRET_KEY and GOOGLE_API_KEY if you use “AI write description”
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

### Learning sections (suggested + saved)

On **Edit training video**, after **Suggest learning sections**, the table is a draft until it is stored:

- **Add selected sections** / **Replace existing sections with suggestions** POSTs to the apply API and persists `VideoSection` rows.
- **Save** (main form) also **appends** checked suggested rows to the database (when the video already exists and suggestions are present), then saves the video fields — so you do not lose sections if you only hit **Save**.

### AI Tutor / ElevenLabs (course page)

On **`/courses/<id>/`**, logged-in users see a floating **Talk to tutor** control. They can type (or use the browser **Web Speech API** where supported) to ask questions; the server builds context from the course title/description, reading page (plain text + citations), training video transcripts and section timestamps, the latest saved top reading chunks, quiz questions (including `source_refs` where set) and recent **quiz attempt scores** (pass/fail and percentage — per-question right/wrong is **not** stored yet; the tutor is told that in context).

- **Gemini** (`GOOGLE_API_KEY`, `GOOGLE_MODEL_NAME`) powers tutor **reasoning and text** replies. If the key is missing, the API returns a clear configuration error and typed chat does not call the model.
- **ElevenLabs** (`ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL`) is used **only** for optional **spoken** playback of the assistant reply (`audio/mpeg` as base64 in the JSON response). It is never used for reasoning. If ElevenLabs is not configured, chat still works; warnings may list missing voice/key.
- **API keys never go to the browser**; all Gemini and ElevenLabs calls are server-side.

See `.env.example` for variable names. After enabling the tutor DB tables:

```bash
python3 manage.py migrate
```

After pulling changes that touch `courses.models.TrainingVideo`, always run:

```bash
python manage.py makemigrations   # if you changed models locally
python manage.py migrate
python manage.py check_trainingvideo_schema
```

If you see `OperationalError: no such column ... thumbnail_url`, the database is behind the models — `migrate` (and migration `0003_repair_trainingvideo_columns` if history is inconsistent) brings SQLite in sync **without** deleting `db.sqlite3`.

### Demo logins (from `seed_demo`)

| Role    | Username   | Password     |
|---------|------------|--------------|
| Teacher | `teacher`  | `teacher123` |
| Student | `student1` | `student123` |
| Student | `student2` | `student123` |

Django admin: http://127.0.0.1:8000/admin/ — create a superuser with `python3 manage.py createsuperuser` if you need full admin access.

## Teacher admin panel (`/admin-panel/`)

- **Courses:** lists **all** courses with **owner** (`created_by`), optional **course icon** thumbnail, **Edit** / **Delete** for courses you manage (staff see all); **View** for others. Public **Courses** page shows every course; this panel explains why a course may appear publicly but not be “yours” to edit.
- **Student progress:** recent quiz attempts on **your** courses (staff see all); each row can be **deleted** (POST) unless a **claimed** Solana badge blocks deletion.
- **Course editor** (`/admin-panel/manage/course/<id>/`): metadata, **course icon picker**, videos, quizzes, resources, reading generation, etc.

### Management commands (accounts app)

Useful for cleanup and debugging:

```bash
# List courses with id, title, owner, video/quiz/attempt counts
python manage.py list_courses_debug

# Dry-run (default): show quiz attempts that would be removed
python manage.py cleanup_demo_attempts --users a,b --quizzes T

# Actually delete matching attempts (+ unclaimed skill badges for those attempts)
python manage.py cleanup_demo_attempts --users a,b --quizzes T --confirm

# Delete one course by id (requires --confirm)
python manage.py delete_course <course_id> --confirm
```

## Course icons

- `Course.icon_name` stores a slug (e.g. `diagnostics`, `fuse`); static SVGs live under `static/images/course-icons/`.
- **`Course.icon_static_path`** resolves to a path under `static/`; invalid/blank values fall back to **`default.svg`**.
- Teachers pick an icon on **Edit course** (and **Add course**); **Courses** cards and **course detail** show the icon.

## Project layout

- `carhoot/` — Django project package: **settings** and root **URLconf** (historical package name; product is **MotorMind**)
- `accounts/` — login/logout, role-aware **dashboard**, **teacher admin panel** (courses, resources, quiz-attempt removal, nested course editor), `Profile` (teacher/student)
- `courses/` — `Course` (incl. `icon_name`), `TrainingVideo`, `VideoSection`, landing, course list/detail
- `tutor/` — AI tutor conversations/messages; course context + Gemini + optional ElevenLabs TTS
- `quizzes/` — quiz models, take quiz / results / leaderboard
- `ar_tasks/` — models + **REST API** only (no web task UI in this branch)
- `resources/` — **Resource library**, ingestion jobs, retrieval logs, Chroma vector services
- `study_content/` — course reading pages / generation hooks from the admin course UI
- `api/` — DRF serializers and endpoints for courses, videos, sections, quizzes, resources, AR (API), etc.
- `templates/` — Bootstrap 5 base layout and page templates
- `solana_badges/` — optional **Solana Devnet** “Proof of Skill” memo transactions after passing a quiz (not NFTs)

## Solana Devnet setup (optional skill badges)

Badges record a short **on-chain memo** on **Devnet** only (issuer wallet pays fees). **No Solana API key** is required for the public Devnet RPC. Public RPCs and faucets can be **rate-limited**; if airdrops fail, retry later or use another Devnet faucet.

**Do not** use mainnet or real-money wallets for this prototype. Keep issuer keys out of git (`.env` and `devnet-issuer.json` are gitignored).

### Configure the issuer

1. (Optional) Install the [Solana CLI](https://docs.solana.com/cli/install-solana-cli-tools) and create a **Devnet** keypair, or generate a keypair in code and export the **64-byte secret** as a JSON array.
2. Add to `.env` (copy from `.env.example`):
   - `SOLANA_RPC_URL=https://api.devnet.solana.com` (default if omitted)
   - `SOLANA_NETWORK=devnet`
   - `SOLANA_ISSUER_PRIVATE_KEY=[...]` — JSON array of **32** (seed) or **64** (full secret) byte values. **Never commit** this value.
3. **Fund the issuer’s public address** with Devnet SOL (required before claims succeed):
   - Web: [Solana Devnet faucet](https://faucet.solana.com/)
   - CLI: `solana airdrop 1 <ISSUER_PUBKEY> --url devnet` (when the faucet allows it)

### Check readiness

```bash
python manage.py migrate
python manage.py check_solana_badges
```

You should see the **issuer public key**, **balance in SOL** and either **READY** or **NOT READY** (with the address to fund). The command **never prints** the private key.

### Test memo transaction

After `check_solana_badges` reports **READY**:

```bash
python manage.py send_test_solana_badge --wallet <any_devnet_pubkey_for_your_notes>
```

This sends a small **test memo** on Devnet and prints the **signature** and **Solana Explorer** link. If the issuer has **no SOL**, the command exits with a clear message and does **not** send.

### In the app

- After a **passed** quiz, students see **Claim Solana Devnet badge** on the result page.
- If the issuer is **unfunded**, the UI explains that the **project issuer** needs Devnet SOL and links the faucet (no private keys shown).
- **Teachers / staff** see a **Solana Devnet status** panel on the quiz result page and on **Profile** (`/profile/`).

## URLs (web)

| Path | Description |
|------|-------------|
| `/` | Landing |
| `/login/`, `/logout/` | Auth |
| `/dashboard/` | Role-aware dashboard |
| `/courses/` | Course cards (icons + descriptions) |
| `/courses/<id>/` | Course detail (videos, quizzes, **Talk to tutor**; no AR web UI) |
| `/courses/<id>/tutor/message/` | POST JSON — AI tutor chat (session auth + CSRF) |
| `/courses/<id>/tutor/speech/` | POST JSON — ElevenLabs TTS only (replay / extras) |
| `/courses/<id>/videos/<video_id>/` | Video + sections; use `?t=90` to start near 90s (YouTube embed) |
| `/admin-panel/` | Teacher/staff **admin panel** (all courses + owner, resources, student quiz attempts) |
| `/admin-panel/manage/course/<id>/` | Course hub (icon, metadata, videos, quizzes, reading, resources) |
| `/admin-panel/progress/quiz-attempt/<id>/delete/` | POST — teacher/staff delete quiz attempt (blocked if Solana badge **claimed**) |
| `/admin-panel/resources/` | **Teacher-only** resource dashboard (upload + table) |
| `/admin-panel/resources/test/` | **Teacher-only** retrieval test UI |
| `/admin-panel/videos/youtube-autofill/` | **Teacher-only** POST JSON — oEmbed + captions for the video form |
| `/admin-panel/videos/ai-description/` | **Teacher-only** POST JSON — optional Gemini/Gemma description |
| `/profile/` | User profile (wallet, badges, quiz progress); teachers see Solana Devnet diagnostics |
| `/leaderboard/` | Off-chain site leaderboard (badges / quiz stats) |
| `/badges/claim/quiz-attempt/<id>/` | POST — claim Devnet memo badge for a passed attempt |

## Resource library / vector database

### Book upload workflow (ISBN PDFs)

1. **Rename** the PDF to its ISBN (hyphens/spaces allowed), for example `9780415725774.pdf` or `978-0-415-72577-4.pdf`.
2. Open **Resource Library** (`/admin-panel/resources/`) and upload the file.
3. Optionally select **one or more courses** (checkboxes).
4. Leave **Resource type** on **Auto** for PDFs (defaults to **book**) or pick a type explicitly.
5. MotorMind **validates ISBN-10 / ISBN-13 checksums**, then tries **Open Library** and **Google Books** to auto-fill title/author/publisher/year/description when possible.
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
- MotorMind calls **Open Library** first (`GET https://openlibrary.org/isbn/{ISBN}.json`, 10s timeout). Many editions list authors only on the linked **work** record; the app follows `/works/...` and `/authors/...` links to resolve names.
- If Open Library is missing useful fields, **Google Books** is used as **fallback and enrichment** (`GET https://www.googleapis.com/books/v1/volumes?q=isbn:{ISBN}`).
- Lookup can **fail** if the ISBN is unknown, an API error occurs, or the server has **no outbound internet** — the `Resource` is still created, `title` falls back to the ISBN, `metadata_lookup_status` is set to **failed** and **ingestion / ChromaDB** still runs.
- Teachers can **retry** lookup from the resource detail page (**Retry metadata lookup**) or run:
  - `python3 manage.py lookup_isbn 9780080969459` — prints normalized JSON and `metadata_source`
  - `python3 manage.py lookup_resource_metadata <resource_id>` — updates the row and prints before/after title, author, publisher, year
- Teachers can **manually edit** metadata (including ISBN) on the edit form if lookup is incomplete.

### What is stored where

- **SQLite** stores only **high-level metadata** (`Resource`), **ingestion jobs** (`ResourceIngestionJob`), **retrieval logs** (`ResourceRetrievalLog`) and the **ManyToMany** link between `Resource` and `Course`.
- **ChromaDB** (on disk under `vector_db/`) stores **one vector per text chunk**, including the **full chunk text** as the Chroma **document**, embeddings and rich **metadata** (resource id/title/type, course ids/titles, page number, chunk index, char offsets, etc.).
- `Resource.chunk_count` is a **UI counter** mirrored from ingestion; there is **no** `ResourceChunk` table and **no** per-chunk SQLite rows.

### Many-to-many courses

`Resource.courses` is a **ManyToManyField** to `courses.Course` (no `ForeignKey` from `Resource` → `Course`). A resource can belong to **zero, one, or many** courses and a course can have many resources.

When course associations change, MotorMind **updates Chroma metadata only** (`course_ids_csv`, `course_titles_csv`, JSON mirrors) on existing chunk vectors — **no** full re-extraction, re-chunking, or re-embedding. Use **Re-ingest** on the resource detail page when you actually need to rebuild vectors from the file.

### Embeddings (local)

The project tries **`sentence-transformers`** first, but many developer machines have broken global TensorFlow/Keras stacks that can break `import sentence_transformers`. In that case MotorMind **falls back** to Chroma’s bundled **ONNX MiniLM** embedding function (still `all-MiniLM-L6-v2`-class, 384-dim).

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

### Management commands (resources / courses)

- `python3 manage.py seed_demo` — demo users/content + optional demo text resource ingest (skips vector ingest if dependencies fail).
- `python3 manage.py ingest_resource <resource_id>` — run ingestion synchronously.
- `python3 manage.py lookup_resource_metadata <resource_id>` — re-fetch book metadata using `Resource.isbn`.
- `python3 manage.py clear_vector_db` — drop/recreate the Chroma collection.
- `python3 manage.py test_vector_search "your query"` — quick CLI vector search.
- See **Teacher admin panel** above for `list_courses_debug`, `cleanup_demo_attempts` and `delete_course`.

## JSON API (authenticated)

All routes are under **`/api/`** and require authentication (session or basic auth in development).

### Course / content endpoints

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/courses/` | Course list (`icon_name`, `icon_static_path` included) |
| GET | `/api/courses/<id>/` | Course detail (nested videos w/ sections, quizzes; `ar_tasks` in JSON for clients that use it) |
| GET | `/api/courses/<id>/videos/` | Videos for a course |
| GET | `/api/videos/<id>/sections/` | Sections for a video |
| GET | `/api/courses/<id>/quizzes/` | Quizzes for a course |
| GET | `/api/quizzes/<id>/` | Quiz + nested questions + choices |

### AR task endpoints (API only)

| Method | Path | Notes |
|--------|------|--------|
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
| DELETE | `/api/resources/<id>/` | Deletes SQLite row, uploaded file and Chroma vectors |
| POST | `/api/resources/search/` | Semantic search JSON body `{ "query": "...", "top_k": 5, "course_id": 1, "resource_type": "notes", "resource_id": 2 }` (filters optional except `query`) |

Example (teacher basic auth):

```bash
curl -u teacher:teacher123 -X POST http://127.0.0.1:8000/api/resources/search/ \
  -H "Content-Type: application/json" \
  -d '{"query":"how do you test a car fuse?","top_k":3,"course_id":1}'
```

Example (student AR progress via API):

```bash
curl -u student1:student123 -X POST http://127.0.0.1:8000/api/ar-tasks/1/progress/ \
  -H "Content-Type: application/json" \
  -d '{"status":"completed","notes":"Simulated fault isolated"}'
```

## Notes

- **Large PDF uploads**: there is no app-enforced file size cap. Django’s `DATA_UPLOAD_MAX_MEMORY_NUMBER` is raised (default **200 MB** request body; override with `DATA_UPLOAD_MAX_MEMORY_MB` in `.env`). Very large books produce more Chunks → longer CPU time during synchronous ingest.
- **SQLite** is used for development (`db.sqlite3`).
- **Bootstrap 5** is loaded from a CDN in `templates/base.html`.
- **Public course list** uses a flex card layout (clamped descriptions; **Open** anchored at the bottom of each card).
- Uploaded files are stored under `MEDIA_ROOT/resources/` (served in `DEBUG` mode from `/media/`).
