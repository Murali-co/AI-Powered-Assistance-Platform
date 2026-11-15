import re
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple
from app.vector_db.chroma_client import ChromaDBClient
from app.vector_db.embedder import embed_text, embed_batch
from app.vector_db.profile_store import ProfileStore
from app.resume.extractor import SKILL_TAXONOMY

class JobMatcher:
    @staticmethod
    def _job_bucket(match_score: float, matched_skills: List[str], missing_skills: List[str] | None = None) -> str:
        if float(match_score) >= 70.0 and len(missing_skills or []) <= 2:
            return "matched"
        return "skill_gap"

    @staticmethod
    def _normalize_posted_at(value: Any) -> str:
        if value is None:
            return ""
        value_str = str(value).strip()
        if not value_str or value_str.lower() in {"nan", "recently", "just now"}:
            return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        try:
            if value_str.endswith("Z"):
                value_str = value_str[:-1] + "+00:00"
            iso = datetime.fromisoformat(value_str)
            if iso.tzinfo is None:
                iso = iso.replace(tzinfo=timezone.utc)
            return iso.isoformat().replace("+00:00", "Z")
        except ValueError:
            pass

        lowered = value_str.lower()
        if any(prefix in lowered for prefix in ["hour", "hours", "day", "days", "week", "weeks", "month", "months"]):
            now = datetime.now(timezone.utc)
            match = re.search(r"(\d+)\s*(hour|hours|day|days|week|weeks|month|months)", lowered)
            if match:
                count = int(match.group(1))
                unit = match.group(2)
                delta = None
                if unit.startswith("hour"):
                    delta = __import__("datetime").timedelta(hours=count)
                elif unit.startswith("day"):
                    delta = __import__("datetime").timedelta(days=count)
                elif unit.startswith("week"):
                    delta = __import__("datetime").timedelta(weeks=count)
                elif unit.startswith("month"):
                    delta = __import__("datetime").timedelta(days=30 * count)
                if delta is not None:
                    return (now - delta).isoformat().replace("+00:00", "Z")

        try:
            parsed = datetime.fromisoformat(value_str.split(" ")[0])
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.isoformat().replace("+00:00", "Z")
        except ValueError:
            return ""

    @staticmethod
    def _posted_ts_from_meta(job: Dict[str, Any]) -> str:
        posted_at = job.get("posted_ts") or job.get("posted_at") or ""
        ts = JobMatcher._normalize_posted_at(posted_at)
        if ts:
            return ts
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _coerce_epoch_seconds(value: Any, fallback: float | None = None) -> float:
        if value is None:
            return fallback if fallback is not None else time.time()

        if isinstance(value, (int, float)):
            return float(value)

        if hasattr(value, "timestamp") and callable(value.timestamp):
            try:
                return float(value.timestamp())
            except Exception:
                pass

        if isinstance(value, str):
            value_str = value.strip()
            if not value_str or value_str.lower() in {"nan", "recently", "just now", "now"}:
                return fallback if fallback is not None else time.time()
            try:
                return float(value_str)
            except ValueError:
                pass
            try:
                normalized = value_str.replace("Z", "+00:00")
                dt = datetime.fromisoformat(normalized)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return float(dt.timestamp())
            except ValueError:
                pass

        return fallback if fallback is not None else time.time()

    @staticmethod
    def _is_recent(job: Dict[str, Any], hours_old: int | None) -> bool:
        if hours_old is None:
            return True
        posted_at = job.get("posted_at") or ""
        if not posted_at:
            return True

        value = str(posted_at).strip()
        if value.lower() in {"recently", "nan", ""}:
            return True

        try:
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
            return age_hours <= float(hours_old)
        except ValueError:
            return True

    COLLECTION_NAME = "job_listings"
    _match_cache: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}  # In-memory cache for matched jobs to optimize performance

    @classmethod
    def get_collection(cls):
        return ChromaDBClient.get_collection(cls.COLLECTION_NAME)

    @classmethod
    def upsert_jobs(cls, jobs: List[Dict[str, Any]]):
        cls._match_cache.clear()  # Clear match cache when new jobs are indexed
        collection = cls.get_collection()
        if not jobs:
            return

        cleaned_jobs = []
        for job in jobs:
            normalized = dict(job)
            fallback_ts = time.time()
            normalized["posted_at"] = cls._normalize_posted_at(job.get("posted_at")) or "Recently"
            normalized["posted_ts"] = cls._coerce_epoch_seconds(
                job.get("posted_ts") or job.get("posted_at") or normalized.get("posted_at"),
                fallback=fallback_ts
            )
            normalized["location"] = normalized.get("location") or "Remote"
            normalized["source"] = normalized.get("source") or "scraped"
            normalized["job_type"] = normalized.get("job_type") or "onsite"
            cleaned_jobs.append(normalized)

        ids = []
        documents = []
        embeddings = []
        metadatas = []

        # Collect descriptions for batch embedding to optimize performance
        descriptions = [j["description"] for j in cleaned_jobs]
        job_embeddings = embed_batch(descriptions)

        for i, job in enumerate(cleaned_jobs):
            ids.append(job["id"])
            documents.append(job["description"])
            embeddings.append(job_embeddings[i])
            metadatas.append({
                "title": job["title"],
                "company": job["company"],
                "location": job["location"],
                "url": job["url"],
                "posted_at": job["posted_at"],
                "posted_ts": job.get("posted_ts") or cls._posted_ts_from_meta(job),
                "source": job["source"],
                "job_type": job.get("job_type", "onsite"),
            })

        collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas
        )

    @classmethod
    def match_jobs_for_user(cls, user_id: int, limit: int = 50, hours_old: int | None = None) -> List[Dict[str, Any]]:
        cache_key = (user_id, limit, hours_old)
        if cache_key in cls._match_cache:
            return cls._match_cache[cache_key]

        collection = cls.get_collection()
        total_jobs = collection.count()
        if total_jobs == 0:
            return []
        effective_limit = min(limit, total_jobs)

        where_clause = None
        if hours_old is not None:
            cutoff_ts = time.time() - (float(hours_old) * 3600)
            where_clause = {"posted_ts": {"$gte": cutoff_ts}}

        # 1. Retrieve the user's profile text and skills
        profile = ProfileStore.get_profile(user_id)
        if not profile or not profile.get("resume_text"):
            # If no profile, we can't do semantic matching. Return raw list of jobs with 0 score
            try:
                results = collection.get(where=where_clause, limit=effective_limit)
            except Exception as exc:
                import logging
                logger = logging.getLogger("uvicorn.error")
                logger.error(f"Chroma get failed in match_jobs_for_user: {exc}", exc_info=True)
                cls._match_cache[cache_key] = []
                return []
            jobs = cls._format_unmatched_jobs(results)
            if hours_old is not None:
                jobs = [job for job in jobs if cls._is_recent(job, hours_old)]
            cls._match_cache[cache_key] = jobs
            return jobs

        user_skills = set(profile.get("skills", []))
        user_skills_lower = {s.lower() for s in user_skills}

        # 2. Get the full profile embedding
        profile_collection = ProfileStore.get_collection()
        profile_emb_result = profile_collection.get(
            ids=[f"{user_id}_full_profile"],
            include=["embeddings"]
        )

        user_emb = None
        if profile_emb_result:
            embeddings = profile_emb_result.get("embeddings")
            if embeddings is not None:
                embeddings_list = embeddings.tolist() if hasattr(embeddings, 'tolist') else embeddings
                if isinstance(embeddings_list, list) and len(embeddings_list) > 0:
                    user_emb = embeddings_list[0]

        if user_emb is None:
            user_emb = embed_text(profile["resume_text"])

        try:
            filtered_docs = collection.get(where=where_clause, include=["metadatas"]) if where_clause else collection.get(include=["metadatas"])
            matched_docs = len(filtered_docs["ids"]) if filtered_docs and filtered_docs.get("ids") else 0
        except Exception as exc:
            import logging
            logger = logging.getLogger("uvicorn.error")
            logger.error(f"Chroma age filter count failed in match_jobs_for_user: {exc}", exc_info=True)
            cls._match_cache[cache_key] = []
            return []

        n_results = min(effective_limit, max(0, matched_docs))
        if n_results == 0:
            cls._match_cache[cache_key] = []
            return []

        try:
            results = collection.query(
                query_embeddings=[user_emb],
                n_results=n_results,
                where=where_clause
            )
        except Exception as exc:
            import logging
            logger = logging.getLogger("uvicorn.error")
            logger.error(f"Chroma query failed in match_jobs_for_user: {exc}", exc_info=True)
            cls._match_cache[cache_key] = []
            return []

        matched_jobs = []
        if not results or not results["ids"] or not results["ids"][0]:
            cls._match_cache[cache_key] = []
            return []

        ids = results["ids"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0] if "distances" in results else [0.5] * len(ids)

        for i in range(len(ids)):
            job_id = ids[i]
            desc = documents[i]
            meta = metadatas[i]
            dist = distances[i]

            score = (1.0 - float(dist)) * 100.0
            if dist > 1.0:
                score = max(0.0, min(100.0, (1.0 - (dist / 2.0)) * 100.0))
            else:
                score = max(0.0, min(100.0, score))

            job_desc_lower = desc.lower()
            job_skills = set()
            for kw, std_name in SKILL_TAXONOMY.items():
                escaped_kw = re.escape(kw)
                pattern = rf"\b{escaped_kw}" if (kw.endswith("++") or kw.endswith("#")) else rf"\b{escaped_kw}\b"
                if re.search(pattern, job_desc_lower):
                    job_skills.add(std_name)

            matched_skills_list = []
            missing_skills_list = []
            for s in job_skills:
                if s.lower() in user_skills_lower:
                    matched_skills_list.append(s)
                else:
                    missing_skills_list.append(s)

            job_entry = {
                "id": job_id,
                "title": meta.get("title", "Unknown Role"),
                "company": meta.get("company", "Unknown Company"),
                "location": meta.get("location", "Remote"),
                "description": desc,
                "url": meta.get("url", ""),
                "posted_at": meta.get("posted_at", ""),
                "posted_ts": meta.get("posted_ts") or cls._posted_ts_from_meta(meta),
                "source": meta.get("source", "scraped"),
                "job_type": meta.get("job_type", "onsite"),
                "match_score": round(score, 1),
                "bi_encoder_score": round(score, 1),
                "matched_skills": matched_skills_list,
                "missing_skills": missing_skills_list,
                "bucket": cls._job_bucket(score, matched_skills_list, missing_skills_list),
            }

            if hours_old is not None and not cls._is_recent(job_entry, hours_old):
                continue

            matched_jobs.append(job_entry)

        try:
            from app.jobs.two_stage_matcher import TwoStageJobMatcher
            matched_jobs = TwoStageJobMatcher.match_and_explain(
                candidate_profile=profile,
                jobs=matched_jobs,
                top_k=limit,
                rerank_limit=min(15, limit)
            )
        except Exception as e:
            print(f"Notice: Two-stage reranking fallback to bi-encoder: {e}")
            matched_jobs.sort(key=lambda x: x["match_score"], reverse=True)

        for job in matched_jobs:
            job["bucket"] = cls._job_bucket(job.get("match_score", 0.0), job.get("matched_skills", []) or [], job.get("missing_skills", []) or [])

        cls._match_cache[cache_key] = matched_jobs
        return matched_jobs

    @classmethod
    def _format_unmatched_jobs(cls, get_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        jobs = []
        if not get_results or not get_results["ids"]:
            return []
        for i in range(len(get_results["ids"])):
            meta = get_results["metadatas"][i]
            jobs.append({
                "id": get_results["ids"][i],
                "title": meta.get("title", "Unknown Role"),
                "company": meta.get("company", "Unknown Company"),
                "location": meta.get("location", "Remote"),
                "description": get_results["documents"][i],
                "url": meta.get("url", ""),
                "posted_at": meta.get("posted_at", ""),
                "posted_ts": meta.get("posted_ts") or cls._posted_ts_from_meta(meta),
                "source": meta.get("source", "scraped"),
                "job_type": meta.get("job_type", "onsite"),
                "match_score": 0.0,
                "matched_skills": [],
                "missing_skills": [],
                "bucket": "skill_gap"
            })
        return jobs

    @classmethod
    def cleanup_old_jobs(cls, days: int = 30):
        collection = cls.get_collection()
        results = collection.get(include=["metadatas"])
        if not results or not results["ids"]:
            return
        
        from datetime import datetime, timezone
        
        now = datetime.now(timezone.utc)
        ids_to_delete = []
        
        for i, job_id in enumerate(results["ids"]):
            meta = results["metadatas"][i]
            posted_at_str = meta.get("posted_at")
            if not posted_at_str:
                continue
            try:
                posted_date = None
                if "T" in posted_at_str:
                    clean_str = posted_at_str.replace("Z", "+00:00")
                    posted_date = datetime.fromisoformat(clean_str)
                elif "-" in posted_at_str:
                    parts = posted_at_str.split(" ")[0].split("-")
                    if len(parts) == 3:
                        posted_date = datetime(int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=timezone.utc)
                
                if posted_date:
                    age_days = (now - posted_date).days
                    if age_days > days:
                        ids_to_delete.append(job_id)
            except Exception as e:
                print(f"Error parsing date {posted_at_str}: {e}")
                
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
            print(f"Cleaned up {len(ids_to_delete)} stale jobs from ChromaDB.")


    @classmethod
    async def explain_job_match(cls, user_id: int, job_id: str) -> Dict[str, Any]:
        """
        Retrieves vector match score, matched/missing skills, and queries the local LLM
        to produce detailed analysis of experience, education, keyword gaps, and recommendations.
        """
        collection = cls.get_collection()
        job_data = collection.get(ids=[job_id])
        if not job_data or not job_data["ids"]:
            raise Exception("Job listing not found.")
            
        desc = job_data["documents"][0]
        meta = job_data["metadatas"][0]
        
        # 1. Fetch user profile
        profile = ProfileStore.get_profile(user_id)
        if not profile or not profile.get("resume_text"):
            raise Exception("User profile/resume not found. Please upload a resume first.")
            
        resume_text = profile["resume_text"]
        user_skills = set(profile.get("skills", []))
        user_skills_lower = {s.lower() for s in user_skills}
        
        # 2. Get user embedding
        profile_collection = ProfileStore.get_collection()
        profile_emb_result = profile_collection.get(
            ids=[f"{user_id}_full_profile"],
            include=["embeddings"]
        )
        
        # Handle numpy arrays safely - avoid boolean checks on multi-element arrays
        user_emb = None
        if profile_emb_result:
            embeddings = profile_emb_result.get("embeddings")
            if embeddings is not None:
                # Convert to list if it's a numpy array to safely check length
                embeddings_list = embeddings.tolist() if hasattr(embeddings, 'tolist') else embeddings
                if isinstance(embeddings_list, list) and len(embeddings_list) > 0:
                    user_emb = embeddings_list[0]
        
        # Recompute embedding if missing
        if user_emb is None:
            user_emb = embed_text(resume_text)

        # Query specifically to find this job's vector distance
        total_jobs = collection.count()
        dist = 0.5
        if total_jobs > 0:
            effective_n_results = min(100, total_jobs)
            results = collection.query(
                query_embeddings=[user_emb],
                n_results=effective_n_results
            )
            if results and results["ids"] and results["ids"][0]:
                for idx_id, rid in enumerate(results["ids"][0]):
                    if rid == job_id:
                        dist = results["distances"][0][idx_id]
                        break
        
        # Normalize score
        score = (1.0 - float(dist)) * 100.0
        if dist > 1.0:
            score = max(0.0, min(100.0, (1.0 - (dist / 2.0)) * 100.0))
        else:
            score = max(0.0, min(100.0, score))
        score = round(score, 1)

        # 3. Extract skills
        job_desc_lower = desc.lower()
        job_skills = set()
        for kw, std_name in SKILL_TAXONOMY.items():
            escaped_kw = re.escape(kw)
            pattern = rf"\b{escaped_kw}" if (kw.endswith("++") or kw.endswith("#")) else rf"\b{escaped_kw}\b"
            if re.search(pattern, job_desc_lower):
                job_skills.add(std_name)
                
        matched_skills_list = []
        missing_skills_list = []
        for s in job_skills:
            if s.lower() in user_skills_lower:
                matched_skills_list.append(s)
            else:
                missing_skills_list.append(s)
                
        # 4. LLM Gap Analysis
        from app.llm.ollama_client import OllamaClient
        import json
        
        prompt = f"""
        You are an ATS Parser and Career Copilot. Analyze the candidate's resume against the target job description.
        
        Target Job Title: {meta.get("title")}
        Target Job Company: {meta.get("company")}
        
        Candidate Resume:
        {resume_text}
        
        Job Description:
        {desc}
        
        Provide a structured analysis comparing:
        1. Experience Gap: Compare years of experience or level of seniority.
        2. Education Gap: Compare degree levels and fields.
        3. Keyword Gap: Key terms and technologies in the job description missing from the resume.
        4. Actionable Recommendations: Actionable steps (projects, courses, certifications) to raise the match score.
        
        Return ONLY a valid JSON object. Do not wrap it in markdown block tags. Do not output any introductory or concluding text.
        
        JSON Schema:
        {{
            "experience_gap": "description of experience gaps",
            "education_gap": "description of education/degree gaps",
            "keyword_gap": ["missing_term_1", "missing_term_2"],
            "recommendations": ["actionable_tip_1", "actionable_tip_2"]
        }}
        """
        
        experience_gap = "Unable to analyze experience gap."
        education_gap = "Unable to analyze education gap."
        keyword_gap: List[str] = []
        recommendations = [
            "Review job requirements and align resume keywords.",
            "Build target projects to gain hands-on experience.",
            "Obtain relevant certifications in missing tech stacks."
        ]
        
        try:
            llm_res = await OllamaClient.generate(prompt, format="json", think=False)
            cleaned = llm_res.strip()
            if "```" in cleaned:
                parts = cleaned.split("```")
                for p in parts:
                    p_strip = p.strip()
                    if p_strip.startswith("{") or p_strip.startswith("json\n{"):
                        if p_strip.startswith("json\n"):
                            cleaned = p_strip[5:]
                        else:
                            cleaned = p_strip
                        break
            
            data = json.loads(cleaned)
            experience_gap = data.get("experience_gap", experience_gap)
            education_gap = data.get("education_gap", education_gap)
            keyword_gap = data.get("keyword_gap", keyword_gap)
            recommendations = data.get("recommendations", recommendations)
        except Exception as e:
            print(f"Ollama JSON parsing failed, using fallbacks: {e}")
        # Generate traceable evidence citations and ESCO mapping
        try:
            from app.services.esco_service import ESCOSkillService
            from app.jobs.two_stage_matcher import TwoStageJobMatcher
            esco_res = ESCOSkillService.analyze_skill_overlap(
                job_required=matched_skills_list + missing_skills_list,
                job_preferred=[],
                candidate_skills=list(user_skills)
            )
            citations = []
            for s in matched_skills_list:
                ev = TwoStageJobMatcher.extract_resume_evidence(resume_text, s)
                if ev:
                    citations.append({"requirement": s, "supporting_evidence": ev[0]})
        except Exception as e:
            print(f"Notice: ESCO explanation fallback: {e}")
            esco_res = {"matched_related": [], "esco_version": "v1.1.2-ict"}
            citations = []
            
        return {
            "score": score,
            "matched_skills": matched_skills_list,
            "missing_skills": missing_skills_list,
            "matched_related_skills": esco_res.get("matched_related", []),
            "evidence_citations": citations,
            "experience_gap": experience_gap,
            "education_gap": education_gap,
            "keyword_gap": keyword_gap,
            "recommendations": recommendations,
            "esco_version": esco_res.get("esco_version", "v1.1.2-ict")
        }

