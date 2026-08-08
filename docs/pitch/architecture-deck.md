# Verifiable E-Commerce Analytics — Architecture Deck

13 slides. Diagrams on slides 2, 5, 7, 8, 11 — each carries a full drawing brief
for a diagramming assistant.

All figures verified against the running system at commit `1df8e5b` on 2026-08-08.

---

## Slide 1 — The failure mode that actually costs money

> **A system that answers the wrong question fluently is more dangerous than one that declines.**

An analytics assistant fails in two ways. One is visible: it refuses, and the user
asks again. The other is invisible: it returns a confident paragraph, with a real
number, a real citation, and an answer to a question nobody asked.

A case caught in our own test suite:

| | |
|---|---|
| **Question asked** | "How much bigger is the average discount in Indonesia than in Vietnam?" |
| **Answer returned** | "There are 474 product listings in Indonesia." |
| **Number** | correct |
| **Citation** | valid, resolvable |
| **Automatic checks** | all passed |

Nothing in the output tells the reader it is wrong. A business decision made on
that answer is made on nothing.

**Design constraint that follows:** every number shown must be traceable to a
stored record of where it came from — or it must not be shown at all.

---

## Slide 2 — System architecture 🎨

**On-slide text:** 3,972 components · 8,272 dependencies · 306 clusters ·
**zero circular dependencies**. Five components carry the system: the typed query
plan (134 links), the orchestrator (102), the evidence record (64), the plan step
(62), the parsed request (56).

````text
DRAWING BRIEF — SLIDE 2 "SYSTEM ARCHITECTURE"

Draw a vertical top-to-bottom flow, nine stages, 16:9 landscape.
Audience is non-technical. Use the plain-English labels given here VERBATIM.
Do not invent, rename, merge or reorder any stage.

INPUT BOX: "User question (Vietnamese or Indonesian, may be unpunctuated,
            may contain several sub-questions)"

STAGE 1 — "UNDERSTAND THE QUESTION"
   Draw ONE box containing TWO side-by-side sub-boxes feeding a THIRD box below:
     left sub-box  : "Language model proposes"        -- PURPLE
     right sub-box : "Rule-based parser"              -- BLUE
     box below     : "Rules have final say"           -- BLUE
   Label the arrow from the left sub-box down: "proposal only"
   NEVER draw the language model connecting directly to Stage 2.
   It must always pass through the "Rules have final say" box.
   Add a small caption under the left sub-box:
     "active only when a model provider is configured; the rule-based parser
      runs in every configuration"

STAGE 2 — "DECIDE WHERE THE ANSWER COMES FROM"  (BLUE)
   Five labelled outgoing branches:
   "internal data only" | "internal + web context" | "web context only" |
   "ask the user to clarify" | "decline"

STAGE 3 — "IDENTIFY WHICH PRODUCT OR SHOP IS MEANT"  (BLUE)
   Four outcome labels EXACTLY:
   "resolved" | "not found" | "invalid reference" | "too broad / ambiguous"
   Caption: "When two candidates are equally likely, the system asks back.
             It is never allowed to pick the more popular one."

STAGE 4 — "PERMISSION CHECK"  (BLUE)
   Outputs: "proceed" | "ask the user to clarify" | "decline"
   Draw a clearly visible BYPASS ARROW from the clarify/decline outputs
   straight down to Stage 7, skipping stages 5 and 6.
   Caption on that arrow: "no data is touched"

FROM STAGE 4 "proceed", SPLIT INTO TWO PARALLEL BRANCHES:

  LEFT BRANCH — "INTERNAL ANALYSIS" (BLUE background panel):
     "Certified analysis template" --> "Template scope check"
     "Open-ended question"  --> "Language model drafts a query plan" [PURPLE]
                            --> "Plan validator" [BLUE]
                            --> "Does this plan answer the question asked?" [BLUE]
     Both paths merge into:
        "Plan compiled into a read-only database query"
        "Query executed (read-only, row-count and sanity limits enforced)"

  RIGHT BRANCH — "EXTERNAL WEB CONTEXT" — DRAW WITH DASHED BORDERS
     and a badge reading "OFF BY DEFAULT":
     "Search planner" [PURPLE] --> "Web search" --> "Relevance filter" [BLUE]
     --> "Extract only text spans that literally exist on the page" [PURPLE]
     --> "Admission control" [BLUE]
     Badge on the branch: "web results can never become a computed fact"

