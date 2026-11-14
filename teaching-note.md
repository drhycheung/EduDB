# EduDB — Teaching note: why the demo is designed this way

This note explains the design choices behind the EduDB demonstration application.
It is written for the teacher and for students who want to understand the *why*,
not only the *how*. The course is **INT4087 — Web Database Applications for Data
Analytics** (EdUHK). To run the application, see [README.md](README.md).

---

## 1. The one rule that shapes everything

Every line of code in this demo must be explainable in one lesson. This single
rule decides most of the design.

Consequences:

- The whole application is **one Python file** (`app.py`) with eight short HTML
  page templates that share one base layout. A student can print the file and
  read it in class.
- There is **no JavaScript**. Every number on the screen comes from one SQL
  query that the teacher can read.
- There is **no object-relational mapper**. SQL stays visible as plain text
  inside the Python code, so students see the exact query that produced each
  table.
- The demo runs **two local database containers** (PostgreSQL and MongoDB), and
  it makes **no call to the public internet at runtime** — it only talks to those
  local containers and reads a local file. It works offline once the Docker
  images are downloaded.
- All data is **synthetic**. No real student name or student number appears
  anywhere. This is a data-preparation rule, not an accident.

The point is not to show a clever application. The point is to give students a
small, complete object that they can trace from the database to the screen.

---

## 2. Why two databases: a SQL database and a NoSQL database

This is the question students ask most. The short answer: the demo stores two
*kinds* of data, and each kind fits a different model. Using both databases shows
a real pattern called **polyglot persistence** — choosing the right storage for
each piece of data.

### 2.1 PostgreSQL holds the facts (relational)

PostgreSQL is a relational database. It stores data in tables with fixed columns
and keys. EduDB uses it for the seven analytics tables:

- `Student`, `Course`, `Enrolment`
- `Topic`, `Quiz`, `Question`
- `Attempt` (one row per answer)

These tables need **exact aggregation**. The teacher wants a correct-answer rate
such as "66.7%". That rate comes from a `GROUP BY` query and a `COUNT`. Relational
databases are strong at this. They also support **joins** (link a question to its
topic), **normalisation** (store each fact once), and a **fixed schema** that
everyone agrees on.

This part of the demo serves several lessons:

- **L02–L03** — data modelling and normalisation (the entity-relationship
  diagram and the schema).
- **L04** — introduction to SQL (`CREATE TABLE`, load CSV, first `GROUP BY`).
- **L05** — advanced SQL (common table expressions, window functions, a
  corrected join).

One small teaching detail lives here: `Attempt.is_correct` is `NULL` for one
skipped question. The plain meaning is "the learner did not answer", which is not
the same as "wrong". The correct-answer rate therefore divides by
`COUNT(is_correct)`, not by `COUNT(*)`. This one `NULL` supports a short lesson
on counting and on what `NULL` means.

### 2.2 MongoDB holds the teacher remarks (document)

MongoDB is a document database. It stores each record as a **document**, and
documents in one collection may have different fields. EduDB uses it for the
**teacher remarks**: one document per learner, holding the teacher's free-text
comment on that learner's performance.

This part serves **L06 — NoSQL databases and vector data**. In that lesson
students:

- store data as MongoDB documents,
- run the four basic operations (create, read, update, delete) on those
  documents,
- and compare the document model with the relational model from L02.

The same MongoDB service does double duty. It powers the live **F7** feature
(teacher adds and edits one remark per learner; the learner reads only their own
remark), and it is the concrete object for the L06 NoSQL lesson. One small
collection and four operations make the document-store idea real.

A useful boundary to state in class: the keyword and vector search (F6) does
**not** use MongoDB. It reads a plain CSV of teaching-note excerpts and computes
cosine similarity in Python, so it needs no database at all. MongoDB is used only
for the teacher remarks (F7).

### 2.3 Why keep both, instead of one database?

Three reasons, all relevant to the course.

1. **It matches real systems.** A production learning-analytics system rarely
   uses one database only. It often keeps measured facts (attempts, scores) in a
   relational warehouse for clean reporting, and keeps flexible records (notes,
   feedback, free text) in a document store. Students see the trade-off, not just
   one tool.
