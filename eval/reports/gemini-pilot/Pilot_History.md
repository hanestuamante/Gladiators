# Gemini pilot history — 2026-07-16

## First live run after schema fix

- 12 cases, 12 successful API calls.
- End-to-end accuracy: 41.67%.
- Trajectory/evidence accuracy: 75%.
- Citation precision/recall and numeric verification: 100%.
- Parse fallback: 16.67%; generation fallback: 8.33%.
- Abstention F1: 71.43%.
- 5,044 input tokens; 7,346 output/thinking tokens; estimated paid list cost: 0.073680 USD.

Failure analysis: Gemini invented non-canonical `unsupported:*` labels, returned uppercase country and mapped an ads question to promotion. Runtime was then changed to canonicalize country and give deterministic unsupported-capability detection safety precedence.

## Post-fix validation attempts

One attempt completed one API call before quota failures. The final throttled attempt received three consecutive `ClientError:429` responses and zero successful API calls. Therefore the post-fix live metric and full `60 × 3` remain unverified until project quota resets or is increased.

The current harness fails Gemini cases that use parser/generator fallback, stops on `429`, checkpoints completed rows and supports `--resume`.
