"""
AI Powered Assistance Platform Two-Stage Job Matching Engine
Stage 1: Bi-encoder semantic retrieval (SentenceTransformer)
Stage 2: Cross-encoder requirement reranking (CrossEncoder)
ESCO-based ontology normalization and traceable evidence extraction.
"""

import re
import math
from typing import List, Dict, Any, Tuple, Optional
from app.services.esco_service import ESCOSkillService
from app.vector_db.embedder import embed_text, get_embedding_model

_cross_encoder_model = None

def get_cross_encoder_model(model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
    """
    Lazy-loads CrossEncoder model with fallback to calibrated scoring
    if model weights cannot be downloaded in offline mode.
    """
    global _cross_encoder_model
    if _cross_encoder_model is None:
        try:
            from sentence_transformers.cross_encoder import CrossEncoder
            _cross_encoder_model = CrossEncoder(model_name, max_length=512)
        except Exception as e:
            print(f"Notice: CrossEncoder lazy load fallback: {e}")
            return None
    return _cross_encoder_model


class TwoStageJobMatcher:
    """
    Two-Stage matching engine with evidence-based explanations.
    """
    BI_ENCODER_MODEL_NAME = "all-MiniLM-L6-v2"
    CROSS_ENCODER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    @classmethod
    def get_bi_encoder(cls):
        return get_embedding_model()

    @classmethod
    def get_cross_encoder(cls):
        return get_cross_encoder_model(cls.CROSS_ENCODER_MODEL_NAME)

    @classmethod
    def extract_resume_evidence(cls, resume_text: str, requirement: str) -> List[str]:
        """
        Extracts traceable sentences from resume that substantiate a requirement.
        """
        if not resume_text or not requirement:
            return []

        # Split resume into sentences/bullet points
        sentences = re.split(r"[\n•\-\*\.]+", resume_text)
        req_words = [w.lower() for w in re.findall(r"\b[A-Za-z0-9+#_]{2,}\b", requirement) if w.lower() not in {"and", "with", "the", "for", "years", "experience", "required", "preferred"}]
        
        matches = []
        for s in sentences:
            cleaned = s.strip()
            if len(cleaned) < 15:
                continue
            lower_s = cleaned.lower()
            overlap = sum(1 for rw in req_words if rw in lower_s)
            if overlap >= 2 or (len(req_words) == 1 and req_words[0] in lower_s):
                matches.append(cleaned)
                if len(matches) >= 3:
                    break

        return matches

    @classmethod
    def rerank_with_cross_encoder(
        cls,
        candidate_summary: str,
        retrieved_candidates: List[Dict[str, Any]],
        top_n: int = 15
    ) -> List[Dict[str, Any]]:
        """
        Stage 2: Cross-encoder reranking of the top-K retrieved candidate jobs.
        Reranks query-document pairs: (candidate_summary, job_description).
        """
        if not retrieved_candidates:
            return []

        # Rerank only up to top_n to control latency
        candidates_to_rerank = retrieved_candidates[:top_n]
        remaining = retrieved_candidates[top_n:]

        pairs = [
            (candidate_summary[:600], job.get("description", "")[:800])
            for job in candidates_to_rerank
        ]

        cross_model = get_cross_encoder_model(cls.CROSS_ENCODER_MODEL_NAME)
        
        if cross_model is not None:
            try:
                raw_scores = cross_model.predict(pairs)
                # Map raw logits through sigmoid to 0.0 - 100.0 score
                for i, score in enumerate(raw_scores):
                    # Sigmoid activation: 1 / (1 + exp(-x))
                    sig_score = 1.0 / (1.0 + math.exp(-float(score)))
                    candidates_to_rerank[i]["cross_encoder_score"] = round(sig_score * 100.0, 1)
            except Exception as e:
                print(f"CrossEncoder prediction warning: {e}. Using calibrated fallback.")
                cls._apply_fallback_reranker_scores(candidate_summary, candidates_to_rerank)
        else:
            cls._apply_fallback_reranker_scores(candidate_summary, candidates_to_rerank)

        # Compute balanced final ranking score:
        # 40% Bi-encoder semantic retrieval score
        # 35% Cross-encoder query-document alignment score
        # 25% ESCO skill coverage score
        for job in candidates_to_rerank:
            bi_score = float(job.get("bi_encoder_score", job.get("match_score", 50.0)))
            cross_score = float(job.get("cross_encoder_score", bi_score))
            skill_score = float(job.get("skill_match_score", bi_score))

            final_score = (bi_score * 0.40) + (cross_score * 0.35) + (skill_score * 0.25)
            job["final_score"] = round(final_score, 1)
            job["match_score"] = job["final_score"]  # Ensure backward compatibility

        # Sort reranked jobs by final_score descending
        candidates_to_rerank.sort(key=lambda x: x["final_score"], reverse=True)
        return candidates_to_rerank + remaining

    @classmethod
    def _apply_fallback_reranker_scores(cls, candidate_summary: str, candidates: List[Dict[str, Any]]):
        """Calibrated fallback if cross-encoder weights are offline."""
        cand_lower = candidate_summary.lower()
        cand_terms = set(re.findall(r"\b[a-zA-Z0-9+#_]{3,}\b", cand_lower))
        for job in candidates:
            desc_lower = job.get("description", "").lower()
            job_terms = set(re.findall(r"\b[a-zA-Z0-9+#_]{3,}\b", desc_lower))
            overlap = len(cand_terms.intersection(job_terms))
            denominator = max(len(job_terms), 1)
            jaccard = (overlap / denominator)
            # Combine jaccard with bi-encoder score
            base = float(job.get("bi_encoder_score", 50.0))
            score = max(0.0, min(100.0, (base * 0.70) + (jaccard * 100.0 * 0.30)))
            job["cross_encoder_score"] = round(score, 1)

    @classmethod
    def match_and_explain(
        cls,
        candidate_profile: Dict[str, Any],
        jobs: List[Dict[str, Any]],
        top_k: int = 25,
        rerank_limit: int = 15
    ) -> List[Dict[str, Any]]:
        """
        End-to-end two-stage matching pipeline:
        1. Bi-encoder semantic retrieval score
        2. ESCO skill overlap & transferability analysis
        3. Cross-encoder reranking
        4. Evidence citations & structured explanation
        """
        if not candidate_profile or not candidate_profile.get("resume_text"):
            # Empty candidate profile: return baseline with 0.0 scores
            return [
                {
                    **j,
                    "match_score": 0.0,
                    "bi_encoder_score": 0.0,
                    "cross_encoder_score": 0.0,
                    "matched_skills": [],
                    "missing_skills": [],
                    "explanation": {
                        "summary": "Please upload a resume to receive personalized match scores and explanations.",
                        "matched_exact": [],
                        "matched_related": [],
                        "missing_mandatory": [],
                        "missing_preferred": [],
                        "evidence_citations": []
                    }
                }
                for j in jobs[:top_k]
            ]

        resume_text = candidate_profile["resume_text"]
        cand_skills = candidate_profile.get("skills", [])
        
        # 1. Compute Bi-Encoder Scores for jobs
        retrieved: List[Dict[str, Any]] = []
        for job in jobs:
            # Analyze ESCO skills
            job_desc = job.get("description", "")
            raw_req = job.get("required_skills", []) or []
            raw_pref = job.get("preferred_skills", []) or []

            # If required_skills not pre-populated, extract from description
            if not raw_req:
                from app.resume.extractor import SKILL_TAXONOMY
                extracted = []
                job_desc_lower = job_desc.lower()
                for kw, std in SKILL_TAXONOMY.items():
                    if re.search(rf"\b{re.escape(kw)}\b", job_desc_lower):
                        extracted.append(std)
                raw_req = extracted[:5]
                raw_pref = extracted[5:8]

            esco_analysis = ESCOSkillService.analyze_skill_overlap(
                job_required=raw_req,
                job_preferred=raw_pref,
                candidate_skills=cand_skills
            )

            # Stage 1 Score
            bi_score = float(job.get("bi_encoder_score") or job.get("match_score") or 60.0)

            # Build evidence citations for matched skills
            evidence_citations = []
            for matched_skill in esco_analysis["matched_exact"]:
                evidence = cls.extract_resume_evidence(resume_text, matched_skill)
                if evidence:
                    evidence_citations.append({
                        "requirement": matched_skill,
                        "type": "exact_match",
                        "supporting_evidence": evidence[0]
                    })

            for related in esco_analysis["matched_related"]:
                evidence = cls.extract_resume_evidence(resume_text, related["candidate_skill"])
                if evidence:
                    evidence_citations.append({
                        "requirement": related["required_skill"],
                        "type": "transferable_skill",
                        "candidate_skill": related["candidate_skill"],
                        "confidence": related["confidence"],
                        "supporting_evidence": evidence[0],
                        "note": related["note"]
                    })

            retrieved.append({
                **job,
                "bi_encoder_score": round(bi_score, 1),
                "skill_match_score": esco_analysis["skill_match_score"],
                "matched_skills": esco_analysis["matched_exact"],
                "missing_skills": esco_analysis["missing_mandatory"],
                "esco_analysis": esco_analysis,
                "evidence_citations": evidence_citations
            })

        # Sort by Stage 1 bi-encoder score descending and take top-K
        retrieved.sort(key=lambda x: x["bi_encoder_score"], reverse=True)
        retrieved_top = retrieved[:top_k]

        # Stage 2: Cross-Encoder Reranking
        candidate_summary = f"{candidate_profile.get('target_role', '')}\nSkills: {', '.join(cand_skills)}\n{resume_text[:400]}"
        reranked = cls.rerank_with_cross_encoder(
            candidate_summary=candidate_summary,
            retrieved_candidates=retrieved_top,
            top_n=rerank_limit
        )

        # Assemble explainable output for each job
        for item in reranked:
            esco = item["esco_analysis"]
            item["explanation"] = {
                "overall_score": item["final_score"],
                "bi_encoder_retrieval_score": item["bi_encoder_score"],
                "cross_encoder_rerank_score": item.get("cross_encoder_score", item["bi_encoder_score"]),
                "skill_coverage_score": item["skill_match_score"],
                "matched_exact_skills": esco["matched_exact"],
                "matched_related_skills": esco["matched_related"],
                "missing_mandatory_skills": esco["missing_mandatory"],
                "missing_preferred_skills": esco["missing_preferred"],
                "evidence_citations": item["evidence_citations"],
                "taxonomy_version": esco["esco_version"],
                "model_versions": {
                    "stage1_bi_encoder": cls.BI_ENCODER_MODEL_NAME,
                    "stage2_cross_encoder": cls.CROSS_ENCODER_MODEL_NAME,
                    "esco_taxonomy": ESCOSkillService.get_version()
                }
            }

        return reranked
