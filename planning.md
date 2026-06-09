# Project 1 Planning: The Unofficial Guide

> Write this document before you write any pipeline code.
> Your spec and architecture diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Update the Retrieval Approach and Chunking Strategy sections if you change your approach during implementation.
> Update this file before starting any stretch features.

---

## Domain

<!-- What domain did you choose? Why is this knowledge valuable and hard to find through official channels? -->

I chose the domain Student reviews of CS professors at Georgia State University. This knowledge would be hard to find in a structured format, but is likely to be found in unstructured form on websites like RateMyProfessors. A system that can retrieve and summarize this information would be useful for students trying to choose classes or professors.

---

## Documents

<!-- List your specific sources: URLs, subreddit names, forum threads, or file descriptions.
     Aim for at least 10 sources that together cover different subtopics or perspectives within your domain. -->

| # | Source | Description | URL or location |
|---|--------|-------------|-----------------|
| 1 | ratemyprofessors.com | Student reviews of CS professors | https://www.ratemyprofessors.com/professor/2942443 |
| 2 | ratemyprofessors.com | Student reviews of CS professors | https://www.ratemyprofessors.com/professor/458011 |
| 3 | ratemyprofessors.com | Student reviews of CS professors | https://www.ratemyprofessors.com/professor/3126576 |
| 4 | ratemyprofessors.com | Student reviews of CS professors | https://www.ratemyprofessors.com/professor/2782285 |
| 5 | ratemyprofessors.com | Student reviews of CS professors | https://www.ratemyprofessors.com/professor/2910619 |
| 6 | ratemyprofessors.com | Student reviews of CS professors | https://www.ratemyprofessors.com/professor/3075860 |
| 7 | ratemyprofessors.com | Student reviews of CS professors | https://www.ratemyprofessors.com/professor/2056921 |
| 8 | ratemyprofessors.com | Student reviews of CS professors | https://www.ratemyprofessors.com/professor/418488 |
| 9 | ratemyprofessors.com | Student reviews of CS professors | https://www.ratemyprofessors.com/professor/2317655 |
| 10 | ratemyprofessors.com | Student reviews of CS professors | https://www.ratemyprofessors.com/professor/1311577 |

---

## Chunking Strategy

<!-- How will you split documents into chunks?
     State your chunk size (in tokens or characters), overlap size, and explain why those
     numbers fit the structure of your documents.
     A review-heavy corpus warrants different chunking than a long FAQ. -->

**Chunk size:**
350 characters
**Overlap:**
50 characters
**Reasoning:**
Reviews on RateMyProfessors are limited to 350 characters, so this chunk size ensures that each review is contained within a single chunk. The 50 character overlap allows for some context to be preserved between chunks without creating too much redundancy.
---

## Retrieval Approach

<!-- Which embedding model are you using (e.g., all-MiniLM-L6-v2 via sentence-transformers)?
     How many chunks will you retrieve per query (top-k)?
     If you were deploying this for real users and cost wasn't a constraint, what tradeoffs
     would you weigh in choosing a different embedding model — context length, multilingual
     support, accuracy on domain-specific text, latency? -->

**Embedding model:**
The embedding model I plan to use is all-MiniLM-L6-v2 via sentence-transformers. This model is a good balance of performance and cost, and has been shown to work well for a variety of retrieval tasks.
**Top-k:**
5
**Production tradeoff reflection:**
If cost weren't a constraint, I would consider using a more advanced embedding model with better performance on domain-specific text, but this would increase latency and computational requirements.
---

## Evaluation Plan

<!-- List your 5 test questions with their expected correct answers.
     Questions should be specific enough that you can judge whether the system's response
     is right or wrong. "What are good dining halls?" is too vague.
     "What do students say about wait times at [dining hall name] during lunch?" is testable. -->

| # | Question | Expected answer |
|---|----------|-----------------|
| 1 | What do students say about Professor Week's teaching style? | Doesn't provide slides and mostly uses the textbook |
| 2 | What do students say about Professor Alser's lecture quality? | Explains complex concepts well and makes them interesting |
| 3 | What do students say about Professor Iraji's pop quizzes? | He gives them sometimes and they constitue 20% of the grade |
| 4 | What do students say about Professor Sadasivuni's course organization? | Very disorganized and changes things last minute |
| 5 | What do students say about Professor Kuzmin's extra credit opportunities? | Provides lots of extra credit points on exams |

---

## Anticipated Challenges

<!-- What could go wrong? Name at least two specific risks with reasoning.
     Consider: noisy or inconsistent documents, missing source attribution, off-topic
     retrieval, chunks that split key information across boundaries. -->

1. Noisy or inconsistent documents: Student reviews may contain typos, grammatical errors, and/or subjective opinions that could affect the quality of the embedding and retrieval. Sometimes students will vent frustration, use sarcasm, or say something that contradicts what other students say about the same professor, which could lead to inaccurate or misleading responses from the system.

2. Missing source attribution: If the system doesn't properly attribute sources, users may not know where the information came from, reducing trust in the responses.

---

## Architecture

<!-- Draw a diagram of your pipeline showing the five stages:
     Document Ingestion → Chunking → Embedding + Vector Store → Retrieval → Generation
     Label each stage with the tool or library you're using.
     You can use ASCII art, a Mermaid diagram, or embed a sketch as an image.
     You'll use this diagram as context when prompting AI tools to implement each stage. -->


![alt text](<Document Ingestion to LLM-2026-06-09-204115-1.png>)

---

## AI Tool Plan

<!-- For each part of the pipeline below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, which requirements)
     - What you expect it to produce
     - How you'll verify the output matches your spec

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Chunking Strategy section and ask it to implement chunk_text()
     with my specified chunk size and overlap" is a plan. -->

**Milestone 3 — Ingestion and chunking:**

**Milestone 4 — Embedding and retrieval:**

**Milestone 5 — Generation and interface:**
