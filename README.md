# The Unofficial Guide — Project 1

> A retrieval-augmented question-answering system over student reviews of
> Computer Science professors at Georgia State University (sourced from
> RateMyProfessors). Ask a natural-language question; the system retrieves the
> most relevant reviews and produces a grounded, cited answer.

**Pipeline:** `ingest.py` (ingestion + chunking) → `embed.py` (embedding + vector
store + retrieval) → `generate.py` (grounded generation + interface).

### Running it

```bash
pip install -r requirements.txt
cp .env.example .env          # add your free Groq API key (https://console.groq.com)

python ingest.py              # fetch reviews, clean, chunk -> chunks.json + documents/
python embed.py --rebuild     # embed chunks into ChromaDB + run retrieval test
python generate.py            # interactive Q&A  (--eval runs the 5 eval questions)
```

---

## Domain

Student reviews of CS professors at Georgia State University.

---

## Document Sources

10 RateMyProfessors professor pages for GSU Computer Science faculty. The review
text is not exposed as a static document — it is loaded by the site's React/Relay
front end, and the page HTML server-renders only the first 5 reviews per
professor. So `ingest.py` calls RateMyProfessors' public GraphQL endpoint to
retrieve the **complete** review set for each professor. URLs are in `sources.txt`.

| #  | Source           | Type                                 | URL                                                |
|----|------------------|--------------------------------------|----------------------------------------------------|
| 1  | RateMyProfessors | Prof. reviews — Abdullah Bal         | https://www.ratemyprofessors.com/professor/2942443 |
| 2  | RateMyProfessors | Prof. reviews — Louis Henry          | https://www.ratemyprofessors.com/professor/458011  |
| 3  | RateMyProfessors | Prof. reviews — Mohammed Alser       | https://www.ratemyprofessors.com/professor/3126576 |
| 4  | RateMyProfessors | Prof. reviews — Kiril Kuzmin         | https://www.ratemyprofessors.com/professor/2782285 |
| 5  | RateMyProfessors | Prof. reviews — Armin Iraji          | https://www.ratemyprofessors.com/professor/2910619 |
| 6  | RateMyProfessors | Prof. reviews — Lan Gao              | https://www.ratemyprofessors.com/professor/3075860 |
| 7  | RateMyProfessors | Prof. reviews — Yuan Long            | https://www.ratemyprofessors.com/professor/2056921 |
| 8  | RateMyProfessors | Prof. reviews — Michael Weeks        | https://www.ratemyprofessors.com/professor/418488  |
| 9  | RateMyProfessors | Prof. reviews — Tushara Sadasivuni   | https://www.ratemyprofessors.com/professor/2317655 |
| 10 | RateMyProfessors | Prof. reviews — Alexander Zelikovsky | https://www.ratemyprofessors.com/professor/1311577 |

Across the 10 professors the pipeline ingested **522 reviews**.

---

## Chunking Strategy

**Chunk size:** 550 characters

**Overlap:** 50 characters

**Why these choices fit your documents:**
A RateMyProfessors comment is capped at 350 characters, so a single review is the
natural atomic unit and should never be split mid-thought. I originally planned a
350-character chunk, but I prepend an **attribution header** to each review —
`Professor <Name> | <Department> | Course <Code>.` — so the professor's name
travels into the embedded text (critical for grounding: a chunk read in isolation
still identifies whose review it is), and I append the review's rating tags /
received grade. With the header + tags, the longest assembled review is ~508
characters, so I raised the window to **550** to keep **one review = one chunk**
with no mid-sentence splits. The 50-character overlap is retained as a safeguard
for any document longer than the window (none in the current corpus trigger it).

**Preprocessing before chunking:** Reviews are fetched as structured JSON via
GraphQL (no HTML body to strip), then cleaned — HTML entities unescaped
(`&amp;` → `&`, `&#39;` → `'`) and all whitespace/newline runs collapsed to single
spaces — before the header/tags are assembled.

**Final chunk count:** 522 chunks (1:1 with reviews; chunk sizes 63–508 chars,
avg ~359).

---

## Embedding Model

**Model used:** `all-MiniLM-L6-v2` via `sentence-transformers`, stored in a
persistent ChromaDB collection using cosine distance. The same embedding function
is used for indexing and querying so document and query vectors share one space.
Retrieval uses **top-k = 5**. I chose all-MiniLM-L6-v2 because it is small
(384-dim, ~80 MB), runs locally with no API cost, and is well-benchmarked for
general semantic retrieval — a good fit for short, informal review text.

