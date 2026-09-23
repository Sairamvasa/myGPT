import os
import json
from pathlib import Path

from pypdf import PdfReader
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings


BASE_DIR = Path(__file__).resolve().parent
RAG_STORAGE_DIR = Path(
    os.getenv("RAG_STORAGE_DIR", str(BASE_DIR / "rag_indexes"))
)

# Relevance threshold for FAISS L2 distance scores.
# FAISS uses Euclidean distance (L2) where LOWER = more relevant.
# Observed score distribution:
#   Relevant queries (calculator.py):   1.4584 – 1.5744
#   Unrelated queries:                   1.8368 – 1.9164
# A threshold of 1.70 sits safely in the gap and rejects weak matches.
RAG_RELEVANCE_THRESHOLD = float(
    os.getenv("RAG_RELEVANCE_THRESHOLD", "1.70")
)


class RecursiveCharacterTextSplitter:
    def __init__(self, chunk_size=1500, chunk_overlap=200, separators=None):
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._separators = separators or ["\n\n", "\n", " ", ""]

    def split_text(self, text: str) -> list[str]:
        return self._split_text(text, self._separators)

    def _split_text(self, text: str, separators: list[str]) -> list[str]:
        separator = separators[-1]
        new_separators = []
        for i, s in enumerate(separators):
            if not s:
                separator = s
                break
            if s in text:
                separator = s
                new_separators = separators[i + 1:]
                break

        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)
        splits = [s for s in splits if s]

        final_chunks = []
        good_splits = []
        for s in splits:
            if len(s) < self._chunk_size:
                good_splits.append(s)
            else:
                if good_splits:
                    merged = self._merge_splits(good_splits, separator)
                    final_chunks.extend(merged)
                    good_splits = []
                if not new_separators:
                    final_chunks.append(s)
                else:
                    other_info = self._split_text(s, new_separators)
                    final_chunks.extend(other_info)
        if good_splits:
            merged = self._merge_splits(good_splits, separator)
            final_chunks.extend(merged)
        return final_chunks

    def _merge_splits(self, splits: list[str], separator: str) -> list[str]:
        separator_len = len(separator)
        docs = []
        current_doc = []
        total = 0
        for d in splits:
            len_ = len(d)
            if (
                total + len_ + (separator_len if len(current_doc) > 0 else 0)
                > self._chunk_size
            ):
                if len(current_doc) > 0:
                    doc = separator.join(current_doc)
                    if doc:
                        docs.append(doc)
                    while (
                        total > self._chunk_overlap
                        or (
                            total + len_ + (separator_len if len(current_doc) > 0 else 0)
                            > self._chunk_size
                            and total > 0
                        )
                    ):
                        total -= len(current_doc[0]) + (
                            separator_len if len(current_doc) > 1 else 0
                        )
                        current_doc = current_doc[1:]
            current_doc.append(d)
            total += len_ + (separator_len if len(current_doc) > 1 else 0)
        if current_doc:
            doc = separator.join(current_doc)
            if doc:
                docs.append(doc)
        return docs

# Per-user vector databases: {user_id: FAISS store}
vector_stores = {}

# Per-user uploaded file names: {user_id: set of filenames}
uploaded_files_map = {}

# Lazy load embedding model to prevent startup crashes.
embeddings = None


def _user_index_dir(user_id):
    return RAG_STORAGE_DIR / str(user_id)


def _manifest_path(user_id):
    return _user_index_dir(user_id) / "files.json"


def _persist_user_state(user_id):
    vector_store = vector_stores.get(user_id)
    if vector_store is None:
        return

    index_dir = _user_index_dir(user_id)
    index_dir.mkdir(parents=True, exist_ok=True)
    vector_store.save_local(str(index_dir))

    with _manifest_path(user_id).open("w", encoding="utf-8") as manifest:
        json.dump(sorted(uploaded_files_map.get(user_id, set())), manifest)


def _load_user_state(user_id):
    if user_id in vector_stores:
        return True

    index_dir = _user_index_dir(user_id)
    if not (index_dir / "index.faiss").exists():
        return False

    try:
        vector_stores[user_id] = FAISS.load_local(
            str(index_dir),
            get_embeddings(),
            allow_dangerous_deserialization=True,
        )

        manifest_path = _manifest_path(user_id)
        if manifest_path.exists():
            with manifest_path.open("r", encoding="utf-8") as manifest:
                uploaded_files_map[user_id] = set(json.load(manifest))
        else:
            uploaded_files_map[user_id] = {
                document.metadata.get("source", "")
                for document in vector_stores[user_id].docstore._dict.values()
                if document.metadata.get("source")
            }

        return True
    except Exception as error:
        print(f"Unable to load persisted RAG index for user {user_id}: {error}")
        vector_stores.pop(user_id, None)
        uploaded_files_map.pop(user_id, None)
        return False

def get_embeddings():
    global embeddings
    if embeddings is None:
        # Remove local_files_only=True on Railway so it can download
        is_railway = "RAILWAY_ENVIRONMENT" in os.environ
        model_kwargs = {} if is_railway else {"local_files_only": True}
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs=model_kwargs
        )
    return embeddings


