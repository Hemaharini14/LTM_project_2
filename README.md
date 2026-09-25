# EduBridge

**AI-powered higher education discovery platform using RAG.**

Students lose hours across a dozen sites comparing universities on rankings,
fees, accommodation, living costs and entry requirements. EduBridge puts those
in one place, matches universities to a student's own preferences, and answers
questions in natural language — grounded in real data rather than generated
from the model's memory.

---

## What it does

| | |
|---|---|
| **Résumé intake** | Upload a PDF; an LLM extracts field of study, country, budget, degree and skills for you to confirm |
| **Preference matching** | Country, field, budget, skills and certifications, with a match score per university |
| **University profiles** | Fees, accommodation, entry requirements, graduate outcomes, scholarships, fields offered |
| **Cross-border comparison** | Any two universities side by side, including IIT Bombay against MIT |
| **3D globe explorer** | 840 real universities plotted at real coordinates, with country outlines |
| **Ask EduBridge** | RAG chat over ~9,000 university documents |
| **Entrance exams** | IELTS, TOEFL, PTE, GRE, GMAT, SAT, ACT and aptitude, linked to lessons |
| **Accounts** | Signup/login with bcrypt-hashed passwords, per-user history, admin dashboard |

---

## The data, and what it does not cover

Every figure shown comes from a real source. Where a source has nothing, the
interface says so rather than filling the gap.

