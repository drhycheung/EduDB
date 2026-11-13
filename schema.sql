-- EduDB schema: seven tables for a learning analytics demonstration.
-- Run once with seed.py. Every column has a plain-language meaning in class.

CREATE TABLE student (
    student_id    INTEGER PRIMARY KEY,
    display_name  TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL
);

CREATE TABLE course (
    course_id    INTEGER PRIMARY KEY,
    course_title TEXT NOT NULL
);

CREATE TABLE enrolment (
    student_id INTEGER REFERENCES student(student_id),
    course_id  INTEGER REFERENCES course(course_id),
    PRIMARY KEY (student_id, course_id)
);

CREATE TABLE topic (
    topic_id   INTEGER PRIMARY KEY,
    topic_name TEXT NOT NULL
);

CREATE TABLE quiz (
    quiz_id    INTEGER PRIMARY KEY,
    course_id  INTEGER REFERENCES course(course_id),
    quiz_week  INTEGER
);

CREATE TABLE question (
    question_id   INTEGER PRIMARY KEY,
    quiz_id       INTEGER REFERENCES quiz(quiz_id),
    topic_id      INTEGER REFERENCES topic(topic_id),
    question_text TEXT NOT NULL
);

CREATE TABLE attempt (
    attempt_id   INTEGER PRIMARY KEY,
    student_id   INTEGER REFERENCES student(student_id),
    question_id  INTEGER REFERENCES question(question_id),
    is_correct   BOOLEAN,
    attempted_at TEXT
);
-- is_correct is NULL when a learner skipped the question.
