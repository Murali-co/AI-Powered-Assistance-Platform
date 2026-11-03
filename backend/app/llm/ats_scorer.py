"""
ATS (Applicant Tracking System) Score Simulator
Analyzes resume against job description and provides match scoring
"""

import re
from typing import List, Dict, Tuple
from app.llm.ollama_client import OllamaClient
from app.services.privacy_service import PrivacyPreservingEngine

class ATSScorer:
    """Analyze resume against JD using keyword detection and ATS optimization"""
    
    # Common ATS keywords to detect
    TECHNICAL_SKILLS = {
        'python', 'javascript', 'java', 'c++', 'c#', 'go', 'rust', 'kotlin',
        'sql', 'postgresql', 'mysql', 'mongodb', 'redis', 'elasticsearch',
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'terraform',
        'react', 'angular', 'vue', 'node', 'django', 'flask', 'fastapi',
        'git', 'jenkins', 'gitlab', 'github', 'ci/cd', 'devops',
        'machine learning', 'deep learning', 'nlp', 'tensorflow', 'pytorch',
    }
    
    SOFT_SKILLS = {
        'leadership', 'communication', 'teamwork', 'collaboration',
        'problem solving', 'critical thinking', 'project management',
        'agile', 'scrum', 'kanban', 'analytical', 'strategic',
    }
    
    REQUIRED_SECTIONS = {
        'experience', 'education', 'skills', 'projects', 'summary', 'contact'
    }
    
    @staticmethod
    def extract_keywords(text: str) -> set:
        """Extract keywords from text (lowercase)"""
        text_lower = text.lower()
        # Remove special characters but keep spaces
        text_clean = re.sub(r'[^a-z0-9\s+#/]', ' ', text_lower)
        words = text_clean.split()
        return set(words)
    
    @staticmethod
    def calculate_keyword_match(resume_text: str, job_description: str) -> Tuple[float, List[str]]:
        """
        Calculate how many JD keywords appear in resume
        Returns: (match_percentage, matched_keywords)
        """
        resume_keywords = ATSScorer.extract_keywords(resume_text)
        jd_keywords = ATSScorer.extract_keywords(job_description)
        
        # Find matching keywords
        matched = resume_keywords.intersection(jd_keywords)
        
        # Also check for variations (e.g., "python" vs "python3")
        technical_matches = resume_keywords.intersection(ATSScorer.TECHNICAL_SKILLS)
        soft_skill_matches = resume_keywords.intersection(ATSScorer.SOFT_SKILLS)
        
        match_percentage = len(matched) / len(jd_keywords) * 100 if jd_keywords else 0
        
        return min(100, match_percentage), sorted(list(matched))
    
    @staticmethod
    def detect_experience_level(resume_text: str) -> Tuple[str, int]:
        """
        Detect years of experience from resume
        Returns: (level_name, estimated_years)
        """
        text_lower = resume_text.lower()
        
        # Look for experience patterns
        experience_patterns = [
            (r'(\d+)\+?\s*years?', 1),
            (r'over\s+(\d+)\s*years?', 1),
            (r'(\d+)\s*yrs?', 1),
        ]
        
        years = 0
        for pattern, group in experience_patterns:
            matches = re.findall(pattern, text_lower)
            if matches:
                years = max(years, int(matches[-1]))
        
        # Classify level
        if years >= 10:
            level = 'Senior'
        elif years >= 5:
            level = 'Mid-Level'
        elif years >= 2:
            level = 'Junior'
        else:
            level = 'Entry-Level'
        
        return level, years
    
    @staticmethod
    def check_ats_formatting(resume_text: str) -> Tuple[float, List[str]]:
        """
        Check for ATS-friendly formatting
        Returns: (score, issues_found)
        """
        issues = []
        score = 100
        
        # Check for required sections
        text_lower = resume_text.lower()
        found_sections = 0
        
        for section in ATSScorer.REQUIRED_SECTIONS:
            if section in text_lower:
                found_sections += 1
            else:
                issues.append(f"Missing '{section}' section")
                score -= 5
        
        # Check for suspicious formatting
        if resume_text.count('\n') < 5:
            issues.append("Resume seems too short or missing line breaks")
            score -= 10
        
        if len(resume_text) < 200:
            issues.append("Resume is too short for proper ATS analysis")
            score -= 15
        
        # Check for common ATS issues
        if '•' in resume_text or '◦' in resume_text:
            # Bullets are good for ATS
            pass
        else:
            issues.append("Consider using bullet points for better formatting")
            score -= 5
        
        # Check for excessive special characters (bad for ATS)
        special_chars = len(re.findall(r'[^a-zA-Z0-9\s.,;:\-\n]', resume_text))
        if special_chars > len(resume_text) * 0.1:
            issues.append("Too many special characters (ATS may have issues parsing)")
            score -= 10
        
        return max(0, score), issues
    
    @staticmethod
    def calculate_skills_match(resume_text: str, job_description: str) -> Tuple[float, Dict]:
        """
        Calculate skills match between resume and JD
        Returns: (match_percentage, skills_breakdown)
        """
        resume_keywords = ATSScorer.extract_keywords(resume_text)
        jd_keywords = ATSScorer.extract_keywords(job_description)
        
        tech_matches = resume_keywords.intersection(ATSScorer.TECHNICAL_SKILLS).intersection(jd_keywords)
        soft_matches = resume_keywords.intersection(ATSScorer.SOFT_SKILLS).intersection(jd_keywords)
        
        breakdown = {
            'technical_matched': len(tech_matches),
            'technical_keywords': list(tech_matches),
            'soft_matched': len(soft_matches),
            'soft_keywords': list(soft_matches),
        }
        
        total_jd_skills = len(jd_keywords.intersection(ATSScorer.TECHNICAL_SKILLS.union(ATSScorer.SOFT_SKILLS)))
        if total_jd_skills == 0:
            match_percentage: float = 0.0
        else:
            match_percentage = (len(tech_matches) + len(soft_matches)) / total_jd_skills * 100.0
        
        return int(min(100.0, match_percentage)), breakdown
    
    @staticmethod
    async def generate_ats_score_detailed(resume_text: str, job_description: str) -> Dict:
        """
        Generate comprehensive ATS score analysis
        Returns detailed breakdown and improvement suggestions
        """
        # 1. Keyword matching (30%)
        keyword_score, matched_keywords = ATSScorer.calculate_keyword_match(
            resume_text, job_description
        )
        keyword_weight = (keyword_score / 100) * 30
        
        # 2. Skills matching (30%)
        skills_score, skills_breakdown = ATSScorer.calculate_skills_match(
            resume_text, job_description
        )
        skills_weight = (skills_score / 100) * 30
        
        # 3. Experience level (20%)
        exp_level, exp_years = ATSScorer.detect_experience_level(resume_text)
        exp_score = 70  # Default moderate score
        exp_weight = (exp_score / 100) * 20
        
        # 4. ATS formatting (20%)
        format_score, format_issues = ATSScorer.check_ats_formatting(resume_text)
        format_weight = (format_score / 100) * 20
        
        # Calculate total score
        total_score = keyword_weight + skills_weight + exp_weight + format_weight
        
        # Generate AI-powered suggestions with anonymized candidate resume
        jd_excerpt = job_description[:500]  # First 500 chars for context
        anon_resume = PrivacyPreservingEngine.anonymize_text(resume_text).get("anonymized_text", resume_text)
        resume_excerpt = anon_resume[:500]
        
        suggestion_prompt = f"""
        Analyze this job match and provide 3 specific improvements for the resume:
        
        Job Description: {jd_excerpt}
        Resume: {resume_excerpt}
        
        Provide actionable suggestions to improve ATS compatibility.
        Keep response under 200 words.
        """
        
        suggestions = []
        try:
            async for token in OllamaClient.generate_stream(suggestion_prompt):
                suggestions.append(token)
        except Exception as e:
            suggestions = [
                "Add more quantifiable achievements and metrics",
                "Include industry-specific keywords from the job posting",
                "Use standard section headers (Experience, Education, Skills)"
            ]
        
        return {
            "overall_score": int(total_score),
            "breakdown": {
                "keyword_match": {
                    "score": int(keyword_score),
                    "weight": 30,
                    "contribution": int(keyword_weight)
                },
                "skills_match": {
                    "score": int(skills_score),
                    "weight": 30,
                    "contribution": int(skills_weight),
                    "details": skills_breakdown
                },
                "experience_level": {
                    "score": int(exp_score),
                    "weight": 20,
                    "contribution": int(exp_weight),
                    "level": exp_level,
                    "years": exp_years
                },
                "ats_formatting": {
                    "score": int(format_score),
                    "weight": 20,
                    "contribution": int(format_weight),
                    "issues": format_issues
                }
            },
            "matched_keywords": matched_keywords[:20],  # Top 20
            "suggestions": ''.join(suggestions) if suggestions else "Consider tailoring your resume for this specific role.",
            "pass_ats": total_score >= 70,
            "recommendation": (
                "This resume has excellent ATS compatibility" if total_score >= 80
                else "Good ATS score, but could be improved" if total_score >= 70
                else "Consider revising resume for better ATS parsing"
            )
        }
