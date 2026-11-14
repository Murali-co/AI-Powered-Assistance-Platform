"""
AI Powered Assistance Platform ESCO Skill Intelligence Service
Compliant with European Skills, Competences, Qualifications and Occupations (ESCO v1.1)
Provides canonical skill normalization, alias resolution, transferable skill analysis,
and calibrated skill-gap taxonomy mapping.
"""

import re
from typing import Dict, Any, List, Optional, Set, Tuple

# Version tag of the ESCO taxonomy representation
ESCO_VERSION = "v1.1.2-ict"


class ESCOSkillService:
    """
    ESCO-based ontology and normalization service.
    Distinguishes exact matches, related skills, and missing requirements.
    Never treats related skills as absolute proof of acquiring a mandatory skill.
    """

    # Comprehensive canonical ESCO skills with metadata and transferable relationships
    ONTOLOGY: Dict[str, Dict[str, Any]] = {
        "python": {
            "esco_id": "http://data.europa.eu/esco/skill/48737e61-9c16-4354-9407-743ef0c77f0a",
            "preferred_label": "Python (computer programming)",
            "alt_labels": ["python", "python3", "py", "cpython"],
            "skill_type": "knowledge",
            "category": "ICT Programming",
            "related_skills": ["object-oriented programming", "scripting languages", "software development"],
            "transferable_to": {
                "scripting languages": 0.85,
                "data science": 0.70,
                "backend development": 0.80
            }
        },
        "postgresql": {
            "esco_id": "http://data.europa.eu/esco/skill/b653457a-9a9c-4c2f-b4b1-8b2b934b1234",
            "preferred_label": "PostgreSQL database management",
            "alt_labels": ["postgresql", "postgres", "psql", "pgadmin"],
            "skill_type": "skill/competence",
            "category": "Database Engineering",
            "related_skills": ["sql", "relational databases", "database management systems"],
            "transferable_to": {
                "sql": 0.90,
                "relational databases": 0.85,
                "database optimization": 0.60
            }
        },
        "sql": {
            "esco_id": "http://data.europa.eu/esco/skill/12c140df-1d60-4966-9b0c-7b43c683b51b",
            "preferred_label": "SQL (Structured Query Language)",
            "alt_labels": ["sql", "structured query language", "ansi sql"],
            "skill_type": "knowledge",
            "category": "Database Engineering",
            "related_skills": ["relational databases", "data querying"],
            "transferable_to": {
                "database querying": 0.90,
                "data analysis": 0.75
            }
        },
        "fastapi": {
            "esco_id": "http://data.europa.eu/esco/skill/c54b2a31-9011-4472-a7f4-8a43f80c6a1b",
            "preferred_label": "FastAPI web framework",
            "alt_labels": ["fastapi", "fast api", "asgi", "starlette", "pydantic"],
            "skill_type": "skill/competence",
            "category": "Web Development",
            "related_skills": ["rest api", "python", "backend development", "microservices"],
            "transferable_to": {
                "rest api": 0.85,
                "backend development": 0.80,
                "flask": 0.75
            }
        },
        "docker": {
            "esco_id": "http://data.europa.eu/esco/skill/e3d7a86e-9964-42f8-8ec4-511ecf330663",
            "preferred_label": "Containerization using Docker",
            "alt_labels": ["docker", "docker-compose", "containerization", "containers"],
            "skill_type": "skill/competence",
            "category": "Cloud & DevOps",
            "related_skills": ["kubernetes", "devops", "cloud computing", "ci/cd"],
            "transferable_to": {
                "kubernetes": 0.65,
                "devops": 0.75,
                "cloud deployment": 0.70
            }
        },
        "kubernetes": {
            "esco_id": "http://data.europa.eu/esco/skill/7f8a9b0c-1122-3344-5566-778899aabbcc",
            "preferred_label": "Kubernetes container orchestration",
            "alt_labels": ["kubernetes", "k8s", "helm", "container orchestration"],
            "skill_type": "skill/competence",
            "category": "Cloud & DevOps",
            "related_skills": ["docker", "cloud architecture", "devops"],
            "transferable_to": {
                "docker": 0.80,
                "cloud infrastructure": 0.75
            }
        },
        "react": {
            "esco_id": "http://data.europa.eu/esco/skill/d9c0e1f2-3344-5566-7788-99aabbccdde0",
            "preferred_label": "React framework",
            "alt_labels": ["react", "react.js", "reactjs", "react-dom"],
            "skill_type": "skill/competence",
            "category": "Frontend Development",
            "related_skills": ["javascript", "frontend development", "single-page applications", "typescript"],
            "transferable_to": {
                "frontend development": 0.85,
                "vue.js": 0.70,
                "next.js": 0.85
            }
        },
        "typescript": {
            "esco_id": "http://data.europa.eu/esco/skill/a1b2c3d4-e5f6-7890-1234-56789abcdef0",
            "preferred_label": "TypeScript",
            "alt_labels": ["typescript", "ts"],
            "skill_type": "knowledge",
            "category": "ICT Programming",
            "related_skills": ["javascript", "object-oriented programming", "static typing"],
            "transferable_to": {
                "javascript": 0.95,
                "frontend development": 0.80
            }
        },
        "javascript": {
            "esco_id": "http://data.europa.eu/esco/skill/8b9c0d1e-2f3a-4b5c-6d7e-8f9a0b1c2d3e",
            "preferred_label": "JavaScript",
            "alt_labels": ["javascript", "js", "ecmascript"],
            "skill_type": "knowledge",
            "category": "ICT Programming",
            "related_skills": ["typescript", "web development"],
            "transferable_to": {
                "web development": 0.90,
                "typescript": 0.75
            }
        },
        "machine learning": {
            "esco_id": "http://data.europa.eu/esco/skill/6f5e4d3c-2b1a-0f9e-8d7c-6b5a4f3e2d1c",
            "preferred_label": "Machine Learning",
            "alt_labels": ["machine learning", "ml", "statistical learning", "supervised learning"],
            "skill_type": "knowledge",
            "category": "Artificial Intelligence",
            "related_skills": ["deep learning", "python", "data science", "pytorch", "scikit-learn"],
            "transferable_to": {
                "data science": 0.80,
                "ai engineering": 0.85
            }
        },
        "pytorch": {
            "esco_id": "http://data.europa.eu/esco/skill/5e4d3c2b-1a0f-9e8d-7c6b-5a4f3e2d1c0b",
            "preferred_label": "PyTorch deep learning framework",
            "alt_labels": ["pytorch", "torch"],
            "skill_type": "skill/competence",
            "category": "Artificial Intelligence",
            "related_skills": ["machine learning", "deep learning", "python", "neural networks"],
            "transferable_to": {
                "machine learning": 0.85,
                "deep learning": 0.90,
                "tensorflow": 0.70
            }
        },
        "rest api": {
            "esco_id": "http://data.europa.eu/esco/skill/4d3c2b1a-0f9e-8d7c-6b5a-4f3e2d1c0b9a",
            "preferred_label": "RESTful API design and integration",
            "alt_labels": ["rest api", "rest", "restful api", "restful apis", "api design"],
            "skill_type": "skill/competence",
            "category": "Software Architecture",
            "related_skills": ["http", "json", "backend development", "microservices"],
            "transferable_to": {
                "api integration": 0.90,
                "backend development": 0.80
            }
        },
        "microservices": {
            "esco_id": "http://data.europa.eu/esco/skill/3c2b1a0f-9e8d-7c6b-5a4f-3e2d1c0b9a8f",
            "preferred_label": "Microservices architecture",
            "alt_labels": ["microservices", "microservice architecture", "distributed systems"],
            "skill_type": "knowledge",
            "category": "Software Architecture",
            "related_skills": ["docker", "rest api", "distributed systems", "cloud computing"],
            "transferable_to": {
                "software architecture": 0.85,
                "cloud architecture": 0.75
            }
        },
        "ci/cd": {
            "esco_id": "http://data.europa.eu/esco/skill/2b1a0f9e-8d7c-6b5a-4f3e-2d1c0b9a8f7e",
            "preferred_label": "Continuous Integration / Continuous Deployment (CI/CD)",
            "alt_labels": ["ci/cd", "ci cd", "continuous integration", "continuous deployment", "github actions", "gitlab ci", "jenkins"],
            "skill_type": "skill/competence",
            "category": "Cloud & DevOps",
            "related_skills": ["devops", "git", "automated testing"],
            "transferable_to": {
                "devops": 0.85,
                "release engineering": 0.80
            }
        },
        "git": {
            "esco_id": "http://data.europa.eu/esco/skill/1a0f9e8d-7c6b-5a4f-3e2d-1c0b9a8f7e6d",
            "preferred_label": "Version control with Git",
            "alt_labels": ["git", "github", "gitlab", "version control"],
            "skill_type": "skill/competence",
            "category": "Software Tools",
            "related_skills": ["software collaboration", "code review"],
            "transferable_to": {
                "version control": 0.95
            }
        },
        "aws": {
            "esco_id": "http://data.europa.eu/esco/skill/0f9e8d7c-6b5a-4f3e-2d1c-0b9a8f7e6d5c",
            "preferred_label": "Amazon Web Services (AWS) cloud platform",
            "alt_labels": ["aws", "amazon web services", "ec2", "s3", "lambda"],
            "skill_type": "knowledge",
            "category": "Cloud & DevOps",
            "related_skills": ["cloud computing", "cloud infrastructure"],
            "transferable_to": {
                "cloud computing": 0.90,
                "azure": 0.65,
                "gcp": 0.65
            }
        },
        "linux": {
            "esco_id": "http://data.europa.eu/esco/skill/9e8d7c6b-5a4f-3e2d-1c0b-9a8f7e6d5c4b",
            "preferred_label": "Linux operating system administration",
            "alt_labels": ["linux", "ubuntu", "debian", "red hat", "centos", "bash", "shell scripting"],
            "skill_type": "skill/competence",
            "category": "System Administration",
            "related_skills": ["bash", "unix", "server management"],
            "transferable_to": {
                "server administration": 0.80,
                "devops": 0.70
            }
        },
        "redis": {
            "esco_id": "http://data.europa.eu/esco/skill/8d7c6b5a-4f3e-2d1c-0b9a-8f7e6d5c4b3a",
            "preferred_label": "Redis in-memory data store",
            "alt_labels": ["redis", "in-memory caching", "redis cache"],
            "skill_type": "skill/competence",
            "category": "Database Engineering",
            "related_skills": ["caching", "nosql", "key-value stores"],
            "transferable_to": {
                "caching systems": 0.85,
                "nosql databases": 0.70
            }
        },
        "chromadb": {
            "esco_id": "http://data.europa.eu/esco/skill/7c6b5a4f-3e2d-1c0b-9a8f-7e6d5c4b3a29",
            "preferred_label": "Vector database management (ChromaDB)",
            "alt_labels": ["chromadb", "chroma", "vector db", "vector databases", "pinecone", "milvus"],
            "skill_type": "skill/competence",
            "category": "Artificial Intelligence & Data",
            "related_skills": ["vector search", "embeddings", "retrieval augmented generation", "rag"],
            "transferable_to": {
                "vector search": 0.85,
                "rag systems": 0.80
            }
        }
    }

    # Pre-built lookup table: alias -> canonical key
    _ALIAS_LOOKUP: Dict[str, str] = {}
    for canonical_key, data in ONTOLOGY.items():
        _ALIAS_LOOKUP[canonical_key.lower()] = canonical_key
        _ALIAS_LOOKUP[data["preferred_label"].lower()] = canonical_key
        for alias in data.get("alt_labels", []):
            _ALIAS_LOOKUP[alias.lower()] = canonical_key

    @classmethod
    def get_version(cls) -> str:
        return ESCO_VERSION

    @classmethod
    def normalize_skill(cls, raw_skill: str) -> Optional[Dict[str, Any]]:
        """
        Maps a free-text skill to canonical ESCO representation.
        Returns None if not in ontology.
        """
        if not raw_skill:
            return None
        clean_text = raw_skill.strip().lower()
        canonical_key = cls._ALIAS_LOOKUP.get(clean_text)
        if canonical_key and canonical_key in cls.ONTOLOGY:
            data = cls.ONTOLOGY[canonical_key]
            return {
                "canonical_id": data["esco_id"],
                "canonical_name": data["preferred_label"],
                "key": canonical_key,
                "skill_type": data["skill_type"],
                "category": data["category"],
                "related_skills": data.get("related_skills", []),
                "transferable_to": data.get("transferable_to", {}),
                "matched_alias": raw_skill
            }
        return None

    @classmethod
    def evaluate_skill_relation(cls, required_skill: str, candidate_skill: str) -> Tuple[str, float, Optional[str]]:
        """
        Determines relationship between a required job skill and a candidate skill:
        - ('exact', 1.0, None)
        - ('related', confidence, note)
        - ('unrelated', 0.0, None)
        """
        req_norm = cls.normalize_skill(required_skill)
        cand_norm = cls.normalize_skill(candidate_skill)

        # 1. Exact canonical match
        if req_norm and cand_norm and req_norm["key"] == cand_norm["key"]:
            return ("exact", 1.0, f"Exact match for {req_norm['canonical_name']}")

        # Raw string equality fallback
        if required_skill.strip().lower() == candidate_skill.strip().lower():
            return ("exact", 1.0, f"Direct string match for {required_skill}")

        # 2. Check transferability in ontology
        if cand_norm:
            transfers = cand_norm.get("transferable_to", {})
            req_key = req_norm["key"] if req_norm else required_skill.strip().lower()
            
            # Check if candidate skill transfers to required skill
            if req_key in transfers:
                conf = transfers[req_key]
                note = f"{cand_norm['canonical_name']} provides transferable experience toward {required_skill} (transferability confidence: {int(conf * 100)}%). Note: Does not verify advanced specialized proficiency."
                return ("related", conf, note)

            # Check related skills
            cand_related = [r.lower() for r in cand_norm.get("related_skills", [])]
            if req_key in cand_related:
                note = f"{cand_norm['canonical_name']} is conceptually related to {required_skill}. Supplemental practice recommended."
                return ("related", 0.60, note)

        return ("unrelated", 0.0, None)

    @classmethod
    def analyze_skill_overlap(
        cls,
        job_required: List[str],
        job_preferred: List[str],
        candidate_skills: List[str]
    ) -> Dict[str, Any]:
        """
        Compares job requirements with candidate skills using ESCO rules.
        Returns:
          - matched_exact: list of skills with exact matches
          - matched_related: list of dicts with candidate_skill, required_skill, confidence, note
          - missing_mandatory: required skills without exact or related match
          - missing_preferred: preferred skills without exact or related match
          - score: calibrated match percentage (exact=1.0, related=transferable weight)
        """
        cand_set = set(candidate_skills)
        matched_exact: List[str] = []
        matched_related: List[Dict[str, Any]] = []
        missing_mandatory: List[str] = []
        missing_preferred: List[str] = []

        # Process mandatory required skills
        for req in job_required:
            found_exact = False
            best_related = None

            for cand in cand_set:
                rel_type, conf, note = cls.evaluate_skill_relation(req, cand)
                if rel_type == "exact":
                    found_exact = True
                    matched_exact.append(req)
                    break
                elif rel_type == "related":
                    if best_related is None or conf > best_related["confidence"]:
                        best_related = {
                            "required_skill": req,
                            "candidate_skill": cand,
                            "confidence": conf,
                            "note": note,
                            "is_mandatory": True
                        }

            if not found_exact:
                if best_related:
                    matched_related.append(best_related)
                else:
                    missing_mandatory.append(req)

        # Process preferred skills
        for pref in job_preferred:
            found_exact = False
            best_related = None

            for cand in cand_set:
                rel_type, conf, note = cls.evaluate_skill_relation(pref, cand)
                if rel_type == "exact":
                    found_exact = True
                    if pref not in matched_exact:
                        matched_exact.append(pref)
                    break
                elif rel_type == "related":
                    if best_related is None or conf > best_related["confidence"]:
                        best_related = {
                            "required_skill": pref,
                            "candidate_skill": cand,
                            "confidence": conf,
                            "note": note,
                            "is_mandatory": False
                        }

            if not found_exact:
                if best_related:
                    matched_related.append(best_related)
                else:
                    missing_preferred.append(pref)

        # Calibrate overall skill match score
        total_req_count = len(job_required)
        total_pref_count = len(job_preferred)
        
        if total_req_count == 0 and total_pref_count == 0:
            calibrated_score = 100.0 if cand_set else 0.0
        else:
            # Mandatory requirements are 75% of skill score, preferred are 25%
            mandatory_points = 0.0
            for req in job_required:
                if req in matched_exact:
                    mandatory_points += 1.0
                else:
                    rel = next((r for r in matched_related if r["required_skill"] == req and r["is_mandatory"]), None)
                    if rel:
                        mandatory_points += (rel["confidence"] * 0.70)  # Related gets partial credit

            preferred_points = 0.0
            for pref in job_preferred:
                if pref in matched_exact:
                    preferred_points += 1.0
                else:
                    rel = next((r for r in matched_related if r["required_skill"] == pref and not r["is_mandatory"]), None)
                    if rel:
                        preferred_points += (rel["confidence"] * 0.70)

            mandatory_ratio = (mandatory_points / total_req_count) if total_req_count > 0 else 1.0
            preferred_ratio = (preferred_points / total_pref_count) if total_pref_count > 0 else 1.0

            if total_pref_count > 0 and total_req_count > 0:
                calibrated_score = (mandatory_ratio * 75.0) + (preferred_ratio * 25.0)
            elif total_req_count > 0:
                calibrated_score = mandatory_ratio * 100.0
            else:
                calibrated_score = preferred_ratio * 100.0

        return {
            "matched_exact": matched_exact,
            "matched_related": matched_related,
            "missing_mandatory": missing_mandatory,
            "missing_preferred": missing_preferred,
            "skill_match_score": round(calibrated_score, 1),
            "esco_version": ESCO_VERSION,
        }
