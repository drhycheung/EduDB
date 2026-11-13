-- L05: a query written by a generative tool, then a corrected version.

-- WRONG: the tool joined the attempt table a second time, so every row is counted twice.
-- The total is inflated (here the denominator doubles, so the rate halves).
SELECT q.question_id,
       COUNT(a.is_correct) FILTER (WHERE a.is_correct) * 1.0
       / NULLIF(COUNT(a.is_correct), 0) AS wrong_rate
FROM attempt a
JOIN question q ON q.question_id = a.question_id
JOIN attempt a2 ON a2.question_id = a.question_id   -- accidental second join
GROUP BY q.question_id;

-- CORRECT: one join only. Each attempt is counted once.
SELECT q.question_id,
       COUNT(a.is_correct) FILTER (WHERE a.is_correct) * 1.0
       / NULLIF(COUNT(a.is_correct), 0) AS rate
FROM attempt a
JOIN question q ON q.question_id = a.question_id
GROUP BY q.question_id;

-- Check: the wrong version returns twice as many rows as the correct version for every question.
