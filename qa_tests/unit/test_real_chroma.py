"""Real isolated Chroma storage; supplied vectors, no embedding model or Neon."""
import chromadb
from chromadb.config import Settings


def test_chroma_persistence_retrieval_and_two_user_filter(tmp_path):
    path = str(tmp_path / "isolated-chroma")
    settings = Settings(anonymized_telemetry=False)
    client = chromadb.PersistentClient(path=path, settings=settings)
    collection = client.create_collection("audit_isolated", metadata={"hnsw:space": "cosine"})
    collection.add(
        ids=["user-a", "user-b"],
        documents=["Python experience", "Python experience"],
        embeddings=[[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        metadatas=[{"user_id": "a"}, {"user_id": "b"}],
    )
    reopened = chromadb.PersistentClient(path=path, settings=settings).get_collection("audit_isolated")
    assert reopened.count() == 2
    result = reopened.query(query_embeddings=[[1.0, 0.0, 0.0]], where={"user_id": "a"}, n_results=2)
    assert result["ids"] == [["user-a"]]
    assert result["distances"][0][0] == 0.0
    reopened.delete(where={"user_id": "a"})
    assert reopened.get()["ids"] == ["user-b"]
