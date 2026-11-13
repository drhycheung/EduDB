# EduDB

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

## Run locally

1. `docker compose up -d` (starts PostgreSQL)
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and set a random `SECRET_KEY`
5. `python3 seed.py`
6. `flask run`, then open http://localhost:5000

Sign in as `Teacher` / `teacher123` (sees all rows) or `Learner 1` to `Learner 6` / `learner123`.

## Data

Every record is synthetic. The relational schema shape follows the INT4177 Big Data Analytics
course materials, used as a reference corpus only. No real student data is used. See `LICENCE` for
the data attribution block.

## Deployment note

This repository holds a local application and a labelled static preview. A real deployment would add
a production server, a secret store, a reverse proxy and a persistent database. That is documented in
`EduDB-planning.md` and is not part of the course. Supabase and Firebase host databases in L04; they
do not run this Flask application.

## Licence

MIT. See `LICENCE`.
