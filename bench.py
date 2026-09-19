from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
from contextlib import redirect_stdout
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

from src import (
    Document,
    EmbeddingStore,
    FixedSizeChunker,
    KnowledgeBaseAgent,
    OpenAIEmbedder,
    RecursiveChunker,
    SentenceChunker,
    _mock_embed,
)


DATA_DIR = Path("data/library-borrowing")
CACHE_DIR = Path(".embedding-cache")
TOP_K = 3
CHUNK_SIZE = 500

# Personal strategy — Lê Hoàng Thiên Phú. Keep all other benchmark settings fixed.
PERSONAL_CHUNKER = FixedSizeChunker(chunk_size=CHUNK_SIZE, overlap=50)

# Shared benchmark set prepared by R2 (Đinh Văn Hùng).
BENCHMARKS = [
    {
        "query": "How many Short Loan items may be borrowed at once, and how long does each loan last?",
        "gold_answer": "Only two Short Loan items may be borrowed at once, and each Short Loan lasts 3 hours.",
        "expected_doc_id": "borrowing-limits",
        "metadata_filter": None,
        "gold_phrases": ["two Short Loan", "3 hours"],
    },
    {
        "query": "Under what conditions may a General Collection item be kept for up to 365 days?",
        "gold_answer": (
            "There must be no recall, the borrower's enrolment or membership must remain current, "
            "and the borrowing record must have no fines or blocks."
        ),
        "expected_doc_id": "borrowing-terms",
        "metadata_filter": None,
        "gold_phrases": ["recalled", "enrolment or membership", "no fines or blocks"],
    },
    {
        "query": "How do I request a digital copy of a journal article or book chapter?",
        "gold_answer": (
            "Sign in to the catalogue, select the journal and location, choose Request a digital copy, "
            "complete the form and copyright acknowledgement, and submit the request."
        ),
        "expected_doc_id": "requesting-items",
        "metadata_filter": None,
        "gold_phrases": ["Request a digital copy", "copyright acknowledgement"],
    },
    {
        "query": "Where must a Short Loan item be returned?",
        "gold_answer": "A Short Loan item must be returned to the location from which it was borrowed.",
        "expected_doc_id": "returning-items",
        "metadata_filter": None,
        "gold_phrases": ["Short Loan item", "location from which it was borrowed"],
    },
    {
        "query": "How many items can I borrow through Resource Sharing in a calendar year, and who is eligible?",
        "gold_answer": (
            "Postgraduate and honours students are eligible, and eligible students may borrow up to "
            "100 items from other institutions per calendar year."
        ),
        "expected_doc_id": "resource-sharing-students",
        "metadata_filter": {"audience": "student"},
        "gold_phrases": ["postgraduate students and honours students", "up to 100 items"],
    },
]


class HeadingChunker:
    """R3 strategy: preserve Markdown sections and repeat headings on fallbacks."""

    def __init__(self, chunk_size: int = CHUNK_SIZE) -> None:
        self.chunk_size = chunk_size
        self._recursive = RecursiveChunker(chunk_size=chunk_size)

    def chunk(self, text: str) -> list[str]:
        if not text.strip():
            return []
        starts = [match.start() for match in re.finditer(r"(?m)^##\s+", text)]
        if not starts:
            return self._recursive.chunk(text)

        boundaries = [0, *starts, len(text)]
        sections = [
            text[boundaries[index] : boundaries[index + 1]].strip()
            for index in range(len(boundaries) - 1)
        ]
        chunks: list[str] = []
        for section in sections:
            if not section:
                continue
            if len(section) <= self.chunk_size:
                chunks.append(section)
                continue
            lines = section.splitlines()
            heading = lines[0].strip() if lines and lines[0].startswith("##") else ""
            body = "\n".join(lines[1:]).strip() if heading else section
            for piece in self._recursive.chunk(body):
                chunks.append(f"{heading}\n{piece}".strip() if heading else piece)
        return chunks


