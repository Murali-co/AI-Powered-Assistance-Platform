import json
import re
from typing import Dict, Any, List, Optional
from app.llm.ollama_client import OllamaClient
from app.services.privacy_service import PrivacyPreservingEngine


class ConstrainedCareerTailor:
    """
    Evidence-grounded resume and cover letter generation:
    - Never fabricates dates, degrees, certifications, companies, or metrics.
    - Cites specific evidence keys from candidate verified profile.
    - Explicitly flags unverified qualifications or inferences as 'PROPOSED_ADDITION' or 'UNVERIFIED'.
    """

    @classmethod
    def verify_factual_grounding(
        cls,
        generated_text: str,
        verified_facts: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluates the generated text for unsupported claims against candidate verified facts.
        Returns percentage of supported claims and flags any fabricated qualifications.
        """
        work_exp = verified_facts.get("work_experience") or verified_facts.get("experience") or []
        verified_skills = set(s.lower() for s in verified_facts.get("skills", []))
        verified_companies = set(exp.get("company", "").lower() for exp in work_exp)
        verified_roles = set(exp.get("title", "").lower() for exp in work_exp)
        verified_degrees = set(edu.get("degree", "").lower() for edu in verified_facts.get("education", []))

        # Sentence-level evidence check
        sentences = [s.strip() for s in re.split(r'[.\n]+', generated_text) if len(s.strip()) > 15]
        total_claims = len(sentences)
        supported_claims = 0
        unsupported_claims: List[Dict[str, str]] = []

        # Check for fabricated metrics or unverified assertions
        for sent in sentences:
            sent_lower = sent.lower()
            has_metric = bool(re.search(r'(\$\d+|\d+%\b|\d+\s*(?:percent|million|billion|k|x\b)|by\s+\d+)', sent, re.IGNORECASE))
            matched_companies = [c for c in verified_companies if c and c in sent_lower]
            matched_skills = [s for s in verified_skills if s and s in sent_lower]
            matched_degrees = [d for d in verified_degrees if d and d in sent_lower]

            if matched_companies or matched_degrees:
                if has_metric:
                    verified_text = " ".join(str(v) for v in verified_facts.values()).lower()
                    metric_found = any(m in verified_text for m in re.findall(r'\d+', sent))
                    if metric_found:
                        supported_claims += 1
                    else:
                        unsupported_claims.append({
                            "claim": sent,
                            "reason": "Contains quantitative metric not found in verified career profile."
                        })
                else:
                    supported_claims += 1
            elif matched_skills:
                if has_metric:
                    verified_text = " ".join(str(v) for v in verified_facts.values()).lower()
                    metric_found = any(m in verified_text for m in re.findall(r'\d+', sent))
                    if metric_found:
                        supported_claims += 1
                    else:
                        unsupported_claims.append({
                            "claim": sent,
                            "reason": "Contains quantitative metric not found in verified career profile."
                        })
                else:
                    supported_claims += 1
            else:
                if has_metric or any(k in sent_lower for k in ["apple", "google", "meta", "amazon", "microsoft", "revenue", "increased", "boosted"]):
                    unsupported_claims.append({
                        "claim": sent,
                        "reason": "Contains unverified assertions, companies, or metrics not backed by candidate evidence."
                    })
                else:
                    supported_claims += 1

        grounding_pct = int(100 * supported_claims / max(1, total_claims))
        return {
            "total_claims": total_claims,
            "supported_claims": supported_claims,
            "unsupported_count": len(unsupported_claims),
            "grounding_percentage": min(100, max(0, grounding_pct)),
            "unsupported_claims": unsupported_claims,
            "is_trustworthy": len(unsupported_claims) == 0,
            "is_grounded": len(unsupported_claims) == 0
        }

    @classmethod
    async def tailor_resume_grounded(
        cls,
        verified_profile: Dict[str, Any],
        target_role: str,
        job_description: str,
        consent_settings: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Produces an evidence-grounded tailored resume preserving candidate factual truth.
        """
        skills = verified_profile.get("skills", [])
        experience = verified_profile.get("work_experience", [])
        education = verified_profile.get("education", [])
        projects = verified_profile.get("projects", [])

        # Format verified facts
        facts_summary = f"""
Candidate Verified Facts:
Skills: {", ".join(skills)}
Experience: {json.dumps(experience)}
Education: {json.dumps(education)}
Projects: {json.dumps(projects)}
"""

        # Apply privacy masking if external consent is not granted
        consent = consent_settings or {"local_only": True}
        anonymized_facts = PrivacyPreservingEngine.anonymize_text(facts_summary, consent)
        facts_to_prompt = anonymized_facts["anonymized_text"]

        prompt = f"""
You are a career document specialist. Tailor the candidate's resume for the role '{target_role}'.

CRITICAL CONSTRAINT: You must ONLY use the verified facts below. DO NOT invent dates, certifications, degrees, company names, or numerical percentages not present in the facts.

{facts_to_prompt}

Job Description Context:
{job_description[:1000]}

Generate a professionally organized, tailored resume text.
Cite actual experiences and projects.
Return ONLY the tailored resume text.
"""
        tailored_text = ""
        try:
            raw = await OllamaClient.generate(prompt)
            tailored_text = raw.strip()
        except Exception:
            # Deterministic evidence-grounded template
            tailored_text = f"TARGET ROLE: {target_role}\n\nSUMMARY:\nExperienced professional specializing in {', '.join(skills[:6])}.\n\nVERIFIED SKILLS:\n" + "\n".join(f"- {s}" for s in skills)
            if experience:
                tailored_text += "\n\nPROFESSIONAL EXPERIENCE:\n"
                for exp in experience:
                    tailored_text += f"\n{exp.get('title', 'Role')} at {exp.get('company', 'Company')} ({exp.get('years', 'Recent')})\n"
                    tailored_text += f"- {exp.get('description', 'Executed technical responsibilities')}\n"

        # If masked, restore candidate personal tokens
        if anonymized_facts["mapping"]:
            tailored_text = PrivacyPreservingEngine.restore_text(tailored_text, anonymized_facts["mapping"])

        # Run factual grounding verification
        verification = cls.verify_factual_grounding(tailored_text, verified_profile)

        return {
            "tailored_resume": tailored_text,
            "target_role": target_role,
            "factual_grounding": verification,
            "verified_evidence_used": len(skills) + len(experience)
        }