**Production tradeoff reflection:**
If deployed for real users with cost no object, I would weigh a larger /
API-hosted model (e.g. OpenAI `text-embedding-3-large` or a domain-tuned model).
Benefits: better accuracy on slang, sarcasm, and domain phrasing ("yap sessions",
"curve") that MiniLM may embed weakly, plus a longer context window. Costs: higher
latency, per-call spend, and a network/data-privacy dependency (sending student
reviews to a third party). Because most queries name a specific professor and
MiniLM already routes to the right professor reliably, the upgrade would mainly
help the harder *facet* queries (see Failure Case Analysis).

---

## Grounded Generation

Generation uses Groq-hosted `llama-3.3-70b-versatile` at low temperature (0.2).
Grounding is enforced two ways:

**System prompt grounding instruction (the actual instruction given):**
> "...answer questions about GSU CS professors using ONLY the student reviews
> provided in the context. (1) Base every statement strictly on the provided
> reviews. Do NOT use any outside or prior knowledge. (2) Support each claim with a
> bracketed citation matching the numbered sources, e.g. [1] or [2][3]. (3) If the
> reviews do not contain enough information to answer, respond exactly with: 'I
> don't have enough information in the reviews to answer that.' (4) Reviews are
> subjective and may conflict — summarize the range of opinions rather than picking
> one. (5) Be concise; do not invent professor names, courses, or facts not in the
> context."

