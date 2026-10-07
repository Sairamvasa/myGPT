import os
import tempfile

import rag


def test_user_text_rag_contains_rich_metadata(monkeypatch):
    class FakeStore:
        def __init__(self):
            self.documents = []

        def add_documents(self, documents):
            self.documents.extend(documents)

    fake_store = FakeStore()
    rag.vector_stores.pop(1, None)
    rag.project_vector_stores.pop(rag._project_key(42), None)

    monkeypatch.setattr(rag, "_load_user_state", lambda user_id: True)
    monkeypatch.setattr(rag, "_persist_user_state", lambda user_id: None)
    monkeypatch.setattr(rag, "get_embeddings", lambda: object())

    class FakeFAISS:
        @staticmethod
        def from_documents(documents, embeddings):
            fake_store.documents.extend(documents)
            return fake_store

    monkeypatch.setattr(rag, "FAISS", FakeFAISS)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        delete=False,
    ) as f:
        f.write("def hello():\n    return 'hello world'\n")
        path = f.name

    try:
        count = rag.process_text_file(
            path,
            user_id=1,
            source_filename="hello.py",
        )

        assert count >= 1

        metadata = fake_store.documents[0].metadata

        assert metadata["source"] == "hello.py"
        assert metadata["file_type"] == "code"
        assert metadata["user_id"] == 1
        assert metadata["scope"] == "user"
        assert metadata["chunk_index"] == 0
        assert metadata["chunk_id"].startswith("hello.py:")
    finally:
        os.unlink(path)


def test_project_text_rag_contains_project_metadata(monkeypatch):
    class FakeStore:
        def __init__(self):
            self.documents = []

        def add_documents(self, documents):
            self.documents.extend(documents)

    fake_store = FakeStore()

    monkeypatch.setattr(rag, "_load_project_state", lambda project_id: True)
    monkeypatch.setattr(rag, "_persist_project_state", lambda project_id: None)
    monkeypatch.setattr(rag, "get_embeddings", lambda: object())

    class FakeFAISS:
        @staticmethod
        def from_documents(documents, embeddings):
            fake_store.documents.extend(documents)
            return fake_store

    monkeypatch.setattr(rag, "FAISS", FakeFAISS)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        delete=False,
    ) as f:
        f.write("Project documentation content.")
        path = f.name

    try:
        count = rag.process_text_file(
            path,
            user_id=1,
            source_filename="project.txt",
            project_id=42,
        )

        assert count >= 1

        metadata = fake_store.documents[0].metadata

        assert metadata["source"] == "project.txt"
        assert metadata["file_type"] == "text"
        assert metadata["project_id"] == 42
        assert metadata["scope"] == "project"
        assert metadata["chunk_index"] == 0
        assert metadata["chunk_id"].startswith("project.txt:")
    finally:
        os.unlink(path)


def test_file_type_detection():
    assert rag._get_file_type("main.py") == "code"
    assert rag._get_file_type("index.html") == "web"
    assert rag._get_file_type("data.json") == "data"
    assert rag._get_file_type("README.md") == "text"
    assert rag._get_file_type("document.pdf") == "pdf"
    assert rag._get_file_type("unknown.xyz") == "unknown"