def process_pdf(pdf_path, user_id, source_filename=None):
    global vector_stores
    global uploaded_files_map

    _load_user_state(user_id)

    reader = PdfReader(pdf_path)

    filename = source_filename or os.path.basename(pdf_path)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=200
    )

    documents = []

    # Read every page
    for page_number, page in enumerate(
        reader.pages,
        start=1
    ):
        page_text = page.extract_text()

        if not page_text:
            continue

        chunks = splitter.split_text(page_text)

        for chunk in chunks:
            documents.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "source": filename,
                        "page": page_number
                    }
                )
            )

    if not documents:
        raise ValueError(
            f"No readable text found in {filename}"
        )

    # First PDF for this user
    if user_id not in vector_stores:
        vector_stores[user_id] = FAISS.from_documents(
            documents,
            get_embeddings()
        )

    # Second, third, fourth... PDF for this user
    else:
        vector_stores[user_id].add_documents(
            documents
        )

    if user_id not in uploaded_files_map:
        uploaded_files_map[user_id] = set()

    uploaded_files_map[user_id].add(filename)
    _persist_user_state(user_id)

    print(
        f"PDF processed: {filename} "
        f"({len(documents)} chunks)"
    )

    print(
        "Available PDFs:",
        uploaded_files_map[user_id]
    )

    return len(documents)


def process_text_file(file_path, user_id, source_filename=None):
    """Process any plain-text / code file (py, html, js, ts, css, json, csv, md, txt, etc.)"""
    global vector_stores
    global uploaded_files_map

    _load_user_state(user_id)

    filename = source_filename or os.path.basename(file_path)

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        raw_text = f.read()

    if not raw_text.strip():
        raise ValueError(f"No readable text found in {filename}")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=200
    )

    chunks = splitter.split_text(raw_text)

    documents = [
        Document(
            page_content=chunk,
            metadata={
                "source": filename,
                "page": i + 1
            }
        )
        for i, chunk in enumerate(chunks)
    ]

    if not documents:
        raise ValueError(f"Could not split {filename} into chunks")

    if user_id not in vector_stores:
        vector_stores[user_id] = FAISS.from_documents(documents, get_embeddings())
    else:
        vector_stores[user_id].add_documents(documents)

    if user_id not in uploaded_files_map:
        uploaded_files_map[user_id] = set()

    uploaded_files_map[user_id].add(filename)
    _persist_user_state(user_id)

    print(f"Text/code file processed: {filename} ({len(documents)} chunks)")
    print("All uploaded files:", uploaded_files_map[user_id])

    return len(documents)


def search_pdf(
    question,
    user_id,
    chunks_per_pdf=3
):
    global vector_stores
    global uploaded_files_map

    _load_user_state(user_id)

    if user_id not in vector_stores:
        return None

    if user_id not in uploaded_files_map or not uploaded_files_map[user_id]:
        return None

    vector_store = vector_stores[user_id]
    uploaded_files = uploaded_files_map[user_id]

    context_parts = []

    # Tell Gemini which documents exist
    context_parts.append(
        "UPLOADED DOCUMENTS:\n" +
        "\n".join(
            f"- {filename}"
            for filename in sorted(uploaded_files)
        )
    )

    # Fetch a broad pool of results without any filter (FAISS in-memory
    # does not reliably support metadata filtering via the filter= kwarg).
    # We then manually filter by source filename in Python.
    total_needed = chunks_per_pdf * len(uploaded_files)
    # Fetch at least 50 candidates so we have enough to distribute across files
    fetch_k = max(total_needed * 4, 50)

    try:
        # Use similarity_search_with_score to get L2 distance scores.
        # FAISS uses Euclidean distance: LOWER = more relevant.
        all_docs_with_scores = vector_store.similarity_search_with_score(
            question, k=fetch_k
        )
    except Exception as error:
        print(f"RAG search error: {error}")
        return None

    # Apply relevance threshold: reject chunks whose L2 distance exceeds
    # the configured threshold. This prevents weak/unrelated retrieval
    # from being treated as authoritative RAG context.
    filtered_docs = [
        (doc, score) for doc, score in all_docs_with_scores
        if score <= RAG_RELEVANCE_THRESHOLD
    ]

    if not filtered_docs:
        # No chunks passed the relevance threshold — return None so the
        # agent falls back to normal chat instead of using weak context.
        return None

    # Group results by source filename
    docs_by_file: dict[str, list] = {}
    for doc, score in filtered_docs:
        source = doc.metadata.get("source", "")
        if source not in docs_by_file:
            docs_by_file[source] = []
        if len(docs_by_file[source]) < chunks_per_pdf:
            docs_by_file[source].append(doc)

    for filename in sorted(uploaded_files):

        documents = docs_by_file.get(filename, [])

        if not documents:
            continue

        context_parts.append(
            f"\n===== DOCUMENT: "
            f"{filename} =====\n"
        )

        for doc in documents:

            page = doc.metadata.get(
                "page",
                "Unknown"
            )

            context_parts.append(
                f"""
SOURCE: {filename}
PAGE: {page}

{doc.page_content}
"""
            )

    if len(context_parts) <= 1:
        # Only the header, no actual content found
        return None

    return "\n\n---\n\n".join(
        context_parts
    )
