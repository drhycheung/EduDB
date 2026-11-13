# EduDB

**Live demo (static preview):** https://drhycheung.github.io/EduDB/

**Static preview (not the application).** A rendered copy of the screens is published with
GitHub Pages. It shows fixed examples and connects to no database. The working application runs on
your own computer with Docker. See "Run locally" below.

EduDB is the demonstration learning analytics application for INT4087 Web Database Applications for
Data Analytics (EdUHK, 2026-27 Semester 2). It stores weekly quiz attempts and reports class
weaknesses, learner progress, retrieval over teaching material, and a chart. The code is small
enough to read line by line in class.

## Features

- F1–F2 Dashboard: correct-answer rate by question and by topic
- F3 Progress: quiz 1 and quiz 2 rate per learner
- F4 My attempts: a learner sees own rows; a teacher sees all rows
- F5 Sign-in and roles: two accounts, one password hash check, in-memory sessions
- F6 Search: keyword and vector (semantic) retrieval over teaching-material excerpts
- F7 Documents: create, read, update, delete on question documents
- F8 Chart: an interactive bar chart drawn on the server (no JavaScript)
- F9 Parquet check: the same rate read from a Parquet file with DuckDB

## Project structure

The repository is small so that every file can be read in class. The tree below shows each file
and its job.

```
EduDB/
├── app.py                  # Flask application: one function per route, plain SQL, sessions
├── schema.sql              # CREATE TABLE statements for PostgreSQL
├── seed.py                 # Reads data/*.csv and loads PostgreSQL; also writes attempts.parquet
├── requirements.txt        # Python packages: Flask, psycopg, duckdb, python-dotenv
├── .env.example            # Template for DB_* settings and SECRET_KEY
├── docker-compose.yml      # Starts the PostgreSQL container
├── data/                   # Synthetic source data (CSV and JSON)
│   ├── Student.csv         # 6 learners
│   ├── Course.csv          # 1 course
│   ├── Enrolment.csv       # learner-to-course links
│   ├── Topic.csv           # 3 topics
│   ├── Quiz.csv            # 2 quizzes (one per topic pair)
│   ├── Question.csv        # 6 questions
│   ├── Attempt.csv         # 36 attempts (one empty value means the learner skipped)
│   ├── excerpts.csv        # 5 teaching excerpts, each with an 8-dimension vector
│   └── documents.json      # question documents used by the Documents feature
├── templates/              # Server-rendered HTML pages (no JavaScript)
│   ├── base.html           # Shared layout: header and navigation
│   ├── dashboard.html      # F1-F2: rate by question and by topic
│   ├── progress.html       # F3: progress for each learner
│   ├── student.html        # F4: one learner's own attempts
│   ├── login.html          # F5: sign-in form
│   ├── search.html         # F6: keyword and vector search
│   ├── documents.html      # F7: create, read, update, delete documents
│   ├── chart.html          # F8: bar chart drawn on the server
│   └── parquet.html        # F9: rate read from a Parquet file
├── queries.sql             # L05: a wrong join and the corrected version
├── ai-log.md               # Example of an AI-assisted query log
├── docs/                  # Static preview (a mockup, not the running application)
│   ├── index.html          # Preview home: Dashboard (the page GitHub Pages serves)
│   ├── progress.html       # Progress by learner
│   ├── myattempts.html     # One learner's attempts
│   ├── search.html         # Keyword and vector search, with example results shown
│   ├── documents.html      # Question documents
│   ├── chart.html          # Server-drawn bar chart by topic
│   ├── parquet.html        # Rate read from a Parquet file
│   └── login.html          # Sign-in screen
├── LICENCE                 # MIT licence with a data attribution block
└── README.md               # This file
```

### How the real application works

A database web application has three layers: storage, logic and presentation. EduDB follows this
shape.

1. **Storage.** `docker-compose.yml` starts PostgreSQL. `schema.sql` defines the tables. The
   `data/*.csv` files hold the rows. `seed.py` copies those rows into PostgreSQL and also writes
   `attempts.parquet` for feature F9.
2. **Logic.** `app.py` is a Flask program. Each route opens a connection with the `DATABASE_URL`
   from `.env`, runs a `SELECT` statement, and passes the rows to a template. The password check
   uses one hash; the session stores the signed-in user only.