STAGE 6 — "EVIDENCE STORE" — both branches MERGE here:
   Box contents: "Every number gets a record: id, origin, unit, source field,
                  dataset version, retrieval provenance"
   Plus a second box: "Does the evidence cover what was asked?"
   CRITICAL LABEL on the merge arrows:
   "Internal facts and web context are never combined inside one statement"

STAGE 7 — "WRITE THE ANSWER" — two side-by-side boxes:
   "Fixed template" [BLUE]  and  "Language model writing from a guarded packet" [PURPLE]
   Caption: "The model receives a COPY. The original evidence can never be edited."

STAGE 8 — "CHECK EVERY NUMBER"  (BLUE)
   Draw a LOOP-BACK ARROW to Stage 7 labelled "first failure: rewrite"
   and a second output labelled "second failure: fall back to the fixed template"

STAGE 9 — "FINAL CHECK BEFORE RELEASE"  (BLUE)
   fail --> RED box "Answer withheld"
   pass --> "Answer delivered with its sources"

MANDATORY LEGEND (draw it):
   PURPLE = language model — proposes, never decides
   BLUE   = deterministic code — decides
   RED    = refusal / withheld
   DASHED = disabled by default

THREE MISTAKES YOU MUST NOT MAKE:
1. The language model appears at EXACTLY four places: Stage 1, the query-plan
   draft in the left branch, the two web boxes in the right branch, and Stage 7.
   Every other box is deterministic code. Do not colour anything else purple.
2. No arrow may run from the web branch into the query compiler or the database.
   The two sources meet only at Stage 6, and stay in separate sections.
3. Do not omit the Stage 8 loop-back arrow, and do not omit the Stage 4 bypass.
````

---

## Slide 3 — Inverting the usual design

| | Typical "ask your database" assistant | This system |
|---|---|---|
| The model produces | database query text | a **typed plan**, not query text |
| What runs | whatever string the model wrote | a query the compiler built and validated |
| Who decides to answer | the model | **deterministic rules** |
| Hallucination control | an instruction in the prompt | a number with no record **cannot be printed** |
| When uncertain | keeps guessing | declines, and says which business variable is missing |

> **The model proposes. The code decides.** Every model output passes a
> deterministic validator before it is allowed to influence anything.

---

## Slide 4 — Turning unlimited language into a finite, checkable space

The code never tries to understand the sentence. It converts it, at exactly one
boundary, into symbols drawn from closed lists.

```
"What were total units sold in Vietnam across the whole data window?"
                              ↓  one boundary only
  question type   = aggregate analysis     ← 1 of 22
  measure         = units sold             ← 1 of 83
  market          = Vietnam
  operations      = filter, aggregate      ← from 12 permitted operations
```

| Dimension | Size of the closed list |
|---|---:|
| Business concepts the system will discuss | **83** |
| Question types it recognises | **22** |
| Query operations it can perform | **12** |

Past that boundary there is no natural language left — only set arithmetic. This
is why the system is checkable, and why a question falling *outside* the lists is
declined rather than guessed at.

---

## Slide 5 — Three independent checks 🎨

**On-slide text:** Three different questions, three separate components. Most
systems have the first and, sometimes, the third.

````text
DRAWING BRIEF — SLIDE 5 "THREE INDEPENDENT CHECKS"

Draw THREE GATES IN SERIES along a left-to-right track. Not a Venn diagram,
not three separate cards — it must read as three consecutive gates that an
answer has to pass through ALL of.

GATE 1 — "MAY WE ANSWER THIS AT ALL?"
   Checks: Is the business variable present in the dataset? Are two currencies
           being compared? Is required information missing from the question?
   Example refusals: "no cost data, so profit cannot be computed",
                     "Vietnamese dong and Indonesian rupiah are not comparable"