class CachedEmbedder:
    """Persistent SHA-256 embedding cache with OpenAI batch preloading."""

    def __init__(self, base: Callable[[str], list[float]], namespace: str) -> None:
        self.base = base
        safe_namespace = re.sub(r"[^a-zA-Z0-9_.-]+", "-", namespace)
        self.path = CACHE_DIR / f"{safe_namespace}.json"
        self._backend_name = f"{getattr(base, '_backend_name', base.__class__.__name__)} + sha256 cache"
        self.cache: dict[str, list[float]] = {}
        if self.path.is_file():
            self.cache = json.loads(self.path.read_text(encoding="utf-8"))

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [float(value) / norm for value in vector]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.cache), encoding="utf-8")
        temporary.replace(self.path)

    def __call__(self, text: str) -> list[float]:
        key = self._key(text)
        if key not in self.cache:
            self.cache[key] = self._normalize(self.base(text))
            self._save()
        return list(self.cache[key])

    def preload(self, texts: list[str]) -> None:
        unique_missing: list[str] = []
        seen: set[str] = set()
        for text in texts:
            key = self._key(text)
            if text and key not in self.cache and key not in seen:
                unique_missing.append(text)
                seen.add(key)
        if not unique_missing:
            return

        if isinstance(self.base, OpenAIEmbedder):
            for start in range(0, len(unique_missing), 256):
                batch = unique_missing[start : start + 256]
                response = self.base.client.embeddings.create(model=self.base.model_name, input=batch)
                for text, item in zip(batch, response.data):
                    self.cache[self._key(text)] = self._normalize(list(item.embedding))
        else:
            for text in unique_missing:
                self.cache[self._key(text)] = self._normalize(self.base(text))
        self._save()


class OpenAIAnswerer:
    """Callable adapter for KnowledgeBaseAgent using the Responses API."""

    def __init__(self, model: str) -> None:
        from openai import OpenAI

        self.client = OpenAI()
        self.model = model

    def __call__(self, prompt: str) -> str:
        response = self.client.responses.create(model=self.model, input=prompt)
        return response.output_text