Structural choices reinforce this: the model receives **only** the retrieved
chunks (never the full corpus or outside knowledge); each is presented as a
numbered source `[1]`..`[5]` carrying professor/course/date; and chunks beyond a
cosine-distance cutoff (0.85) are dropped before reaching the model. If nothing
survives the cutoff, the system returns "not enough information" without calling
the LLM. Verified: an out-of-corpus question ("Professor Einstein's physics
lectures and campus parking") correctly returned the refusal instead of
hallucinating.

**How source attribution is surfaced in the response:**
Each answer prints claims with inline `[n]` citations, followed by a **Sources**
list mapping every `[n]` to the professor, course, date, the original
RateMyProfessors URL, and the retrieval distance.

---

## Evaluation Report

Run with `python generate.py --eval`. Responses summarized below.

| # | Question | Expected answer | System response (summarized) | Retrieval quality | Response accuracy |
|---|----------|-----------------|------------------------------|-------------------|-------------------|
| 1 | What do students say about Professor Week's teaching style? | Doesn't provide slides and mostly uses the textbook | Teaching described as outdated, boring, off-topic "yap sessions", with one dissenting review; cited [1]–[5]. Did **not** surface the specific "no slides / use the textbook" point. | Relevant (all 5 chunks are Weeks) | Partially accurate |
| 2 | What do students say about Professor Alser's lecture quality? | Explains complex concepts well and makes them interesting | Lectures are clear, engaging, interesting and easy to follow; advanced topics made enjoyable; well-structured PPTs. Cited [1]–[5]. | Relevant | Accurate |
| 3 | What do students say about Professor Iraji's pop quizzes? | He gives them sometimes and they constitute 20% of the grade | States a pop quiz constituted **20% of the grade**; notes surprise/"pop-up" quizzes handed out at end of class. Cited [1]–[4]. | Relevant | Accurate |
| 4 | What do students say about Professor Sadasivuni's course organization? | Very disorganized and changes things last minute | Mixed-but-mostly-negative: "disorganized" course, low-value lectures, tests not matching slides; one positive outlier. Cited [1]–[5]. Captured "disorganized" but not "changes things last minute". | Relevant | Partially accurate |
| 5 | What do students say about Professor Kuzmin's extra credit opportunities? | Provides lots of extra credit points on exams | Correctly reports that tests had ~60 points of extra credit and were considered easy, and notes no other review mentions extra credit. Cited [4] only. | Partially relevant (only 1 of 5 chunks mentions extra credit) | Accurate |

**Summary:** 3/5 accurate (Alser, Iraji, Kuzmin), 2/5 partially accurate (Weeks,
Sadasivuni). Retrieval routed to the correct professor on **5/5** questions —
every returned chunk belonged to the right professor, which the in-chunk
attribution header clearly helps. The weaker results are *facet* misses: the right
professor is found, but the specific sub-topic detail isn't always in the top 5.

**Retrieval quality:** Relevant (4/5) / Partially relevant (1/5)
**Response accuracy:** Accurate (3/5) / Partially accurate (2/5)

---

## Failure Case Analysis

**Question that failed:**
What do students say about Professor Kuzmin's extra credit opportunities?

**What the system returned:**
A correct but thin answer: it reported that tests carried ~60 points of extra
credit and were considered easy, citing a single source [4], and noted that no
other review mentioned extra credit. The answer happened to be accurate, but it
rested on just one of the five retrieved chunks — a fragile result.

**Root cause (tied to a specific pipeline stage):**
This is a **retrieval-ranking** weakness. Four of the five chunks returned for the
query were genuinely about Kuzmin but praised him generally (caring,
knowledgeable, good lectures) rather than discussing extra credit; only one chunk
actually mentioned it, and it ranked 4th (distance 0.532). Because most Kuzmin
reviews are general praise, semantic similarity favored "great professor" chunks
over the rarer, more specific "extra credit" mention. With top-k = 5 the relevant
chunk was barely included; a smaller k, or a professor with more general reviews,
would have pushed it out of the context entirely and produced a "not enough
information" answer despite the fact existing in the corpus.

**What you would change to fix it:**
(a) Retrieve a larger candidate set and re-rank, or raise top-k for facet
questions; (b) add a keyword/BM25 hybrid retrieval step so a distinctive term like
"extra credit" isn't lost to pure semantic similarity; (c) optionally upgrade to a
stronger embedding model better at separating specific facets within
otherwise-similar reviews.

---

## Spec Reflection

**One way the spec helped you during implementation:**
Writing the Chunking Strategy in `planning.md` first forced me to reason about the
*structure* of my documents before coding. Because I had already established that
RMP reviews cap at 350 characters and should each stay whole, when implementation
revealed that my attribution header pushed reviews past 350, the fix was obvious
and principled — raise the window to 550 to preserve "one review = one chunk" —
rather than an arbitrary guess. The spec gave me a concrete invariant to design
against.

**One way your implementation diverged from the spec, and why:**
The spec specified a 350-character chunk size; the implementation uses 550. The
divergence came from a grounding need I hadn't fully accounted for in planning: to
attribute each chunk to the right professor I prepend a header and append rating
tags, which makes the assembled unit longer than the raw comment. Rather than
split reviews (which would harm retrieval), I enlarged the window so the invariant
held, and updated `planning.md` to record the new size and reasoning so spec and
code stay in sync.

---

## AI Usage

**Instance 1 — Ingestion + chunking**

- *What I gave the AI:* My `planning.md` (domain, the 10 RMP URLs, and the
  Chunking Strategy section with 350-char size / 50-char overlap) and the request
  to load the documents, clean them, and chunk them.
- *What it produced:* It first tested whether the RMP pages were loadable, found
  the review data was only partially server-rendered, and switched to RMP's public
  GraphQL API to fetch all reviews — producing `ingest.py` (a `sources.txt` loader,
  GraphQL fetch with pagination, `clean_text()`, and a sliding-window
  `chunk_text()`), plus per-professor raw documents and `chunks.json`.
- *What I changed or overrode:* It initially kept the 350-char size, which split
  ~62% of reviews once the attribution header was added. I directed it to raise the
  chunk size to keep reviews whole; after measuring the length distribution we
  settled on 550 characters (100% single-chunk).

**Instance 2 — Embedding, retrieval, and grounded generation**

- *What I gave the AI:* My Retrieval Approach section (all-MiniLM-L6-v2, top-k = 5)
  and the requirement that generation be grounded and output an answer plus a
  source list.
- *What it produced:* `embed.py` (ChromaDB persistence + a `retrieve()` function,
  tested against my eval queries with distance scores) and `generate.py` (a
  grounding system prompt, numbered-source context formatting, a distance cutoff,
  and a CLI interface), then ran all 5 eval questions end-to-end.
- *What I changed or overrode:* I verified grounding explicitly by testing an
  out-of-corpus question and confirming the system refused to answer rather than
  hallucinating, and I had the eval results recorded honestly — including the two
  partially-accurate facet misses and the fragile single-source Kuzmin answer —
  rather than presenting a suspiciously perfect score.
