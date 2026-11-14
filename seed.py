"""Seed the EduDB database from the CSV files in data/.

Run after the container is up:
    python3 seed.py
It creates the seven tables, loads each CSV, then writes a Parquet copy of the
attempts for the DuckDB check in F9. Every row is synthetic.
"""
import csv
import json
import os
import time
import duckdb
import psycopg
from pymongo import MongoClient

DATA = os.path.join(os.path.dirname(__file__), "data")

DB = dict(
    host=os.environ.get("DB_HOST", "localhost"),
    port=os.environ.get("DB_PORT", "5432"),
    dbname=os.environ.get("DB_NAME", "edudb"),
    user=os.environ.get("DB_USER", "postgres"),
    password=os.environ.get("DB_PASSWORD", "postgres"),
)


def load_rows(name):
    with open(os.path.join(DATA, name), newline="") as f:
        return list(csv.DictReader(f))


def main():
    conn = psycopg.connect(**DB)
    conn.autocommit = True
    cur = conn.cursor()
    with open(os.path.join(os.path.dirname(__file__), "schema.sql")) as f:
        cur.execute(f.read())

    tables = {
        "Student.csv": ("student", ["student_id", "display_name", "password_hash", "password_salt"]),
        "Course.csv": ("course", ["course_id", "course_title"]),
        "Enrolment.csv": ("enrolment", ["student_id", "course_id"]),
        "Topic.csv": ("topic", ["topic_id", "topic_name"]),
        "Quiz.csv": ("quiz", ["quiz_id", "course_id", "quiz_week"]),
        "Question.csv": ("question", ["question_id", "quiz_id", "topic_id", "question_text"]),
    }
    for file, (table, cols) in tables.items():
        for row in load_rows(file):
            values = [row[c] if row[c] != "" else None for c in cols]
            cur.execute(
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                values,
            )

    attempts = load_rows("Attempt.csv")
    for row in attempts:
        cur.execute(
            "INSERT INTO attempt (attempt_id, student_id, question_id, is_correct, attempted_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            [row["attempt_id"], row["student_id"], row["question_id"],
             None if row["is_correct"] == "" else row["is_correct"] == "true", row["attempted_at"]],
        )
    print("Loaded", len(attempts), "attempts (plus six smaller tables).")

    # Parquet copy for the DuckDB check (F9). DuckDB reads the CSV directly.
    duckdb.connect().execute(
        f"COPY (SELECT * FROM read_csv_auto('{os.path.join(DATA, 'Attempt.csv')}')) "
        f"TO '{os.path.join(DATA, 'attempts.parquet')}' (FORMAT PARQUET)"
    )
    print("Wrote data/attempts.parquet for the DuckDB check.")

    # MongoDB: seed one remark document per learner for F7 (teacher remarks).
    mhost = os.environ.get("MONGO_HOST", "localhost")
    mport = int(os.environ.get("MONGO_PORT", "27017"))
    mclient = MongoClient(mhost, mport, serverSelectionTimeoutMS=1000)
    ready = False
    for _ in range(30):  # wait up to ~30s for MongoDB to accept connections
        try:
            mclient.admin.command("ping")
            ready = True
            break
        except Exception:
            time.sleep(1)
    if ready:
        mdb = os.environ.get("MONGO_DB", "edudb")
        mcoll_name = os.environ.get("MONGO_COLLECTION", "remarks")
        mcoll = mclient[mdb][mcoll_name]
        with open(os.path.join(DATA, "remarks.json")) as f:
            remarks = json.load(f)
        mcoll.delete_many({})
        if remarks:
            mcoll.insert_many(remarks)
        print(f"Seeded {len(remarks)} remarks into MongoDB ({mdb}.{mcoll_name}).")
    else:
        print("MongoDB not reachable after 30s; skipping remarks seed. Run 'docker compose up -d' first.")

    conn.close()


if __name__ == "__main__":
    main()
