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
import math         # used by the cosine similarity calculation
import os           # reads environment variables and builds file paths
import re           # splits question text into words for keyword search
import secrets      # creates random, unguessable session identifiers
from datetime import datetime  # stamps the time a document is edited

# Third-party libraries installed from requirements.txt.
import duckdb       # reads the Parquet copy of the attempts table
import psycopg      # connects to PostgreSQL
from pymongo import MongoClient  # connects to MongoDB for F7 teacher remarks
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

# MongoDB connection settings for F7 (teacher remarks). One document per
# learner. The defaults match docker-compose.yml and .env.example.
MONGO = dict(
    host=os.environ.get("MONGO_HOST", "localhost"),
    port=int(os.environ.get("MONGO_PORT", "27017")),
    db=os.environ.get("MONGO_DB", "edudb"),
    coll=os.environ.get("MONGO_COLLECTION", "remarks"),
)

# One shared MongoDB client. We connect lazily (on first use) so pages that do
# not need MongoDB still work when it is not running yet.
_mongo_client = None

def get_mongo():
    """Return the remarks collection, connecting on first call."""
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(MONGO["host"], MONGO["port"], serverSelectionTimeoutMS=5000)
    return _mongo_client[MONGO["db"]][MONGO["coll"]]

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

    The database stores the hash as TEXT, so we return the hex string form.
    The login check compares this string with the stored string.
    """
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()


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
# vector that points toward the kind of note it should match. The questions are
# about school maths so students see clearly that this is sample data, not the
# database material of the course.
PRACTICE = [
    {"id": 1, "text": "How do I find the unit price of apples?",
     "vec": [0.9, 0.2, 0.3, 0.1, 0.2, 0.1, 0.5, 0.2]},
    {"id": 2, "text": "How do I solve a linear equation?",
     "vec": [0.2, 0.9, 0.3, 0.1, 0.2, 0.1, 0.5, 0.2]},
    {"id": 3, "text": "How do I add fractions?",
     "vec": [0.3, 0.2, 0.9, 0.1, 0.2, 0.1, 0.5, 0.2]},
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
    # A learner sees only their own row. A teacher sees every learner, so they
    # can spot who needs help. This is the same data, filtered by role.
    user = current_user()
    if not user:
        return redirect("/login")
    conn = get_conn()
    # Show each learner's success rate on quiz 1 and on quiz 2 side by side.
    # AVG(CASE WHEN ...) picks the attempts for one quiz, else ignores them.
    # This is the SQL way to build a small pivot table without a chart library.
    if user["role"] == "teacher":
        rows = conn.execute("SELECT s.display_name, AVG(CASE WHEN q.quiz_id = 1 THEN a.is_correct::int END) AS q1, "
                            "AVG(CASE WHEN q.quiz_id = 2 THEN a.is_correct::int END) AS q2 FROM student s "
                            "JOIN attempt a ON a.student_id = s.student_id JOIN question q ON q.question_id = a.question_id "
                            "GROUP BY s.display_name ORDER BY s.display_name").fetchall()
        conn.close()
        return render_template("progress.html", rows=rows, user=user, teacher=True)
    # A learner sees only their own attempt window. The %s keeps the id out of
    # the SQL text, which prevents SQL injection.
    rows = conn.execute("SELECT s.display_name, AVG(CASE WHEN q.quiz_id = 1 THEN a.is_correct::int END) AS q1, "
                        "AVG(CASE WHEN q.quiz_id = 2 THEN a.is_correct::int END) AS q2 FROM student s "
                        "JOIN attempt a ON a.student_id = s.student_id JOIN question q ON q.question_id = a.question_id "
                        "WHERE s.student_id = %s GROUP BY s.display_name", [user["user_id"]]).fetchall()
    conn.close()
    return render_template("progress.html", rows=rows, user=user, teacher=False)


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


@app.route("/remarks", methods=["GET", "POST"])
def remarks():  # F7 teacher remarks on each learner, stored in MongoDB
    # Only a signed-in user may open this page. Teachers add remarks; learners
    # read only their own. This keeps the writing role with the teacher.
    user = current_user()
    if not user:
        return redirect("/login")
    try:
        coll = get_mongo()
    except Exception:
        return render_template("remarks.html", user=user, teacher=(user["role"] == "teacher"),
                               error="Remarks are unavailable: MongoDB is not running. "
                                     "Start it with 'docker compose up -d'.", students=[], own=None)
    mongo_coll = f"{MONGO['db']}.{MONGO['coll']}"
    if request.method == "POST":
        # Only a teacher may change remarks. A learner's POST is ignored.
        if user["role"] != "teacher":
            return redirect("/remarks")
        action = request.form.get("action")
        sid = int(request.form["student_id"])
        if action == "update":
            # Upsert one remark document per learner, matched on student_id, so
            # each learner keeps a single record the teacher can revise.
            coll.update_one(
                {"student_id": sid},
                {"$set": {"student_id": sid, "display_name": request.form["display_name"],
                          "remark": request.form["remark"],
                          "updated_at": datetime.now().isoformat(timespec="seconds"),
                          "by": user["name"]}},
                upsert=True)
        elif action == "delete":
            coll.delete_one({"student_id": sid})
        return redirect("/remarks")
    # GET request.
    if user["role"] == "teacher":
        # List every learner with their current remark so the teacher can edit.
        conn = get_conn()
        students = conn.execute(
            "SELECT student_id, display_name FROM student WHERE display_name != 'Teacher' "
            "ORDER BY student_id").fetchall()
        conn.close()
        stored = {r["student_id"]: r for r in coll.find()}
        rows = []
        for sid, name in students:
            rec = stored.get(sid)
            rows.append({"student_id": sid, "display_name": name,
                         "remark": rec["remark"] if rec else "",
                         "updated_at": rec["updated_at"] if rec else ""})
        return render_template("remarks.html", students=rows, mongo_coll=mongo_coll,
                               user=user, teacher=True)
    # A learner sees only their own remark.
    own = coll.find_one({"student_id": user["user_id"]})
    return render_template("remarks.html", own=own, mongo_coll=mongo_coll,
                           user=user, teacher=False)


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
