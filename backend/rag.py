import os

from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

# Per-user vector databases: {user_id: FAISS store}
vector_stores = {}

# Per-user uploaded file names: {user_id: set of filenames}
uploaded_files_map = {}

# Lazy load embedding model to prevent startup crashes.
embeddings = None

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


def process_pdf(pdf_path, user_id):
    global vector_stores
    global uploaded_files_map

    reader = PdfReader(pdf_path)

    filename = os.path.basename(pdf_path)

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

    print(
        f"PDF processed: {filename} "
        f"({len(documents)} chunks)"
    )

    print(
        "Available PDFs:",
        uploaded_files_map[user_id]
    )

    return len(documents)


def process_text_file(file_path, user_id):
    """Process any plain-text / code file (py, html, js, ts, css, json, csv, md, txt, etc.)"""
    global vector_stores
    global uploaded_files_map

    filename = os.path.basename(file_path)

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
        all_docs = vector_store.similarity_search(question, k=fetch_k)
    except Exception as error:
        print(f"RAG search error: {error}")
        return None

    # Group results by source filename
    docs_by_file: dict[str, list] = {}
    for doc in all_docs:
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