| Region | Source | Covers |
|---|---|---|
| **United States** | [College Scorecard](https://collegescorecard.ed.gov/data/) (US Dept. of Education) | 6,273 institutions — tuition, room & board, admission rate, SAT/ACT, median earnings, net price by family income |
| **International** | Community "Cost of International Education" dataset | 622 universities across 71 countries — tuition, rent, visa fee, insurance |
| **India** | [JoSAA](https://josaa.admissions.nic.in/) seat allocation | 114 institutes (23 IIT, 31 NIT, 29 IIIT, 31 GFTI) — 9,178 branch-level closing ranks |
| **Rankings** | Times Higher Education + QS | 1,985 ranked universities |
| **Geography** | Natural Earth (public domain) | Country outlines, 50,250 city coordinates |

### Deliberate limitations

These are design decisions, not oversights:

- **Acceptance rates only exist for the US.** Elsewhere universities publish
  entry requirements instead — UCAS tariff points, ATAR cutoffs, JEE closing
  ranks, Singapore's Indicative Grade Profile. The app explains each country's
  own system rather than inventing a percentage.
- **US financial aid is for US citizens.** Pell Grants and federal loans are
  not open to international students, and every aid figure says so.
- **LinkedIn is deep-linked, never scraped.** Scraping it breaks their terms
  and means collecting real people's personal data. The app opens LinkedIn's
  own alumni search instead.
- **Missing values read as "Not reported."** Where a cost can be reasonably
  inferred, a peer-median estimate is shown with an `est.` badge and the basis
  it came from. Selectivity and outcomes are never estimated.
- **International tuition is indicative.** That dataset is community-maintained,
  not governmental, and the interface labels it as such.
- **Indian cutoffs are 2021 figures** and shift each year.

---

## Setup

Requires **Python 3.13** and about 1GB of disk for datasets and the vector store.

```bash
pip install -r Requirements.txt
```

### 1. Datasets

Two large files are not in the repository. Download from
[collegescorecard.ed.gov/data](https://collegescorecard.ed.gov/data/) into `dataset/`:

- `Most-Recent-Cohorts-Institution.csv`
- `Most-Recent-Cohorts-Field-of-Study.csv`

The other datasets are already committed.

### 2. Configuration

Copy `.env.example` to `.env` and fill in:

```ini
OPENROUTER_API_KEY=     # https://openrouter.ai/keys — free models only
SESSION_SECRET=         # python -c "import secrets; print(secrets.token_urlsafe(48))"
REDDIT_CLIENT_ID=       # optional, enables live student reviews
REDDIT_CLIENT_SECRET=
```

### 3. Build the database and search indexes

```bash
python -m src.database_setup   # ~3 min: builds edubridge.db
python -m src.vector_store     # embeds 421 field-of-study names
python -m src.rag              # ~8 min: embeds ~9,000 university documents
```

### 4. Run

```bash
uvicorn api.main:app --reload
```

Open **http://127.0.0.1:8000**. Windows users can double-click `start.bat`.

> Keep the terminal open — the site only works while the server runs. Run only
> one server at a time; two processes writing to the same SQLite file is the
> usual cause of locking errors.

---

## Architecture

```
api/main.py          FastAPI: auth, recommendations, RAG chat, globe, admin
src/
  database_setup.py  Builds edubridge.db from the CSVs (run once)
  db.py              SQLite connections (WAL mode, busy timeout)
  auth.py            bcrypt passwords, signed session cookies, history
  set_password.py    Sets a password from the server (there is no reset page)
  recommender.py     US / international / India matching and comparison
  matching.py        Match scoring across five measurable dimensions
  vector_store.py    ChromaDB index of field-of-study names
  rag.py             University document corpus, retrieval and answering
  query_router.py    Sends ranking and lookup questions to SQL, not similarity
  evaluation.py      Scores retrieval against SQL-derived correct answers
  llm_extractor.py   Résumé and free-text preference extraction
  resume_parser.py   PDF text extraction
  news.py            Education headlines from RSS
  reviews.py         Reddit API, LinkedIn deep links
frontend/            Multi-page HTML/CSS/JS, no build step
  index.html         3D landing (Three.js, GSAP, Lenis)
  classic.html       Original book-opening landing
  login.html         Sign in and create account
  js/scene.js        Hero scene
  js/globe.js        Interactive globe with country borders
  vendor/            Three.js, GSAP, Lenis — vendored, no CDN needed
```

### How matching works

The student's own wording is embedded and compared against real CIP field
names, so "Artificial Intelligence" reaches Computer Science and Data Science
programmes even though no CIP field carries that name. Substring matching
could not do this — it returned nothing for "Artificial Intelligence" and
matched "AI" inside "maintenance".

Each result is then scored on five dimensions, all computed:

- **Course match** — semantic distance to the programmes that university offers
- **Budget fit** — where its tuition sits against the stated range
- **Country match** — whether it is in the requested country
- **Graduate earnings** — percentile among the student's results
- **Cost after aid** — net-price percentile among the student's results

Research strength and campus lifestyle are **not** scored, because no dataset
here measures them.

### How RAG works

`src/rag.py` turns each university into a plain-language document — costs,
housing, admissions, outcomes, scholarships, programmes — embeds ~9,000 of
them with Sentence Transformers into ChromaDB, retrieves the closest eight for
a question, and passes them to a free OpenRouter model as grounding context.
The system prompt forbids inventing a fee, ranking, test score or salary.

### Retrieval evaluation

`python -m src.evaluation` scores retrieval against 62 questions whose
correct answer is computed from SQL beforehand, so nothing depends on
judging prose. **Hit rate** is whether the right university appears in the
retrieved context at all; **MRR** is where it ranked, with 1.00 meaning
always first.

| Question type | Vector only | Hybrid |
|---|---|---|
| Superlative ("best scholarships") | **0%** | **100%** |
| Acronym lookup ("tell me about MIT") | 50% | **100%** |
| Named lookup | 100% (MRR 0.90) | 100% (MRR **1.00**) |
| Descriptive | 20% | 20% |
| **Overall** | **73%** (MRR 0.62) | **87%** (MRR 0.84) |

Superlatives failed completely under pure similarity search, because
ranking by a number is not a similarity problem. Acronyms failed half the
time, because "MIT" embeds nowhere near "Massachusetts Institute of
Technology".

Descriptive questions are unchanged at 20%, since both paths handle them
the same way — that is the clearest target for future work, as location
filters ("a selective university in Boston") are also partly structured.

### Tests

```bash
pytest tests/ -q
```

55 tests — 21 on query routing, 13 on match scoring, 21 on accounts,
passwords, sessions and country normalisation. They run in about 35 seconds
and need no network or API key; account tests use a temporary database
rather than the real one.

Two cover bugs that reached committed code and were found by the retrieval
evaluation, and each is verified to fail if the bug returns:

- **"cheapest on-campus housing" ranked by tuition** — the generic
  "cheapest" pattern matched before the housing one. Found by the retrieval
  evaluation, after it had already been committed.
- **"highest graduate earnings" fell through to similarity search** and
  answered with a UK university. Same origin.

---

## Tech stack

Python 3.13 · FastAPI · SQLite (WAL) · ChromaDB · Sentence Transformers
(`all-MiniLM-L6-v2`) · OpenRouter (free models with automatic fallback) ·
Three.js · GSAP · Lenis · vanilla HTML/CSS/JS

---

## Troubleshooting

**"This site can't be reached"** — the server isn't running. Start it and keep
the window open. Check the port is `8000` and the URL is `http://`, not `https`.

**"database is locked"** — more than one server is running. Stop the extras.

**Forgotten password** — there is no reset page, because this project has no
way to send email. Set a new password from the machine running the server:

```bash
python -m src.set_password your@email.com
```

**Model downloads fail behind a corporate proxy** — the embedding model is
fetched from Hugging Face via `requests`, which uses `certifi` rather than the
Windows certificate store. `truststore` is installed for this and injected in
`src/vector_store.py`; `HF_HUB_DISABLE_XET=1` also helps if transfers stall.

**Rate-limited by OpenRouter** — free model endpoints share an upstream pool.
`src/llm_extractor.py` falls through a list of them automatically.