GATE 2 — "IS THIS ANSWERING THE QUESTION THAT WAS ASKED?"
   MARK THIS GATE PROMINENTLY AS "THE LAYER MOST SYSTEMS DO NOT HAVE"
   Checks: Does the plan actually compute the measure that was requested?
           Has it been silently swapped for a different measure?
           Were extra conditions in the question quietly dropped?

GATE 3 — "IS EVERY NUMBER BACKED BY A RECORD?"
   Checks: scans every number in the written answer; each one must match a
           stored evidence value; every citation must resolve

BELOW the three gates, draw a RED HORIZONTAL WARNING BAND that spans
GATE 1 and GATE 3 but is LEFT OPEN / EMPTY beneath GATE 2, labelled:

   "Question: how much bigger is the discount in Indonesia than in Vietnam?
    Answer:   there are 474 listings in Indonesia.
    Gate 1 passed. Gate 3 passed. The answer was still wrong.
    Nothing caught it, because the middle gate did not exist."

Draw an arrow from that empty section pointing up to Gate 2, labelled
"this gate was built to close that gap".

MUST NOT: merge the gates; draw them in parallel; place Gate 2 before Gate 1.
The order is fixed: permission, then relevance, then evidence.
````

---

## Slide 6 — How "did we answer the right question?" is decided

The check is **set arithmetic**, not comprehension:

```
requested by the question  = { units sold }
computed by the plan       = { listing count, market, date }

requested − computed ≠ empty   →   requested measure was dropped   →   ask the user to clarify
```

| Case | Before this layer | After |
|---|---|---|
| Discount comparison across two markets | answered · "474 listings" · all checks passed | declined — two currencies are not comparable |
| Total units sold across the data window | answered · "668 listings" · all checks passed | declined — the requested measure was never computed |

The check runs at **three points**: before execution against the plan, after
execution against the evidence, and after writing against the final text. It is
fully deterministic — correctness is never delegated to a second language model
acting as judge.

---

## Slide 7 — Every number carries a passport 🎨

**On-slide text:** A number without a record does not exist. This is a mechanical
constraint, not prompt guidance.

````text
DRAWING BRIEF — SLIDE 7 "THE EVIDENCE CHAIN"

Draw a four-tier vertical chain, plus one upward verification arrow.
Use the real values below EXACTLY as written — do not alter any digit.

TIER 1 — SOURCE DATA (grey box)
  "Governed snapshot table      dataset version 27de9bff184f4f89"

TIER 2 — EVIDENCE RECORD (green box, show every field on its own line)
  record id      : ev:cb535f1a33f9:0002
  measure        : estimated recent revenue
  value          : 298219517806.0
  unit           : VND
  origin         : internal governed dataset
  source field   : estimated_recent_revenue
  dataset version: 27de9bff184f4f89

TIER 3 — STATEMENT BINDING (blue box)
  statement id   : cl:0002
  type           : monetary
  value          : 298219517806.0
  bound to record: ev:cb535f1a33f9:0002
  bound to field : value

TIER 4 — DELIVERED ANSWER (white box, quote it literally)
  "...for a total of 298219517806 VND [ev:cb535f1a33f9:0002]."

Between TIER 4 and TIER 2 draw a CURVED ARROW GOING UPWARD, labelled:
  "Every number in the finished answer is scanned and must match a stored
   value, with tolerance set by how many digits were displayed"

To the RIGHT, a separate RED box:
  "A number with no matching record --> flagged as unsupported --> answer withheld"
  small line beneath: "Real incident: a hand-written figure placed in a refusal
  message -- which carries no evidence -- was correctly flagged as unsupported
  and dropped a benchmark from 1.00 to 0.77. The checker was right."

To the LEFT, an ORANGE box:
  "Origin separates two worlds:
     internal governed data -- may be computed with
     web context           -- descriptive only, never computed with
   Mixing them inside one statement is rejected automatically."

MUST NOT: connect the answer directly to the source table; drop the statement
binding tier; draw the verification arrow pointing downward -- it is a
backward check.
````

---

## Slide 8 — Why the model is not allowed to write database queries 🎨

**On-slide text:** The typed query plan is the most connected component in the
entire system (134 links) — and the only thing that can become a database query.

