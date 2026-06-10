"""
app.py — Milestone 5 interface: a browser chat UI for The Unofficial Guide.

Wraps the grounded-generation pipeline (generate.answer_query) in a Gradio chat
interface so anyone can use it without instructions: type a question about a GSU
CS professor, get a grounded answer with a clickable source list. The five
evaluation-plan questions are pre-loaded as one-click examples.

Usage:
    python app.py        # then open the printed http://127.0.0.1:7860 URL
"""

import sys

import gradio as gr

from embed import EVAL_QUERIES, get_collection, get_embedding_function
from generate import answer_query, get_groq_client

# Load the vector store and LLM client once at startup.
_collection = get_collection(get_embedding_function())
if _collection.count() == 0:
    sys.exit("Vector store is empty. Run `python embed.py --rebuild` first.")
_client = get_groq_client()


def _format_sources(sources):
    """Render the retrieved sources as a markdown list with clickable links."""
    if not sources:
        return ""
    lines = ["\n\n**Sources**"]
    for i, hit in enumerate(sources, start=1):
        m = hit["metadata"]
        prof = m.get("professor", "Unknown")
        course = m.get("course") or "n/a"
        date = m.get("date") or "n/a"
        url = m.get("source_url", "")
        dist = hit["distance"]
        lines.append(
            f"{i}. [{prof} — {course} ({date})]({url})  ·  relevance distance {dist:.3f}"
        )
    return "\n".join(lines)


def respond(message, history):
    """Chat callback: retrieve + ground + generate, return answer + sources."""
    if not message or not message.strip():
        return "Please ask a question about a GSU Computer Science professor."
    result = answer_query(message.strip(), collection=_collection, client=_client)
    return result["answer"] + _format_sources(result["sources"])


DESCRIPTION = (
    "Ask about a **Georgia State University Computer Science professor** and get an "
    "answer grounded only in real student reviews from RateMyProfessors, with the "
    "sources it used. The assistant will not answer beyond what the reviews say.\n\n"
    "*Try one of the example questions below, or ask your own "
    "(e.g. \"Is Professor Henry's grading fair?\").*"
)

demo = gr.ChatInterface(
    fn=respond,
    title="🎓 The Unofficial Guide — GSU CS Professor Reviews",
    description=DESCRIPTION,
    examples=EVAL_QUERIES,
    cache_examples=False,
    theme=gr.themes.Soft(),
)

if __name__ == "__main__":
    demo.launch()
