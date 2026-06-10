"""
embed.py — Milestone 4: Embedding + Vector Store + Retrieval

Loads the chunks produced by ingest.py, embeds them with all-MiniLM-L6-v2
(sentence-transformers), and stores them in a persistent ChromaDB collection
together with their source metadata. Also exposes a retrieval function and a
small CLI that runs the evaluation-plan queries and prints the returned chunks
with their distance scores.

Usage:
    python embed.py              # build the index (if needed) and run test queries
    python embed.py --rebuild    # wipe and rebuild the index from chunks.json
"""

import argparse
import json
import sys
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

# --- Configuration ----------------------------------------------------------
EMBEDDING_MODEL = "all-MiniLM-L6-v2"   # planning.md > Retrieval Approach
TOP_K = 5                               # planning.md > Retrieval Approach
COLLECTION_NAME = "professor_reviews"

ROOT = Path(__file__).parent
CHUNKS_FILE = ROOT / "chunks.json"
CHROMA_DIR = ROOT / "chroma_db"          # persistent on-disk vector store

# Evaluation-plan queries (planning.md > Evaluation Plan).
EVAL_QUERIES = [
    "What do students say about Professor Weeks's teaching style?",
    "What do students say about Professor Alser's lecture quality?",
    "What do students say about Professor Iraji's pop quizzes?",
    "What do students say about Professor Sadasivuni's course organization?",
    "What do students say about Professor Kuzmin's extra credit opportunities?",
]


def get_embedding_function():
    """Return a Chroma-compatible embedding function backed by all-MiniLM-L6-v2.

    Using one embedding function for both indexing and querying guarantees the
    document and query vectors live in the same space.
    """
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )


def get_collection(embedding_fn, reset=False):
    """Open (or create) the persistent ChromaDB collection."""
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass  # collection didn't exist yet
    # cosine distance suits normalized sentence-transformer embeddings
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )


def load_chunks():
    if not CHUNKS_FILE.exists():
        sys.exit(f"chunks.json not found at {CHUNKS_FILE}. Run `python ingest.py` first.")
    return json.loads(CHUNKS_FILE.read_text(encoding="utf-8"))


def _clean_metadata(meta):
    """ChromaDB only accepts str/int/float/bool metadata values (no None)."""
    cleaned = {}
    for key, value in meta.items():
        if value is None:
            cleaned[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            cleaned[key] = value
        else:
            cleaned[key] = str(value)
    return cleaned


def build_index(reset=False):
    """Embed every chunk and store it in ChromaDB. Returns the collection."""
    chunks = load_chunks()
    embedding_fn = get_embedding_function()
    collection = get_collection(embedding_fn, reset=reset)

    # If already populated and not rebuilding, skip the (slow) embedding pass.
    if not reset and collection.count() == len(chunks):
        print(f"Index already built: {collection.count()} chunks in "
              f"'{COLLECTION_NAME}'. Use --rebuild to recreate it.")
        return collection

    if reset:
        # ensure a clean slate even if count() differed
        collection = get_collection(embedding_fn, reset=True)

    print(f"Embedding {len(chunks)} chunks with {EMBEDDING_MODEL} ...")
    ids = [c["id"] for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [_clean_metadata(c["metadata"]) for c in chunks]

    # Add in batches so the embedding model isn't handed everything at once.
    batch_size = 128
    for start in range(0, len(chunks), batch_size):
        end = start + batch_size
        collection.add(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )
        print(f"  embedded {min(end, len(chunks))}/{len(chunks)}")

    print(f"Done. Collection '{COLLECTION_NAME}' now holds {collection.count()} chunks "
          f"(persisted at {CHROMA_DIR.name}/).")
    return collection


def retrieve(query, collection=None, top_k=TOP_K):
    """Return the top_k most relevant chunks for a query.

    Each result is a dict: {text, distance, metadata}. Lower distance = closer
    (cosine distance, so 0.0 is identical, ~1.0 is unrelated).
    """
    if collection is None:
        collection = get_collection(get_embedding_function())

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
    )

    hits = []
    for doc, dist, meta in zip(
        results["documents"][0],
        results["distances"][0],
        results["metadatas"][0],
    ):
        hits.append({"text": doc, "distance": dist, "metadata": meta})
    return hits


def run_eval_queries(collection, queries=EVAL_QUERIES, top_k=TOP_K):
    """Run each query through retrieval and print chunks + distance scores."""
    for q_num, query in enumerate(queries, start=1):
        print("\n" + "=" * 78)
        print(f"QUERY {q_num}: {query}")
        print("=" * 78)
        hits = retrieve(query, collection=collection, top_k=top_k)
        for rank, hit in enumerate(hits, start=1):
            m = hit["metadata"]
            print(f"\n  [{rank}] distance={hit['distance']:.4f}  "
                  f"professor={m.get('professor')}  course={m.get('course') or 'n/a'}  "
                  f"date={m.get('date') or 'n/a'}")
            print(f"      source: {m.get('source_url')}")
            text = hit["text"]
            snippet = text if len(text) <= 320 else text[:317] + "..."
            print(f"      {snippet}")


def main():
    parser = argparse.ArgumentParser(description="Embed chunks and test retrieval.")
    parser.add_argument("--rebuild", action="store_true",
                        help="wipe and rebuild the vector store from chunks.json")
    parser.add_argument("--top-k", type=int, default=TOP_K,
                        help=f"chunks to retrieve per query (default {TOP_K})")
    parser.add_argument("--query", type=str, default=None,
                        help="run a single ad-hoc query instead of the eval set")
    args = parser.parse_args()

    collection = build_index(reset=args.rebuild)

    if args.query:
        run_eval_queries(collection, queries=[args.query], top_k=args.top_k)
    else:
        run_eval_queries(collection, top_k=args.top_k)


if __name__ == "__main__":
    main()
