import os

from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

# Main vector database
vector_store = None

# Uploaded PDF names
uploaded_files = set()

# Load local embedding model only once
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)


def process_pdf(pdf_path):
    global vector_store
    global uploaded_files

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

    # First PDF
    if vector_store is None:
        vector_store = FAISS.from_documents(
            documents,
            embeddings
        )

    # Second, third, fourth... PDF
    else:
        vector_store.add_documents(
            documents
        )

    uploaded_files.add(filename)

    print(
        f"PDF processed: {filename} "
        f"({len(documents)} chunks)"
    )

    print(
        "Available PDFs:",
        uploaded_files
    )

    return len(documents)


def search_pdf(
    question,
    chunks_per_pdf=3
):
    global vector_store
    global uploaded_files

    if vector_store is None:
        return None

    if not uploaded_files:
        return None

    context_parts = []

    # Tell Gemini which documents exist
    context_parts.append(
        "UPLOADED DOCUMENTS:\n" +
        "\n".join(
            f"- {filename}"
            for filename in sorted(uploaded_files)
        )
    )

    # Search EACH PDF separately
    for filename in sorted(uploaded_files):

        try:
            documents = (
                vector_store.similarity_search(
                    question,
                    k=chunks_per_pdf,
                    filter={
                        "source": filename
                    }
                )
            )

        except Exception as error:
            print(
                f"Search error for "
                f"{filename}: {error}"
            )
            continue

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

    return "\n\n---\n\n".join(
        context_parts
    )