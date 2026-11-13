"""EduDB: a minimal server-side learning analytics demo for INT4087.

Every route is explained in class, one block per lesson (L01 to L09). The database
holds synthetic quiz attempts. No external service, no JavaScript, no hidden logic.
"""
import csv
import hashlib
import math
import os
import re
import secrets
from datetime import datetime

import duckdb
import psycopg
from flask import (Flask, redirect, render_template, request, make_response)

app = Flask(__name__)
SESSIONS = {}  # session_id -> {user_id, role, name}; in-memory only (single worker)
DATA = os.path.join(os.path.dirname(__file__), "data")
DOC_PATH = os.path.join(DATA, "documents.json")

DB = dict(
    host=os.environ.get("DB_HOST", "localhost"),
    port=os.environ.get("DB_PORT", "5432"),
    dbname=os.environ.get("DB_NAME", "edudb"),
    user=os.environ.get("DB_USER", "postgres"),
    password=os.environ.get("DB_PASSWORD", "postgres"),
)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")


def get_conn():
    return psycopg.connect(**DB)


def make_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)


def current_user():
    return SESSIONS.get(request.cookies.get("sid"))


def load_excerpts():
    with open(os.path.join(DATA, "excerpts.csv"), newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["vec"] = [float(r[f"v{i + 1}"]) for i in range(8)]
    return rows


EXCERPTS = load_excerpts()

PRACTICE = [
    {"id": 1, "text": "How do I use GROUP BY to count correct answers?",
     "vec": [0.2, 0.9, 0.8, 0.1, 0.2, 0.1, 0.5, 0.2]},
    {"id": 2, "text": "What is a primary key?",
     "vec": [0.9, 0.2, 0.3, 0.5, 0.1, 0.2, 0.3, 0.3]},
    {"id": 3, "text": "Why does my JOIN return too many rows?",
     "vec": [0.3, 0.7, 0.4, 0.8, 0.1, 0.1, 0.6, 0.2]},
]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


@app.route("/")
def dashboard():  # F1 rate by question, F2 rate by topic
    conn = get_conn()
    q = conn.execute("SELECT q.question_id, COUNT(a.is_correct) FILTER (WHERE a.is_correct) * 1.0 "
                     "/ NULLIF(COUNT(a.is_correct), 0) FROM question q LEFT JOIN attempt a "
                     "ON a.question_id = q.question_id GROUP BY q.question_id ORDER BY q.question_id").fetchall()
    t = conn.execute("SELECT t.topic_name, COUNT(a.is_correct) FILTER (WHERE a.is_correct) * 1.0 "
                     "/ NULLIF(COUNT(a.is_correct), 0) FROM topic t JOIN question q ON q.topic_id = t.topic_id "
                     "LEFT JOIN attempt a ON a.question_id = q.question_id GROUP BY t.topic_name").fetchall()
    conn.close()
    return render_template("dashboard.html", q_rates=q, t_rates=t, user=current_user())


@app.route("/progress")
def progress():  # F3 progress per learner (window over quizzes)
    conn = get_conn()
    rows = conn.execute("SELECT s.display_name, AVG(CASE WHEN q.quiz_id = 1 THEN a.is_correct::int END) AS q1, "
                        "AVG(CASE WHEN q.quiz_id = 2 THEN a.is_correct::int END) AS q2 FROM student s "
                        "JOIN attempt a ON a.student_id = s.student_id JOIN question q ON q.question_id = a.question_id "
                        "GROUP BY s.display_name ORDER BY s.display_name").fetchall()
    conn.close()
    return render_template("progress.html", rows=rows, user=current_user())


@app.route("/student")
def student_view():  # F4 learner sees own attempts; teacher sees all
    user = current_user()
    if not user:
        return redirect("/login")
    conn = get_conn()
    if user["role"] == "teacher":
        rows = conn.execute("SELECT s.display_name, q.question_id, a.is_correct FROM attempt a "
                            "JOIN student s ON s.student_id = a.student_id JOIN question q ON q.question_id = a.question_id "
                            "ORDER BY s.display_name, q.question_id").fetchall()
    else:
        rows = conn.execute("SELECT q.question_id, a.is_correct FROM attempt a JOIN question q "
                            "ON q.question_id = a.question_id WHERE a.student_id = %s ORDER BY q.question_id",
                            [user["user_id"]]).fetchall()
        rate = conn.execute("SELECT COUNT(a.is_correct) FILTER (WHERE a.is_correct) * 1.0 "
                            "/ NULLIF(COUNT(a.is_correct), 0) FROM attempt a WHERE a.student_id = %s",
                            [user["user_id"]]).fetchone()[0]
        conn.close()
        return render_template("student.html", rows=rows, rate=rate, user=user)
    conn.close()
    return render_template("student.html", rows=rows, user=user)


@app.route("/login", methods=["GET", "POST"])
def login():  # F5 sign-in, roles, one hash check
    if request.method == "POST":
        name, pw = request.form["username"], request.form["password"]
        conn = get_conn()
        row = conn.execute("SELECT student_id, display_name, password_hash, password_salt FROM student "
                           "WHERE display_name = %s", [name]).fetchone()
        conn.close()
        if row and make_hash(pw, row[3]) == row[2]:
            sid = secrets.token_hex(16)
            SESSIONS[sid] = {"user_id": row[0], "role": "teacher" if row[1] == "Teacher" else "learner", "name": row[1]}
            resp = make_response(redirect("/student"))
            resp.set_cookie("sid", sid)
            return resp
        return "Wrong username or password", 401
    return render_template("login.html", user=current_user())


@app.route("/logout")
def logout():
    SESSIONS.pop(request.cookies.get("sid"), None)
    resp = make_response(redirect("/"))
    resp.delete_cookie("sid")
    return resp


@app.route("/search")
def search():  # F6 keyword and vector retrieval over excerpts
    qid = request.args.get("qid", type=int)
    if not qid:
        return render_template("search.html", excerpts=EXCERPTS, practice=PRACTICE, user=current_user())
    pq = next(p for p in PRACTICE if p["id"] == qid)
    stop = {"to", "do", "how", "use", "by", "i", "a", "an", "the", "of", "for", "in", "on",
            "and", "is", "are", "what", "why", "when", "with"}
    words = [w for w in re.findall(r"[a-z]+", pq["text"].lower()) if len(w) > 1 and w not in stop]
    keyword = [e for e in EXCERPTS if any(w in e["excerpt_text"].lower() for w in words)]
    vector = sorted(EXCERPTS, key=lambda e: cosine(pq["vec"], e["vec"]), reverse=True)[:3]
    return render_template("search.html", pq=pq, keyword=keyword, vector=vector,
                           excerpts=EXCERPTS, practice=PRACTICE, user=current_user())


def load_docs():
    with open(DOC_PATH) as f:
        import json
        return json.load(f)


def save_docs(docs):
    with open(DOC_PATH, "w") as f:
        import json
        json.dump(docs, f, indent=2)


@app.route("/documents", methods=["GET", "POST"])
def documents():  # F7 create, read, update, delete on question documents
    docs = load_docs()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            docs.append({"doc_id": max([d["doc_id"] for d in docs] + [0]) + 1,
                         "question_id": int(request.form["question_id"]),
                         "title": request.form["title"], "body": request.form["body"],
                         "updated_at": datetime.now().isoformat(timespec="seconds")})
        elif action == "update":
            for d in docs:
                if d["doc_id"] == int(request.form["doc_id"]):
                    d.update(question_id=int(request.form["question_id"]), title=request.form["title"],
                             body=request.form["body"], updated_at=datetime.now().isoformat(timespec="seconds"))
        elif action == "delete":
            docs = [d for d in docs if d["doc_id"] != int(request.form["doc_id"])]
        save_docs(docs)
        return redirect("/documents")
    return render_template("documents.html", docs=docs, user=current_user())


@app.route("/chart", methods=["GET", "POST"])
def chart():  # F8 interactive chart without JavaScript
    topic = request.form.get("topic_id") or request.args.get("topic_id", "1")
    conn = get_conn()
    rows = conn.execute("SELECT q.question_id, COUNT(a.is_correct) FILTER (WHERE a.is_correct) * 1.0 "
                       "/ NULLIF(COUNT(a.is_correct), 0) FROM question q LEFT JOIN attempt a "
                       "ON a.question_id = q.question_id WHERE q.topic_id = %s GROUP BY q.question_id "
                       "ORDER BY q.question_id", [topic]).fetchall()
    topics = conn.execute("SELECT topic_id, topic_name FROM topic ORDER BY topic_id").fetchall()
    conn.close()
    return render_template("chart.html", rows=rows, topics=topics, topic=int(topic), user=current_user())


@app.route("/parquet")
def parquet():  # F9 same rate read from a Parquet file with DuckDB
    rate = duckdb.connect().execute(
        f"SELECT AVG(CAST(is_correct AS INTEGER)) FROM '{os.path.join(DATA, 'attempts.parquet')}' "
        f"WHERE is_correct IS NOT NULL").fetchone()[0]
    return render_template("parquet.html", rate=rate, user=current_user())


if __name__ == "__main__":
    app.run(debug=False)