````text
DRAWING BRIEF — SLIDE 8 "THE CONTROLLED QUERY PATH"

Draw TWO parallel horizontal tracks for contrast.
Top track is struck through in red (rejected approach). Bottom track is real.

TRACK A (top, STRIKE THROUGH ENTIRELY IN RED, label "NOT USED"):
  "Question" -> "Language model" -> "Database query text" -> "Database"
  caption underneath: "whatever the model writes is what runs --
                       there is no point at which it can be checked"

TRACK B (bottom, the real path, one box per step):
  1. "Question"
  2. "Language model drafts a typed plan"  [PURPLE]
     note: "a structured object with a fixed shape -- not query text"
  3. "Plan validator"  [BLUE]
     note: "every concept must exist in the approved list of 83 ·
            table joins · level of detail · duplicate handling · units"
  4. "Does this plan answer the question asked?"  [BLUE]
  5. "Compiler"  [BLUE]
     note: "builds the query itself · read-only operations only ·
            12 permitted operations · internal data source locked"
  6. "Executor"  [BLUE]
     note: "read-only database · no external access · configuration locked ·
            expected row count enforced · result-size guard before running ·
            plan invariants checked after"
  7. "Result becomes evidence"

From steps 3 and 4, draw a BRANCH DOWN to an ORANGE box:
  "fails -> one bounded repair attempt -> still fails -> question declined"

Footer note: "The language model never touches query text. It proposes a
structure the compiler is free to reject."

MUST NOT: connect the language model directly to the compiler or the database
(it must pass the validator); swap the order of validator and compiler;
omit the repair branch.
````

---

## Slide 9 — Blocking invented answers at the generation step, not after

The system does not merely validate the model's reply — it makes an invalid reply
**impossible to produce**.

The list of question types the system accepts is compiled into the schema the
model must generate against. A type outside that list is not *rejected later*; it
is **unrepresentable**, one token at a time.

Two engineering details that matter:

- The vocabulary is **derived from the live registry**, never hand-copied. A
  second copy drifts the moment a capability is added — and that drift shows up
  as the model appearing to "invent" something that is in fact perfectly valid.
- **That already happened once.** Three question types were reported as invented;
  they were later added as real capabilities. The lesson is recorded in the code
  itself so it cannot be relearned the hard way.

**Two levels of evidence, stated separately:**

- *Structural, verifiable offline:* the accepted list is now compiled into the
  schema for **both** supported model providers — 22 permitted values each. An
  invalid type is no longer merely detectable; it cannot be generated.
- *Observed against a live provider:* **0% out-of-list replies**, but on a single
  run of **15 questions**. That is a sanity check, not a statistical claim, and
  the deck does not present it as one.

**Where this sits in the roadmap.** This is one step of a six-step programme. The
remaining steps are blocked on something engineering cannot supply: a set of
questions labelled by hand, independently, by two people, on the *hard*
free-form questions rather than the tidy ones. Until that exists, any accuracy
comparison between the model and the rules would be measured on a benchmark that
was written alongside the rules — and would therefore be measuring the rules.

---

## Slide 10 — Declining is a feature, and it is specific

| Refusal | What the user is told |
|---|---|
| Profit requested | no cost, platform fee or shipping data exists, so profit cannot be computed |
| Two currencies compared | Vietnamese dong and Indonesian rupiah are not the same unit; each market is reported separately |
| Ambiguous product | two candidates are equally likely — the system asks which one, and is forbidden from picking the best-selling |
| Condition outside a certified template | the requested condition is outside the comparison that has been validated |

Every refusal carries **four parts**: which variable is missing · what the data
does cover · what *can* still be answered · a concrete alternative question.

One subtle rule: refusal messages must contain **no digits**. A refusal carries no
evidence, so any number inside it would be an unbacked claim. Coverage is
described in words instead.

> **Cost asymmetry:** a declined question costs one follow-up. A confident wrong
> answer costs a business decision.

---

## Slide 11 — How new capability is allowed to go live 🎨

**On-slide text:** Topic routing · context budgeting · question decomposition ·
sub-question planning — all built, all running in observation mode, and **not one
delivered answer has changed.**

