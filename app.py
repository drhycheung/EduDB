"""EduDB: a minimal server-side learning analytics demo for INT4087.

This single file is the whole application. Each function below becomes one web
page. The pages are explained in class from Lesson 1 to Lesson 9.

The application connects to a PostgreSQL database that holds synthetic quiz
attempts. It shows rates, progress, search and a chart. It uses no JavaScript
and no external service, so every value on the screen comes from one SQL query.

NOTE ON THE STATIC PREVIEW:
The pages published with GitHub Pages are a labelled mockup. They are plain
HTML and connect to no database. The real application runs on your computer
with Docker, as described in the README.
"""

# Standard libraries that ship with Python.
import csv          # reads the comma-separated data files
import hashlib      # builds one-way password hashes with a salt
import json         # reads and writes the documents file
import math         # used by the cosine similarity calculation
import os           # reads environment variables and builds file paths
import re           # splits question text into words for keyword search
import secrets      # creates random, unguessable session identifiers
from datetime import datetime  # stamps the time a document is edited

# Third-party libraries installed from requirements.txt.
import duckdb       # reads the Parquet copy of the attempts table
import psycopg      # connects to PostgreSQL
from flask import (Flask, redirect, render_template, request, make_response)

# Read settings from a ".env" file when one exists. This keeps the database
# address and the secret key out of the code. python-dotenv is listed in
# requirements.txt, so the import below works after "pip install".
from dotenv import load_dotenv
load_dotenv()  # fill os.environ from .env BEFORE we read DB_* and SECRET_KEY

# Create the Flask application. Flask maps each @app.route below to a web page.
app = Flask(__name__)

# In-memory session store. The key is a random session id sent to the browser
# as a cookie. The value records who the user is. A real application would keep
# this in a shared store so many workers could read it; here one process is
# enough for teaching.
SESSIONS = {}  # session_id -> {"user_id", "role", "name"}

# Folder that holds every data file. It sits next to this script so the path
# works on any computer.
DATA = os.path.join(os.path.dirname(__file__), "data")

# Path to the question documents file used by the create/read/update/delete
# feature. It is plain JSON so students can open and edit it by hand.
DOC_PATH = os.path.join(DATA, "documents.json")

# Database connection settings. They come from environment variables so the
# same code runs on a laptop and on a server. The default values match
# docker-compose.yml and .env.example.
DB = dict(
    host=os.environ.get("DB_HOST", "localhost"),
    port=os.environ.get("DB_PORT", "5432"),
    dbname=os.environ.get("DB_NAME", "edudb"),
    user=os.environ.get("DB_USER", "postgres"),
    password=os.environ.get("DB_PASSWORD", "postgres"),
)

# Secret key used to sign the session cookie. In class we set this from .env
# (SECRET_KEY). The default value is for local teaching only.
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")


def get_conn():
    """Open and return one connection to PostgreSQL using the settings above."""
    return psycopg.connect(**DB)


def make_hash(password, salt):
    """Return a one-way hash of the password combined with its salt.

    We use PBKDF2 with SHA-256 and 100,000 rounds. The salt makes two users
    with the same password store different hashes, so an attacker who reads
    the database cannot tell when passwords match.
    """
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)


def current_user():
    """Read the session cookie and return the stored user, or None if signed out."""
    return SESSIONS.get(request.cookies.get("sid"))