3. **Presentation.** The files in `templates/` build the page on the server. The browser receives
   plain HTML. No JavaScript runs, so every value comes from one SQL query.

Read the files in this order: `schema.sql`, then `data/*.csv`, then `seed.py`, then `app.py`, then
the templates. This order follows the data from the table definition to the screen.

## Run locally

These steps assume you have Python 3.11+, Docker, and Git installed.

1. **Get the code.** Clone the repository, then enter the folder:
   ```
   git clone https://github.com/drhycheung/EduDB.git
   cd EduDB
   ```
   If you already have the folder, open a terminal inside it.

2. **Create and activate a virtual environment** so the packages do not affect your system:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
   Your shell prompt should now show `(.venv)`. Every command below must run
   with this virtual environment active. On Windows use `.venv\Scripts\activate`.

3. **Install the Python packages** listed in requirements.txt:
   ```
   pip install -r requirements.txt
   ```
   This installs Flask, psycopg, duckdb and python-dotenv.

4. **Create your settings file** by copying the template:
   ```
   cp .env.example .env
   ```
   The new `.env` is private and is never committed. It already contains a
   working `SECRET_KEY` for local use, so you do not need to edit it. See the
   Deployment note for how to set a strong key before any real deployment.

5. **Start PostgreSQL** in the background:
   ```
   docker compose up -d
   ```
   Wait a few seconds for the database to finish starting.

6. **Load the sample data** into PostgreSQL:
   ```
   python3 seed.py
   ```
   Re-running this command resets the database to the sample data, so it is safe to run again.

7. **Run the application.** Keep the virtual environment active: your shell
   prompt should show `(.venv)`. Then:
   ```
   flask run
   ```
   If `(.venv)` is not shown, the command would use your system Python
   (for example Anaconda) and fail with `ModuleNotFoundError`. Activate first
   with `source .venv/bin/activate`, or run the app directly with
   `.venv/bin/flask run`. Then open http://localhost:5000 in your browser.

Sign in as `Teacher` / `teacher123` (sees all rows) or `Learner 1` to `Learner 6` / `learner123`.

### All commands in one block

Copy and paste the block below in order (macOS / Linux). It performs every step above.
The `.env` created by `cp .env.example .env` already has a working `SECRET_KEY`,
so no extra editing is needed. On Windows, replace `source .venv/bin/activate`
with `.venv\Scripts\activate`.

```bash
git clone https://github.com/drhycheung/EduDB.git
cd EduDB
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d
python3 seed.py
flask run
```

## Troubleshooting

- **Port 5000 already in use (macOS).** On macOS the AirPlay Receiver often
  holds port 5000, so `flask run` may fail to start, or the browser may show a
  `403` from a service other than EduDB. Turn off AirPlay Receiver (System
  Settings > General > AirDrop & Handoff > AirPlay Receiver), or run on another
  port and open that address instead:
  ```bash
  flask run --port 5055
  ```
  Then open http://localhost:5055 .
- **`ModuleNotFoundError: No module named 'duckdb'` (or `psycopg`).** The command
  ran with your system Python instead of the virtual environment. Make sure the
  prompt shows `(.venv)`; if not, run `source .venv/bin/activate` first, or use
  `.venv/bin/flask run`.
- **"Wrong username or password" for every account.** Run `python3 seed.py`
  again so the accounts are loaded, then restart `flask run`.

## Data

Every record is synthetic. The relational schema shape follows the INT4177 Big Data Analytics
course materials, used as a reference corpus only. No real student data is used. See `LICENCE` for
the data attribution block.

## Deployment note

This repository holds a local application and a labelled static preview. A real deployment would add
a production server, a secret store, a reverse proxy and a persistent database. That is documented in
`EduDB-planning.md` and is not part of the course. Supabase and Firebase host databases in L04; they
do not run this Flask application.

**Secret key for real deployment.** The `.env` file already contains a default `SECRET_KEY` that is
safe for local teaching only. Before any public or shared deployment, replace it with a strong random
value and keep that value private:

```
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy the printed string into `.env` as `SECRET_KEY=...`. Anyone who learns this value could forge
sessions, so never reuse the sample value and never commit the real key.

## Licence

MIT. See `LICENCE`.