2. **It makes the L06 choice concrete.** L06 asks students to *compare* the
   relational model with a semi-structured document model. The demo lets them see
   both running side by side, on the same application and the same synthetic
   dataset.
3. **It keeps the NoSQL component even after simplification.** Earlier versions
   of the demo carried a heavier "question bank" feature. Removing it could have
   dropped NoSQL entirely. Instead, the remarks feature was kept on MongoDB, so
   the demo still teaches NoSQL while staying small and readable.

The design rule from section 1 still holds: the MongoDB code is a few short
functions, the documents are seeded from one JSON file, and the operations are
the four basics — nothing hidden.

---

## 3. Why Docker, DuckDB, and Parquet are used

This section explains the three supporting technologies and why each earns a
place in the demo. The short theme is the same as section 2: choose the right
tool for the job.

### 3.1 Docker: one command runs two real databases

`docker compose up -d` starts two database servers — PostgreSQL 16 and MongoDB 7
— each in its own container, each with a named volume for storage.

Reasons it is used:

- **Identical environment for every student.** macOS, Windows, and Linux all run
  the same PostgreSQL 16 and MongoDB 7. This removes the "works on my machine"
  problem that appears when students install database servers by hand.
- **No system-level install.** A database server normally needs services, ports,
  and data directories. Docker bundles them; the only prerequisite is Docker
  Desktop. It also avoids clashing with any database already installed.
- **Clean, repeatable teardown.** `docker compose down` stops both servers;
  `docker compose down -v` wipes the data for a clean reset, and re-running
  `seed.py` returns the demo to a known state.
- **It makes polyglot persistence real.** Running a relational engine and a
  document engine side by side, from one compose file, mirrors a production
  multi-database stack and supports the L06 NoSQL lesson.

Trade-off: Docker adds one prerequisite — Docker Desktop must be installed *and
running*. The README states this explicitly, because a stopped Docker daemon is
the most common student failure. A simpler single-file demo could avoid servers
altogether, but then the real-client lessons (connection strings, ports,
`psycopg`) and the relational-versus-document contrast would be lost.

### 3.2 DuckDB: an in-process analytical engine

DuckDB is a columnar SQL engine that runs *inside the Python process*. There is
no server, no host, no port, and no password. In this demo it appears in two
places: `seed.py` writes the Parquet file, and feature F9 reads it with
`duckdb.connect()`.

Reasons it is used:

- **It contrasts analytical engines.** The same question — "what is the overall
  correct-answer rate?" — is answered by PostgreSQL over a live connection (F1)
  and by DuckDB over a file (F9). Both return the same number, but the paths and
  trade-offs differ.
- **It shows SQL is portable.** The same SQL dialect works across PostgreSQL,
  DuckDB, and (with small differences) SQLite. Students see that SQL is a skill,
  not a single product.
- **It is lightweight.** DuckDB needs no container. A third storage engine is
  demonstrated without adding a third service.
- **It serves the analytics half of the course title.** L09 (Analytics and
  visualisation) uses the DuckDB check as the "read from a columnar file" step.

### 3.3 Parquet: the columnar file format

Parquet is a columnar file format. `seed.py` exports the attempt data to
`data/attempts.parquet` using a DuckDB `COPY` statement. Feature F9 then reads
that file.

Reasons it is used:

- **Columnar storage reads less data.** A query that touches few columns reads
  only those column blocks, not whole rows. With many rows this is a large saving
  in disk input and time.
- **Better compression.** Values in one column are the same type and often
  similar, so they compress well. Smaller files read faster.
- **It is the industry-standard analytics format.** Data lakes and warehouses
  (Spark, Athena, and others) store analytics data as Parquet. One lesson makes
  the format familiar.
- **It models a real reporting pipeline.** The path — operational database,
  export a snapshot, analyse with a different engine — is how company reporting
  works, scaled up.

One teaching caution: the Parquet file is a *snapshot* taken at seed time. If new
attempts are added to PostgreSQL later, F9 will not reflect them until `seed.py`
runs again. The live F1 dashboard always shows current data; F9 shows the file
copy. That contrast — static analytical copy versus live transactional source —
is itself part of the lesson.

### 3.4 How the three fit the course

Docker, DuckDB, and Parquet are not extra topics. Together they complete the
picture that section 2 begins:

