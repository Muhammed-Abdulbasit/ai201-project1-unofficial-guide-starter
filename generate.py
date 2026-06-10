"""
generate.py — Milestone 5: Grounded Generation + Interface

Ties the pipeline together: retrieve the most relevant review chunks for a
question (Milestone 4), feed ONLY those chunks to an LLM as context, and produce
an answer that is grounded in the reviews and accompanied by a source list.

Grounding is enforced two ways:
  1. Structural — the model is given only the retrieved chunks as context, each
     numbered [1]..[k]. Optionally, chunks beyond a cosine-distance cutoff are
     dropped so clearly-irrelevant reviews never reach the model.
  2. Instructional — a system prompt that forbids outside knowledge, requires a
     bracketed [n] citation for every claim, and mandates an explicit "not enough
     information" response when the reviews don't cover the question.

Usage:
    python generate.py                      # interactive Q&A loop
    python generate.py --eval               # run the 5 evaluation-plan questions
    python generate.py --query "..."        # answer a single question
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from groq import Groq

from embed import (
    EVAL_QUERIES,
    TOP_K,
    get_collection,
    get_embedding_function,
    retrieve,
)

# --- Configuration ----------------------------------------------------------
LLM_MODEL = "llama-3.3-70b-versatile"   # Groq-hosted; current as of build
# Cosine distance above which a retrieved chunk is treated as irrelevant and
# dropped before it reaches the model. ~1.0 == unrelated; reviews for the right
# professor cluster well below this. Keeps off-topic context out of the prompt.
RELEVANCE_CUTOFF = 0.85

SYSTEM_PROMPT = (
    "You are The Unofficial Guide, an assistant that answers questions about "
    "Computer Science professors at Georgia State University using ONLY the "
    "student reviews provided in the context.\n\n"
    "Rules:\n"
    "1. Base every statement strictly on the provided reviews. Do NOT use any "
    "outside or prior knowledge.\n"
    "2. Support each claim with a bracketed citation matching the numbered "
    "sources, e.g. [1] or [2][3].\n"
    "3. If the reviews do not contain enough information to answer the question, "
    "respond exactly with: \"I don't have enough information in the reviews to "
    "answer that.\"\n"
    "4. Reviews are subjective student opinions and may conflict. When they "
    "disagree, summarize the range of opinions rather than picking one.\n"
    "5. Be concise and specific. Do not invent professor names, courses, or facts "
    "not present in the context."
)


def get_groq_client():
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
    key = os.getenv("GROQ_API_KEY", "")
    if not key or key == "your_key_here":
        sys.exit("GROQ_API_KEY is not set. Copy .env.example to .env and add your key "
                 "(get one free at https://console.groq.com).")
    return Groq(api_key=key)


def format_context(hits):
    """Render retrieved chunks as a numbered context block for the prompt."""
    blocks = []
    for i, hit in enumerate(hits, start=1):
        m = hit["metadata"]
        header = (f"[{i}] Professor {m.get('professor')} | "
                  f"Course {m.get('course') or 'n/a'} | Date {m.get('date') or 'n/a'}")
        blocks.append(f"{header}\n{hit['text']}")
    return "\n\n".join(blocks)


def answer_query(query, collection=None, top_k=TOP_K, client=None):
    """Retrieve, ground, and generate. Returns a dict with answer + sources."""
    if collection is None:
        collection = get_collection(get_embedding_function())
    if client is None:
        client = get_groq_client()

    hits = retrieve(query, collection=collection, top_k=top_k)
    # Structural grounding: drop clearly-irrelevant chunks.
    relevant = [h for h in hits if h["distance"] <= RELEVANCE_CUTOFF]

    if not relevant:
        return {
            "query": query,
            "answer": "I don't have enough information in the reviews to answer that.",
            "sources": [],
            "all_hits": hits,
        }

    context = format_context(relevant)
    user_message = (
        f"Question: {query}\n\n"
        f"Context (student reviews):\n{context}\n\n"
        "Answer the question using only the reviews above, citing sources by their "
        "bracketed number."
    )

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,   # low — we want faithful summarization, not creativity
        max_tokens=600,
    )
    answer = response.choices[0].message.content.strip()

    return {
        "query": query,
        "answer": answer,
        "sources": relevant,
        "all_hits": hits,
    }


def print_result(result):
    """Print an answer followed by its numbered source list."""
    print("\nAnswer:")
    print(result["answer"])
    if result["sources"]:
        print("\nSources:")
        for i, hit in enumerate(result["sources"], start=1):
            m = hit["metadata"]
            print(f"  [{i}] {m.get('professor')} — {m.get('course') or 'n/a'} "
                  f"({m.get('date') or 'n/a'}) — {m.get('source_url')} "
                  f"(distance {hit['distance']:.3f})")


def run_eval(collection, client, top_k=TOP_K):
    for n, query in enumerate(EVAL_QUERIES, start=1):
        print("\n" + "=" * 78)
        print(f"EVAL QUESTION {n}: {query}")
        print("=" * 78)
        result = answer_query(query, collection=collection, top_k=top_k, client=client)
        print_result(result)


def interactive_loop(collection, client, top_k=TOP_K):
    print("The Unofficial Guide — GSU CS professor reviews")
    print("Ask a question (or type 'quit' to exit).\n")
    while True:
        try:
            query = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            break
        result = answer_query(query, collection=collection, top_k=top_k, client=client)
        print_result(result)
        print()


def main():
    parser = argparse.ArgumentParser(description="Grounded Q&A over professor reviews.")
    parser.add_argument("--eval", action="store_true",
                        help="run the 5 evaluation-plan questions")
    parser.add_argument("--query", type=str, default=None,
                        help="answer a single question and exit")
    parser.add_argument("--top-k", type=int, default=TOP_K,
                        help=f"chunks to retrieve per query (default {TOP_K})")
    args = parser.parse_args()

    collection = get_collection(get_embedding_function())
    if collection.count() == 0:
        sys.exit("Vector store is empty. Run `python embed.py --rebuild` first.")
    client = get_groq_client()

    if args.eval:
        run_eval(collection, client, top_k=args.top_k)
    elif args.query:
        print_result(answer_query(args.query, collection=collection,
                                  top_k=args.top_k, client=client))
    else:
        interactive_loop(collection, client, top_k=args.top_k)


if __name__ == "__main__":
    main()