def read_markdown(path: Path) -> tuple[dict[str, str], str]:
    """Return simple frontmatter metadata and the Markdown body separately."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text.strip()
    parts = text.split("---", maxsplit=2)
    if len(parts) != 3:
        return {}, text.strip()

    metadata: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", maxsplit=1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata, parts[2].strip()


def load_chunk_documents(chunker) -> tuple[list[Document], int]:
    documents: list[Document] = []
    source_count = 0
    for path in sorted(DATA_DIR.glob("*.md")):
        source_count += 1
        frontmatter, content = read_markdown(path)
        for index, chunk in enumerate(chunker.chunk(content)):
            documents.append(
                Document(
                    id=f"{path.stem}#{index}",
                    content=chunk,
                    metadata={
                        **frontmatter,
                        "doc_id": path.stem,
                        "chunk_index": index,
                        "source_file": str(path),
                    },
                )
            )
    return documents, source_count


def build_embedder(provider: str) -> CachedEmbedder:
    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is missing. Add it to .env before the measured run.")
        model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        return CachedEmbedder(OpenAIEmbedder(model_name=model), f"openai-{model}")
    if provider == "mock":
        return CachedEmbedder(_mock_embed, "mock-64")
    raise ValueError("bench.py supports only 'openai' and 'mock'; local embedding is intentionally disabled.")


def strategy_map() -> dict[str, object]:
    return {
        "fixed_size": PERSONAL_CHUNKER,
        "by_sentences": SentenceChunker(max_sentences_per_chunk=3),
        "recursive": RecursiveChunker(chunk_size=CHUNK_SIZE),
        "heading": HeadingChunker(chunk_size=CHUNK_SIZE),
    }


def contains_gold(result: dict, benchmark: dict) -> bool:
    content = result["content"].lower()
    return all(phrase.lower() in content for phrase in benchmark["gold_phrases"])


def first_rank(results: list[dict], predicate: Callable[[dict], bool]) -> int | None:
    for rank, result in enumerate(results, start=1):
        if predicate(result):
            return rank
    return None


def retrieval_points(content_rank: int | None) -> int:
    if content_rank == 1:
        return 2
    if content_rank in {2, 3}:
        return 1
    return 0


def search(store: EmbeddingStore, benchmark: dict, metadata_filter: dict | None) -> list[dict]:
    return store.search_with_filter(
        benchmark["query"],
        top_k=TOP_K,
        metadata_filter=metadata_filter,
    )


def print_top_three(results: list[dict], benchmark: dict) -> None:
    for rank, result in enumerate(results, start=1):
        metadata = result["metadata"]
        print(
            f"  {rank}. score={result['score']:.4f} doc_id={metadata.get('doc_id')} "
            f"chunk_id={result['id']} content_match={contains_gold(result, benchmark)}"
        )
        print(f"     {result['content'][:180].replace(chr(10), ' ')}...")


def filtered_agent(
    documents: list[Document],
    embedder: CachedEmbedder,
    llm_fn: Callable[[str], str],
    metadata_filter: dict | None,
) -> KnowledgeBaseAgent:
    candidates = documents
    if metadata_filter:
        candidates = [
            document
            for document in documents
            if all(document.metadata.get(key) == value for key, value in metadata_filter.items())
        ]
    store = EmbeddingStore(collection_name="agent_candidates", embedding_fn=embedder)
    store.add_documents(candidates)
    return KnowledgeBaseAgent(store, llm_fn)


def run_personal_benchmark(
    documents: list[Document],
    embedder: CachedEmbedder,
    llm_fn: Callable[[str], str] | None,
) -> list[dict]:
    store = EmbeddingStore(collection_name="phu_fixed_size", embedding_fn=embedder)
    store.add_documents(documents)
    evaluations: list[dict] = []

    print("\n=== Personal benchmark: Lê Hoàng Thiên Phú ===")
    print("Strategy: FixedSizeChunker(chunk_size=500, overlap=50)")
    print(f"Loaded {len(documents)} chunks from {len(list(DATA_DIR.glob('*.md')))} documents")

    for number, benchmark in enumerate(BENCHMARKS, start=1):
        results = search(store, benchmark, benchmark["metadata_filter"])
        doc_rank = first_rank(
            results,
            lambda result: result["metadata"].get("doc_id") == benchmark["expected_doc_id"],
        )
        content_rank = first_rank(results, lambda result: contains_gold(result, benchmark))
        answer = "[agent skipped for structural dry-run]"
        answer_marker_match = False
        if llm_fn is not None:
            agent = filtered_agent(documents, embedder, llm_fn, benchmark["metadata_filter"])
            answer = agent.answer(benchmark["query"], top_k=TOP_K)
            answer_marker_match = all(
                phrase.lower() in answer.lower() for phrase in benchmark["gold_phrases"]
            )

        print(f"\nQ{number}: {benchmark['query']}")
        print(f"Gold: {benchmark['gold_answer']}")
        print(
            f"Filter: {benchmark['metadata_filter'] or 'none'} | doc_rank={doc_rank} "
            f"content_rank={content_rank} retrieval_points={retrieval_points(content_rank)}/2"
        )
        print_top_three(results, benchmark)
        print(f"Agent marker match: {answer_marker_match}")
        print(f"Agent answer: {answer}")
        evaluations.append(
            {
                "number": number,
                "benchmark": benchmark,
                "results": results,
                "doc_rank": doc_rank,
                "content_rank": content_rank,
                "answer": answer,
                "answer_marker_match": answer_marker_match,
            }
        )
    print(
        "\nPersonal retrieval total: "
        f"{sum(retrieval_points(item['content_rank']) for item in evaluations)}/10"
    )
    return evaluations


def run_filter_ab(
    documents_by_strategy: dict[str, list[Document]],
    embedder: CachedEmbedder,
) -> None:
    benchmark = BENCHMARKS[4]
    print("\n=== Required Q5 metadata-filter A/B across strategies ===")
    for name, documents in documents_by_strategy.items():
        store = EmbeddingStore(collection_name=f"ab_{name}", embedding_fn=embedder)
        store.add_documents(documents)
        filtered = search(store, benchmark, benchmark["metadata_filter"])
        unfiltered = search(store, benchmark, None)
        filtered_ids = [result["id"] for result in filtered]
        unfiltered_ids = [result["id"] for result in unfiltered]

        print(f"\n[{name}] WITH filter {benchmark['metadata_filter']}")
        print_top_three(filtered, benchmark)
        print(f"[{name}] WITHOUT filter")
        print_top_three(unfiltered, benchmark)
        print(
            f"A/B ranks: content_with={first_rank(filtered, lambda r: contains_gold(r, benchmark))}, "
            f"content_without={first_rank(unfiltered, lambda r: contains_gold(r, benchmark))}, "
            f"identical_top3={filtered_ids == unfiltered_ids}"
        )


def print_chunk_stats(documents_by_strategy: dict[str, list[Document]]) -> None:
    print("=== Chunk statistics (embedding-independent) ===")
    for name, documents in documents_by_strategy.items():
        average = sum(len(document.content) for document in documents) / len(documents) if documents else 0.0
        print(f"{name}: count={len(documents)} avg_length={average:.1f}")


def print_failure_analysis(evaluations: list[dict]) -> None:
    print("\n=== Failure analysis candidates ===")
    failures = [
        item for item in evaluations if item["doc_rank"] is not None and item["content_rank"] is None
    ]
    if not failures:
        failures = [item for item in evaluations if item["content_rank"] not in {1}]
    for item in failures[:2]:
        benchmark = item["benchmark"]
        print(f"Q{item['number']} failed: {benchmark['query']}")
        print(
            "Cause: the gold document may be retrieved while the answer-bearing chunk is absent or ranked too low; "
            "topic similarity alone does not guarantee answer density."
        )
        print(
            "Proposed fix: use semantic embeddings, retain meaningful boundaries/headings, and add targeted metadata "
            "or overlap where the answer crosses a chunk boundary."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Day 7 retrieval benchmark.")
    parser.add_argument("--provider", choices=("mock", "openai"), help="Overrides EMBEDDING_PROVIDER")
    parser.add_argument("--skip-agent", action="store_true", help="Skip LLM answers during a structural dry-run")
    parser.add_argument("--output", type=Path, help="Write the complete console output to this UTF-8 file")
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    load_dotenv(override=False)
    provider = (args.provider or os.getenv("EMBEDDING_PROVIDER", "mock")).strip().lower()
    embedder = build_embedder(provider)
    strategies = strategy_map()
    documents_by_strategy = {
        name: load_chunk_documents(chunker)[0] for name, chunker in strategies.items()
    }

    all_texts = [benchmark["query"] for benchmark in BENCHMARKS]
    for documents in documents_by_strategy.values():
        all_texts.extend(document.content for document in documents)
    embedder.preload(all_texts)

    llm_fn: Callable[[str], str] | None = None
    if not args.skip_agent:
        if provider != "openai":
            raise RuntimeError("Use --skip-agent for mock dry-runs; measured agent answers require OpenAI.")
        response_model = os.getenv("OPENAI_RESPONSE_MODEL", "gpt-4.1-mini")
        llm_fn = OpenAIAnswerer(response_model)

    print(f"Embedding backend: {embedder._backend_name}")
    print_chunk_stats(documents_by_strategy)
    evaluations = run_personal_benchmark(documents_by_strategy["fixed_size"], embedder, llm_fn)
    run_filter_ab(documents_by_strategy, embedder)
    print_failure_analysis(evaluations)
    return 0


def main() -> int:
    args = parse_args()
    capture = io.StringIO()
    with redirect_stdout(capture):
        exit_code = run(args)
    output = capture.getvalue()
    print(output, end="")
    if args.output:
        args.output.write_text(output, encoding="utf-8")
        print(f"Saved benchmark output to {args.output}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