def load_excerpts():
    """Read excerpts.csv and turn each row's eight v-columns into one vector.

    A vector is a list of eight numbers. The numbers are written by hand for the
    lesson so the cosine similarity result is easy to check.
    """
    with open(os.path.join(DATA, "excerpts.csv"), newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["vec"] = [float(r[f"v{i + 1}"]) for i in range(8)]
    return rows


# Load the excerpts once when the program starts. They do not change while the
# application runs.
EXCERPTS = load_excerpts()

# Three practice questions used by the search screen. Each has a hand-written
# vector that points toward the kind of document it should match.
PRACTICE = [
    {"id": 1, "text": "How do I use GROUP BY to count correct answers?",
     "vec": [0.2, 0.9, 0.8, 0.1, 0.2, 0.1, 0.5, 0.2]},
    {"id": 2, "text": "What is a primary key?",
     "vec": [0.9, 0.2, 0.3, 0.5, 0.1, 0.2, 0.3, 0.3]},
    {"id": 3, "text": "Why does my JOIN return too many rows?",
     "vec": [0.3, 0.7, 0.4, 0.8, 0.1, 0.1, 0.6, 0.2]},
]


def cosine(a, b):
    """Return the cosine similarity of two vectors.

    Cosine similarity measures the angle between two vectors. A value near 1.0
    means the vectors point the same way (similar meaning). A value near 0.0
    means they are unrelated. This is the maths behind vector search.
    """
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


@app.route("/")
def dashboard():  # F1 rate by question, F2 rate by topic
    # Open one connection for this request.
    conn = get_conn()

    # F1: success rate for each question.
    # COUNT(...) FILTER (WHERE a.is_correct) counts only the correct attempts.
    # We multiply by 1.0 to keep a decimal result, then divide by the total.
    # NULLIF(total, 0) returns NULL when the total is 0, so we never divide by
    # zero. LEFT JOIN keeps every question even when it has no attempts.
    q = conn.execute("SELECT q.question_id, COUNT(a.is_correct) FILTER (WHERE a.is_correct) * 1.0 "
                     "/ NULLIF(COUNT(a.is_correct), 0) FROM question q LEFT JOIN attempt a "
                     "ON a.question_id = q.question_id GROUP BY q.question_id ORDER BY q.question_id").fetchall()

    # F2: success rate grouped by topic.
    # We join topic -> question -> attempt, then group by topic name.
    t = conn.execute("SELECT t.topic_name, COUNT(a.is_correct) FILTER (WHERE a.is_correct) * 1.0 "
                     "/ NULLIF(COUNT(a.is_correct), 0) FROM topic t JOIN question q ON q.topic_id = t.topic_id "
                     "LEFT JOIN attempt a ON a.question_id = q.question_id GROUP BY t.topic_name").fetchall()

    conn.close()  # Always close the connection after use.
    # Send the two result lists to the dashboard template.
    return render_template("dashboard.html", q_rates=q, t_rates=t, user=current_user())


@app.route("/progress")
def progress():  # F3 progress per learner (window over quizzes)
    conn = get_conn()
    # Show each learner's success rate on quiz 1 and on quiz 2 side by side.
    # AVG(CASE WHEN ...) picks the attempts for one quiz, else ignores them.
    # This is the SQL way to build a small pivot table without a chart library.
    rows = conn.execute("SELECT s.display_name, AVG(CASE WHEN q.quiz_id = 1 THEN a.is_correct::int END) AS q1, "
                        "AVG(CASE WHEN q.quiz_id = 2 THEN a.is_correct::int END) AS q2 FROM student s "
                        "JOIN attempt a ON a.student_id = s.student_id JOIN question q ON q.question_id = a.question_id "
                        "GROUP BY s.display_name ORDER BY s.display_name").fetchall()
    conn.close()
    return render_template("progress.html", rows=rows, user=current_user())


@app.route("/student")
def student_view():  # F4 learner sees own attempts; teacher sees all
    # If the visitor is not signed in, send them to the sign-in page.
    user = current_user()
    if not user:
        return redirect("/login")
    conn = get_conn()
    if user["role"] == "teacher":
        # A teacher may see every learner's attempts.
        rows = conn.execute("SELECT s.display_name, q.question_id, a.is_correct FROM attempt a "
                            "JOIN student s ON s.student_id = a.student_id JOIN question q ON q.question_id = a.question_id "
                            "ORDER BY s.display_name, q.question_id").fetchall()
        conn.close()
        return render_template("student.html", rows=rows, user=user)
    # A learner sees only their own attempts. The %s is filled with their id.
    # Using %s (a parameter) keeps the value separate from the SQL text, which
    # prevents SQL injection. Never build SQL by joining strings from the user.
    rows = conn.execute("SELECT q.question_id, a.is_correct FROM attempt a JOIN question q "
                        "ON q.question_id = a.question_id WHERE a.student_id = %s ORDER BY q.question_id",
                        [user["user_id"]]).fetchall()
    # Compute this learner's overall success rate for the summary card.
    rate = conn.execute("SELECT COUNT(a.is_correct) FILTER (WHERE a.is_correct) * 1.0 "
                        "/ NULLIF(COUNT(a.is_correct), 0) FROM attempt a WHERE a.student_id = %s",
                        [user["user_id"]]).fetchone()[0]
    conn.close()
    return render_template("student.html", rows=rows, rate=rate, user=user)


@app.route("/login", methods=["GET", "POST"])
def login():  # F5 sign-in, roles, one hash check
    if request.method == "POST":
        # Read the submitted username and password from the form.
        name, pw = request.form["username"], request.form["password"]
        conn = get_conn()
        # Look up the user by display name. The %s keeps the name out of the
        # SQL command text, so a strange name cannot change the query.
        row = conn.execute("SELECT student_id, display_name, password_hash, password_salt FROM student "
                           "WHERE display_name = %s", [name]).fetchone()
        conn.close()
        # Check the password without storing it. We hash the typed password with
        # the stored salt and compare it to the stored hash. The original
        # password is never saved, only the hash.
        if row and make_hash(pw, row[3]) == row[2]:
            # Create a new random session id and remember the user in memory.
            sid = secrets.token_hex(16)
            SESSIONS[sid] = {"user_id": row[0],
                             "role": "teacher" if row[1] == "Teacher" else "learner",
                             "name": row[1]}
            # Send the browser a cookie holding the session id, then go to the
            # learner page.
            resp = make_response(redirect("/student"))
            resp.set_cookie("sid", sid)
            return resp
        # Wrong name or wrong password. We return the same message for both so
        # an attacker cannot tell which one was wrong.
        return "Wrong username or password", 401
    # GET request: show the sign-in form.
    return render_template("login.html", user=current_user())


@app.route("/logout")
def logout():
    # Forget the session on the server and delete the cookie on the browser.
    SESSIONS.pop(request.cookies.get("sid"), None)
    resp = make_response(redirect("/"))
    resp.delete_cookie("sid")
    return resp


@app.route("/search")
def search():  # F6 keyword and vector retrieval over excerpts
    # If no question was chosen, show the search page with all excerpts.
    qid = request.args.get("qid", type=int)
    if not qid:
        return render_template("search.html", excerpts=EXCERPTS, practice=PRACTICE, user=current_user())
    # Find the chosen practice question.
    pq = next(p for p in PRACTICE if p["id"] == qid)
    # Common words (stopwords) carry little meaning, so we ignore them. We also
    # drop single letters, which the word splitter would otherwise keep.
    stop = {"to", "do", "how", "use", "by", "i", "a", "an", "the", "of", "for", "in", "on",
            "and", "is", "are", "what", "why", "when", "with"}
    words = [w for w in re.findall(r"[a-z]+", pq["text"].lower()) if len(w) > 1 and w not in stop]
    # Keyword search: keep excerpts that contain any of the question words.
    keyword = [e for e in EXCERPTS if any(w in e["excerpt_text"].lower() for w in words)]
    # Vector search: rank excerpts by cosine similarity to the question vector
    # and keep the three closest. This finds meaning, not just matching words.
    vector = sorted(EXCERPTS, key=lambda e: cosine(pq["vec"], e["vec"]), reverse=True)[:3]
    return render_template("search.html", pq=pq, keyword=keyword, vector=vector,
                           excerpts=EXCERPTS, practice=PRACTICE, user=current_user())


def load_docs():
    """Read the documents file and return it as a Python list of records."""
    with open(DOC_PATH) as f:
        return json.load(f)


def save_docs(docs):
    """Write the list of records back to the documents file, nicely indented."""
    with open(DOC_PATH, "w") as f:
        json.dump(docs, f, indent=2)


@app.route("/documents", methods=["GET", "POST"])
def documents():  # F7 create, read, update, delete on question documents
    docs = load_docs()
    if request.method == "POST":
        # The form tells us which of the four actions to perform.
        action = request.form.get("action")
        if action == "create":
            # Add a new record. We pick the next id as one more than the largest
            # id already present. This keeps ids unique without a database.
            docs.append({"doc_id": max([d["doc_id"] for d in docs] + [0]) + 1,
                         "question_id": int(request.form["question_id"]),
                         "title": request.form["title"], "body": request.form["body"],
                         "updated_at": datetime.now().isoformat(timespec="seconds")})
        elif action == "update":
            # Find the record by id and replace its editable fields.
            for d in docs:
                if d["doc_id"] == int(request.form["doc_id"]):
                    d.update(question_id=int(request.form["question_id"]), title=request.form["title"],
                             body=request.form["body"], updated_at=datetime.now().isoformat(timespec="seconds"))
        elif action == "delete":
            # Keep every record except the one with the chosen id.
            docs = [d for d in docs if d["doc_id"] != int(request.form["doc_id"])]
        save_docs(docs)
        # After a change, show the page again with the updated list.
        return redirect("/documents")
    # GET request: show the current list of documents.
    return render_template("documents.html", docs=docs, user=current_user())


@app.route("/chart", methods=["GET", "POST"])
def chart():  # F8 interactive chart without JavaScript
    # The chosen topic comes from the form (after a click) or the web address.
    # The default is topic 1 so the first view shows something.
    topic = request.form.get("topic_id") or request.args.get("topic_id", "1")
    conn = get_conn()
    # Success rate for each question inside the chosen topic.
    rows = conn.execute("SELECT q.question_id, COUNT(a.is_correct) FILTER (WHERE a.is_correct) * 1.0 "
                       "/ NULLIF(COUNT(a.is_correct), 0) FROM question q LEFT JOIN attempt a "
                       "ON a.question_id = q.question_id WHERE q.topic_id = %s GROUP BY q.question_id "
                       "ORDER BY q.question_id", [topic]).fetchall()
    # The list of topics fills the selector on the page.
    topics = conn.execute("SELECT topic_id, topic_name FROM topic ORDER BY topic_id").fetchall()
    conn.close()
    # The template draws the bars itself using plain HTML, so no script runs
    # in the browser.
    return render_template("chart.html", rows=rows, topics=topics, topic=int(topic), user=current_user())


@app.route("/parquet")
def parquet():  # F9 same rate read from a Parquet file with DuckDB
    # DuckDB can read a Parquet file directly, without PostgreSQL. We compute the
    # same overall success rate as elsewhere to show the file holds the same
    # data. The path is built from the DATA folder so it works on any computer.
    rate = duckdb.connect().execute(
        f"SELECT AVG(CAST(is_correct AS INTEGER)) FROM '{os.path.join(DATA, 'attempts.parquet')}' "
        f"WHERE is_correct IS NOT NULL").fetchone()[0]
    return render_template("parquet.html", rate=rate, user=current_user())


if __name__ == "__main__":
    # Run the built-in server for local teaching. debug=False keeps error
    # details away from the browser.
    app.run(debug=False)
