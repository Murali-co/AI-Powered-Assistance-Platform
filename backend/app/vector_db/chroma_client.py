import os
import logging
import threading
from typing import List, Dict, Any, Optional
import chromadb
from app.config import settings
from app.vector_db.embedder import embed_text

logger = logging.getLogger(__name__)


class ChromaDBClient:
    _client = None
    _lock = threading.Lock()
    _init_error: Optional[str] = None

    @classmethod
    def get_client(cls):
        """
        Thread-safe getter for the persistent ChromaDB client.
        Preserves existing data and never deletes or resets the persistent store on failure.
        """
        if cls._client is None:
            with cls._lock:
                if cls._client is None:
                    os.environ["ANONYMIZED_TELEMETRY"] = "False"
                    os.environ["CHROMA_ANONYMIZED_TELEMETRY"] = "False"

                    try:
                        from chromadb.config import Settings as ChromaSettings
                        chroma_settings = ChromaSettings(
                            anonymized_telemetry=False,
                            chroma_product_telemetry_impl="app.vector_db.telemetry.NoOpTelemetry",
                            chroma_telemetry_impl="app.vector_db.telemetry.NoOpTelemetry"
                        )
                        cls._client = chromadb.PersistentClient(
                            path=settings.CHROMA_PATH,
                            settings=chroma_settings
                        )
                        # Verify database health non-destructively
                        collections = cls._client.list_collections()
                        for col in collections:
                            col.count()
                        cls._init_error = None
                    except Exception as e:
                        cls._client = None
                        cls._init_error = (
                            f"ChromaDB initialization failure at '{settings.CHROMA_PATH}': {type(e).__name__}: {str(e)}. "
                            "Persistent vector database files were kept intact. "
                            "Do not wipe or modify persistent storage without explicit user authorization."
                        )
                        logger.error(cls._init_error)
                        raise RuntimeError(cls._init_error) from e

        return cls._client

    @classmethod
    def check_health(cls) -> Dict[str, Any]:
        """
        Lightweight health inspection for ChromaDB.
        Returns detailed status without modifying storage.
        """
        try:
            client = cls.get_client()
            collections = client.list_collections()
            collection_names = [c.name for c in collections]
            return {
                "healthy": True,
                "path": settings.CHROMA_PATH,
                "collections": collection_names,
                "error": None
            }
        except Exception as e:
            return {
                "healthy": False,
                "path": settings.CHROMA_PATH,
                "collections": [],
                "error": cls._init_error or str(e)
            }

    @classmethod
    def get_collection(cls, name: str):
        """
        Idempotent collection getter that avoids triggering internal ChromaDB
        'Collection X is not created' warning logs by checking existing collections first.
        """
        client = cls.get_client()
        try:
            existing = {c.name for c in client.list_collections()}
            if name in existing:
                return client.get_collection(name=name)
            return client.create_collection(name=name)
        except Exception:
            return client.get_or_create_collection(name=name)

    @classmethod
    def _format_query_results(cls, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        outputs = []
        if results and results.get("ids") and len(results["ids"]) > 0 and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                outputs.append({
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i] if "documents" in results and results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if "metadatas" in results and results["metadatas"] else {},
                    "distance": results["distances"][0][i] if "distances" in results and results["distances"] else None
                })
        return outputs

    @classmethod
    def query_profile(
        cls, 
        user_id: int, 
        query_text: str, 
        n_results: int = 5, 
        where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic query over user resume sections, isolated by user_id.
        """
        collection = cls.get_collection("user_profiles")
        total_count = collection.count()
        if total_count == 0:
            return []
        effective_n_results = min(n_results, total_count)
        query_emb = embed_text(query_text)
        
        user_filter = {"user_id": {"$eq": str(user_id)}}
        section_filter = {"type": {"$ne": "full"}}
        
        combined_filters = [user_filter, section_filter]
        if where:
            combined_filters.append(where)
            
        combined_where = {"$and": combined_filters}

        results = collection.query(
            query_embeddings=[query_emb],
            n_results=effective_n_results,
            where=combined_where
        )
        return cls._format_query_results(results)

    @classmethod
    def query_jobs(
        cls, 
        query_text: str, 
        n_results: int = 5, 
        where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic query over scraped job descriptions.
        """
        collection = cls.get_collection("job_listings")
        total_count = collection.count()
        if total_count == 0:
            return []
        effective_n_results = min(n_results, total_count)
        query_emb = embed_text(query_text)
        
        results = collection.query(
            query_embeddings=[query_emb],
            n_results=effective_n_results,
            where=where
        )
        return cls._format_query_results(results)

    @classmethod
    def query_applications(
        cls, 
        user_id: int, 
        query_text: str, 
        n_results: int = 5, 
        where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic query over stored applications/proposals.
        """
        collection = cls.get_collection("applications")
        total_count = collection.count()
        if total_count == 0:
            return []
        effective_n_results = min(n_results, total_count)
        query_emb = embed_text(query_text)

        user_filter = {"user_id": {"$eq": str(user_id)}}
        if where:
            combined_where = {"$and": [user_filter, where]}
        else:
            combined_where = user_filter

        results = collection.query(
            query_embeddings=[query_emb],
            n_results=effective_n_results,
            where=combined_where
        )
        return cls._format_query_results(results)

    @classmethod
    def query_skills(
        cls, 
        query_text: str, 
        n_results: int = 5, 
        where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic query over taxonomy skills.
        """
        collection = cls.get_collection("skills")
        total_count = collection.count()
        if total_count == 0:
            return []
        effective_n_results = min(n_results, total_count)
        query_emb = embed_text(query_text)

        results = collection.query(
            query_embeddings=[query_emb],
            n_results=effective_n_results,
            where=where
        )
        return cls._format_query_results(results)

    @classmethod
    def seed_skills_if_empty(cls):
        """
        Seeds the skills collection from extractor's taxonomy safely.
        """
        try:
            collection = cls.get_collection("skills")
            if collection.count() == 0:
                from app.resume.extractor import SKILL_TAXONOMY
                from app.vector_db.embedder import embed_batch
                
                unique_skills = sorted(list(set(SKILL_TAXONOMY.values())))
                if not unique_skills:
                    return
                
                ids = [
                    f"skill_{s.lower().replace(' ', '_').replace('+', 'p').replace('#', 'sharp')}" 
                    for s in unique_skills
                ]
                documents = [f"{s} - programming skill, framework, or technology" for s in unique_skills]
                embeddings = embed_batch(documents)
                metadatas = [{"skill": s} for s in unique_skills]
                
                collection.add(
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas
                )
                logger.info(f"Successfully seeded {len(unique_skills)} unique skills into vector DB.")
        except PermissionError as e:
            logger.warning(f"Permission denied writing to ChromaDB at '{settings.CHROMA_PATH}': {e}")
        except Exception as e:
            logger.warning(f"Failed to seed skills vector collection: {e}")

    @classmethod
    def initialize_collections(cls):
        """
        Safely initialize collections and taxonomy seed data during startup.
        Called from application lifespan, not at module import time.
        """
        try:
            cls.get_collection("user_profiles")
            cls.get_collection("job_listings")
            cls.get_collection("applications")
            cls.get_collection("skills")
            cls.seed_skills_if_empty()
            return True
        except Exception as e:
            logger.warning(f"ChromaDB collection initialization deferred/failed: {e}")
            return False
