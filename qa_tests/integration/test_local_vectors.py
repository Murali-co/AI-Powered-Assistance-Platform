"""Real local embeddings + disposable Chroma; does not import the app or Neon."""
import chromadb
from chromadb.config import Settings

from app.vector_db.embedder import embed_batch, embed_text


def test_real_local_embeddings_index_query_and_tenant_filter(tmp_path):
    from qa_tests.guards import require_real_inference
    require_real_inference()
    documents = ['Python backend engineering', 'React frontend engineering']
    vectors = embed_batch(documents)
    assert len(vectors) == 2 and all(len(vector) == 384 for vector in vectors)
    client = chromadb.PersistentClient(path=str(tmp_path / 'chroma'), settings=Settings(anonymized_telemetry=False))
    collection = client.create_collection('local_embedding_audit', metadata={'hnsw:space': 'cosine'})
    collection.add(ids=['a-python', 'b-react'], documents=documents, embeddings=vectors,
                   metadatas=[{'user_id': 'a'}, {'user_id': 'b'}])
    result = collection.query(query_embeddings=[embed_text(documents[0])], n_results=1)
    assert result['ids'] == [['a-python']]
    assert result['distances'][0][0] < 0.001
    isolated = collection.query(query_embeddings=[embed_text(documents[0])], where={'user_id': 'b'}, n_results=1)
    assert isolated['ids'] == [['b-react']]
