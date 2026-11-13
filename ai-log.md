# AI-generated query log (L05 example)

**Prompt 1:** "Write one SQL query that shows the correct-answer rate per question."

Tool output: the WRONG query in `queries.sql` (it joined `attempt` twice).

**Check:** compared the row count with `SELECT COUNT(*) FROM attempt GROUP BY question_id`.
The generated query returned twice as many rows, so its total was inflated.

**Prompt 2:** "Fix the join so each attempt is counted once."

Tool output: the CORRECT query in `queries.sql`.

**Check:** counts now match the per-question attempt count on answered rows
(`COUNT(is_correct)` ignores the skipped row, as intended).

**Lesson:** a generated JOIN can multiply rows. Always verify the row count before trusting a total.