- Docker runs the **two databases** (relational and document) that section 2
  describes.
- DuckDB and Parquet add the **analytical layer** that the course title promises.
- The split is the standard Online Transaction Processing (OLTP) versus Online
  Analytical Processing (OLAP) pattern: PostgreSQL serves the live app, and the
  Parquet file plus DuckDB serve reporting.

The demo therefore shows four storage models — relational, document, columnar
file, and the in-process engine — under one small, consistent "right tool" theme.

---

## 4. How the demo maps to the course

The demo does not add any new learning outcome. It supplies the concrete object
that the existing lesson outcomes refer to. The table below shows the main links.

| Lesson | Course topic | What the demo shows |
|--------|--------------|---------------------|
| L01 | Database concepts and environment | The labelled static preview, then the finished app on three screens |
| L02–L03 | Data modelling and normalisation | The seven entities in the entity-relationship diagram, then the seven-table schema with one `NULL` |
| L04 | Introduction to SQL | Tables created, CSV loaded, first correct-answer rate |
| L05 | Advanced SQL and generated queries | Progress view, a wrong query, the corrected join |
| L06 | NoSQL and vector data | Remarks page (MongoDB) and keyword/vector search |
| L07 | Web database applications | First Flask route and first template |
| L08 | Sessions, authentication, safe access | Sign-in, roles, parameterised query, password hashing |
| L09 | Analytics and visualisation | Chart, Parquet check with DuckDB, full read-through |

**CILO coverage.** CILO3 is "design, build and query SQL and NoSQL databases".
The demo serves it directly: PostgreSQL covers the SQL side (L04–L05, L09) and
MongoDB covers the NoSQL side (L06). CILO4 (develop web database applications for
data analytics) is served by the Flask pages (L07–L09). The demo keeps the
assessment unchanged; it is a teaching object, not a new requirement.

---

## 5. The static preview versus the running application

GitHub Pages publishes the `docs/` folder as a website. GitHub Pages **cannot run
Python** and **cannot connect to a database**. For that reason the online page is
a **static preview**: fixed copies of the screens, clearly labelled on every page.

Keep three cases distinct:

| What is shown | Where it runs | Python running | Database connected |
|---------------|---------------|----------------|--------------------|
| Static preview | GitHub Pages, from `docs/` | No | No |
| Working app in class | Docker on the lab machine | Yes | Yes |
| Actually deployed app | A host that runs Python (not used in this course) | Yes | Yes |

The preview link is in `README.md` under "Live demo (static preview)". It is
labelled as a preview, not as the running application, on purpose.

---

## 6. What the demo leaves out (and the course still teaches)

The demo is deliberately small. The course still covers these topics; the demo
only models some of them.

- **Hosted cloud databases.** Supabase (hosted PostgreSQL) and Firebase Cloud
  Firestore (hosted document database) appear in L04 as a demonstration. The local
  EduDB app does not use them.
- **Vector extensions and embedding models.** L06 explains how embeddings are
  produced. The demo uses hand-authored concept vectors and plain-Python cosine
  similarity, so no model or key is needed at runtime.
- **PHP.** The previous course run used PHP. Its examples stay as reference
  reading only. The demo uses Python with Flask as the worked example.
- **Row-level security.** The demo checks the user role in Python. The course
  discusses database-level row security separately.
- **SQLite.** The course does not include SQLite in the running demo. The
  relational model is already taught by PostgreSQL, and a second relational
  engine would add teaching surface without a new data model. SQLite remains a
  useful zero-setup first SQL exercise that students may explore on their own; it
  is excluded here to keep the demo minimal and to favour the client-server model
  that a web application needs.

---

## 7. How students should use this demo

1. Open the static preview to see the finished result.
2. Follow [README.md](README.md) to run the application on your own computer
   with Docker.
3. Read `app.py` one block at a time, in the lesson order (L04 to L09).
4. For each screen, ask: which table does this read, and which query produced
   this number?
5. Compare the PostgreSQL tables with the MongoDB remarks. State one difference
   between the two data models in your own words.

The demo is a reference object. Your group project builds its own application in
its own private repository. You may reuse the patterns, but the dataset and the
code are yours to design.
