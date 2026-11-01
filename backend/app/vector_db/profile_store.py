import json
from typing import List, Dict, Any, Optional
from app.vector_db.chroma_client import ChromaDBClient
from app.vector_db.embedder import embed_text, embed_batch
from app.resume.cleaner import ResumeCleaner

class ProfileStore:
    COLLECTION_NAME = "user_profiles"
    _profile_cache: Dict[int, Any] = {}  # In-memory user profile cache to optimize DB reads

    @classmethod
    def get_collection(cls):
        return ChromaDBClient.get_collection(cls.COLLECTION_NAME)

    @classmethod
    def store_profile(cls, user_id: int, resume_text: str, skills: List[str], metadata: Optional[Dict[str, Any]] = None):
        cls._profile_cache.pop(user_id, None)
        try:
            from app.jobs.matcher import JobMatcher
            JobMatcher._match_cache.clear()
        except Exception:
            pass
        collection = cls.get_collection()
        
        # Remove any stale profile vectors for this user before writing the current state
        try:
            collection.delete(where={"user_id": str(user_id)})
        except Exception:
            pass

        # Clean and segment the resume into sections
        sections = ResumeCleaner.segment_sections(resume_text)
        
        ids = []
        documents = []
        metadatas = []
        
        skills_str = json.dumps(skills)
        
        meta_base: Dict[str, Any] = {}
        if metadata:
            for k, v in metadata.items():
                if isinstance(v, bytes):
                    meta_base[k] = v.decode("utf-8")
                elif isinstance(v, (str, int, float, bool)):
                    meta_base[k] = v
                elif v is None:
                    meta_base[k] = ""
                else:
                    meta_base[k] = str(v)
        
        meta_base.pop("user_id", None)
        
        # 1. Store the full profile text
        full_id = f"{user_id}_full_profile"
        ids.append(full_id)
        documents.append(resume_text)
        metadatas.append({
            "user_id": str(user_id),
            "type": "full",
            "skills": skills_str,
            **meta_base
        })
        
        # 2. Store individual sections for granular retrieval
        for sec_name, sec_text in sections.items():
            if not sec_text.strip():
                continue
            sec_id = f"{user_id}_section_{sec_name}"
            ids.append(sec_id)
            documents.append(sec_text)
            metadatas.append({
                "user_id": str(user_id),
                "type": f"section_{sec_name}",
                "section_name": sec_name,
                "skills": skills_str,
                **meta_base
            })
            
        # Generate all embeddings in a single batch call
        try:
            embeddings = embed_batch(documents)
        except Exception as emb_err:
            import logging
            logger = logging.getLogger("uvicorn.error")
            logger.error(f"Failed to generate batch embeddings for user profile: {emb_err}")
            raise RuntimeError(f"Embedding batch generation failed: {emb_err}")

        # Use upsert to overwrite if it already exists
        try:
            collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas
            )
        except Exception as e:
            import logging
            logger = logging.getLogger("uvicorn.error")
            logger.error(f"Failed to upsert profile vectors in ChromaDB: {e}")
            raise RuntimeError(f"ChromaDB write error: {e}")

    @classmethod
    def get_profile(cls, user_id: int) -> Optional[Dict[str, Any]]:
        if user_id in cls._profile_cache:
            return cls._profile_cache[user_id]
            
        collection = cls.get_collection()
        
        # Search using metadata filter to ensure isolation
        results = collection.get(
            where={"user_id": str(user_id)}
        )
        
        if not results or not results["ids"]:
            cls._profile_cache[user_id] = None
            return None
            
        profile: Dict[str, Any] = {
            "user_id": user_id,
            "resume_text": "",
            "skills": [],
            "sections": {}
        }
        
        for i, doc_id in enumerate(results["ids"]):
            doc = results["documents"][i]
            meta = results["metadatas"][i]
            doc_type = meta.get("type")
            
            # Extract skills list from any of the records
            if "skills" in meta and not profile["skills"]:
                try:
                    profile["skills"] = json.loads(meta["skills"])
                except Exception:
                    profile["skills"] = []
            
            if doc_type == "full":
                profile["resume_text"] = doc
            elif doc_type.startswith("section_"):
                sec_name = meta.get("section_name")
                profile["sections"][sec_name] = doc
                
        cls._profile_cache[user_id] = profile
        return profile

    @classmethod
    def update_profile(cls, user_id: int, new_data: Dict[str, Any]):
        profile = cls.get_profile(user_id)
        if not profile:
            # Create new
            resume_text = new_data.get("resume_text", "")
            skills = new_data.get("skills", [])
            cls.store_profile(user_id, resume_text, skills)
        else:
            # Merge and store
            resume_text = new_data.get("resume_text", profile["resume_text"])
            skills = new_data.get("skills", profile["skills"])
            cls.store_profile(user_id, resume_text, skills)
            
    @classmethod
    def delete_profile(cls, user_id: int):
        cls._profile_cache.pop(user_id, None)
        try:
            from app.jobs.matcher import JobMatcher
            JobMatcher._match_cache.clear()
        except Exception:
            pass
        collection = cls.get_collection()
        collection.delete(where={"user_id": str(user_id)})
        
    @classmethod
    def query_profile_sections(cls, user_id: int, query_text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        collection = cls.get_collection()
        total_sections = collection.count()
        if total_sections == 0:
            return []
        effective_n_results = min(n_results, total_sections)
        query_emb = embed_text(query_text)
        
        # We query the granular sections only (exclude type: "full")
        results = collection.query(
            query_embeddings=[query_emb],
            n_results=effective_n_results,
            where={
                "$and": [
                    {"user_id": {"$eq": str(user_id)}},
                    {"type": {"$ne": "full"}}
                ]
            }
        )
        
        outputs = []
        if results and results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                outputs.append({
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i] if "distances" in results else None
                })
        return outputs