````text
DRAWING BRIEF — SLIDE 11 "OBSERVE, MEASURE, THEN ENABLE"

Draw a horizontal 4-stage timeline with a LOCKED GATE between stage 3 and 4.

STAGE 1 "BUILT"        : component complete, covered by tests

STAGE 2 "OBSERVING"    : runs on real user traffic, records its verdict,
                         DOES NOT change any answer
                         measured: "3-6 milliseconds ·
                                    every concept the real plan needed was present"
                         locked by test: "answers are byte-identical whether
                                          observation is on or off"

STAGE 3 "SCORECARD"    : 5 of 5 automatic checks pass
                           questions correctly scoped   35.6% -> 72.3%
                           questions matching nothing   30.0% ->  4.8%
                           over-broad routing                    0%
                           all 8 subject areas reachable
                           every one of the 83 concepts owned exactly once

[LOCKED GATE -- draw a large RED PADLOCK blocking the track]
   above the padlock: "NOT ENABLED"
   below the padlock: "6 further measures deliberately left unscored --
                       they require an independent reviewer, not the system's
                       own opinion of itself"
   pull-quote in italics: "Scoring your own routing with your own routing and
                           calling the result recall makes the gate meaningless."

STAGE 4 "ENABLED"      : draw GREYED OUT / faded, label "awaiting sign-off"

Footer: "A component nobody calls is a component nobody measures. Observation
mode buys real measurements without betting a single answer on them."

MUST NOT: draw stage 4 as complete; omit the padlock; change any figure.
````

---

## Slide 12 — How the system proves itself

| Mechanism | What it prevents |
|---|---|
| **Independent recomputation** — figures recalculated straight from source files by code forbidden from importing the product (enforced by an automated scan) | the system grading its own homework |
| **Meaning-preserving rewrites** — each rewrite must carry a written proof it preserves meaning; changing language, market, date or currency is banned outright | tests that look strict but assert nothing |
| **Deliberate sabotage tests** — corrupted plans must be caught | a validator that approves everything |
| **Recorded model replies** — the replay key includes provider, model, model revision, sampling settings, prompt version, context fingerprint and dataset version | mistaking "the recording replays consistently" for "the model is stable" |
| **Punctuation robustness** — every question run in 4 formatting variants | a parser that learned document formatting instead of meaning |

Independent recomputation has already **overturned six claims** carried in earlier
test documentation. Example: a figure quoted as "874 products in Vietnam" is
actually 874 raw rows spanning **two countries and three days**; Vietnam has 255
distinct products.

---

## Slide 13 — Measured state, including what is not finished

```
Automated test suite                      804 passed, 1 skipped
Boundary-condition suite (9 × 3 runs)     1.00
External-context suite                    12 / 12, no network access
Citation accuracy, all suites             1.00 recall, 1.00 precision
Component graph                           3,972 components · 8,272 dependencies
                                          zero circular dependencies
```

Every figure above is measured in the **deterministic-only configuration**, with
no model provider attached. That is deliberate: it is the configuration whose
results are reproducible run to run. The model-assisted path is reported
separately on slide 9 and is not folded into these numbers.

**Open, and stated by the system itself:**

- The main 60-question suite currently scores **0.65**, not 1.00. All 21 failures
  share **one** cause: when the system asks which product was meant, it echoes the
  candidate names back — and those names contain digits (`"... Cream 30 Gr"`).
  The number checker treats those digits as unbacked claims. It is a false alarm
  from our own safety layer, not a wrong answer. It is not yet fixed, and we did
  not weaken the checker to make the number look better.
- Topic routing remains **disabled**; six of its measures require an independent
  reviewer and are deliberately left unscored.
- Live web search is **off** by default and has not been signed off.
- Five items are waiting on human judgement, not engineering: two data-quality
  rules, a scoring-weight review, a claim-boundary review, and a pricing anomaly
  policy.

> Seven silent defects were found this cycle by **running** the system, not by
> reading it — three of them were inside the measuring tools themselves. Two rules
> came out of it: **verify behaviour, not structure**, and **when the harness
> reports something strange, suspect the harness first.**
