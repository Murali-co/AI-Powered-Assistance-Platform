from typing import Optional
from app.llm.ollama_client import OllamaClient
from app.services.privacy_service import PrivacyPreservingEngine

class CoverLetterGenerator:
    @staticmethod
    async def generate(resume_text: str, target_role: str, company_name: Optional[str] = None, tone: str = "formal") -> str:
        system_prompts = {
            "formal": (
                "You are a professional resume writer. Write a polished, highly professional cover letter. "
                "Maintain a respectful, business-standard tone, showcasing strong alignment with the target role."
            ),
            "casual": (
                "You are an approachable, modern career coach. Write a conversational, engaging, yet polite cover letter. "
                "Make it sound natural, enthusiastic, and confident, avoiding stuffy business jargon."
            ),
            "creative": (
                "You are a creative storyteller. Write an imaginative, unique cover letter that stands out. "
                "Highlight the candidate's passion and narrative journey, making it memorable and storytelling-driven."
            )
        }
        
        system_prompt = system_prompts.get(tone.lower(), system_prompts["formal"])
        company_phrase = f" at {company_name}" if company_name else ""
        
        # Anonymize PII before constructing prompt to protect candidate privacy
        anon_result = PrivacyPreservingEngine.anonymize_text(resume_text or "")
        anonymized_resume = anon_result.get("anonymized_text") or (resume_text or "")
        mapping = anon_result.get("mapping", {})

        prompt = f"""
Candidate Resume Details:
{anonymized_resume}

Target Role: {target_role}{company_phrase}
Tone: {tone}

Please write a cover letter of 3 to 4 paragraphs tailored to this candidate and target position. 
- Paragraph 1: Catchy introduction explaining the candidate's interest in the role and company.
- Paragraph 2: Core strengths and technical skill highlights from the candidate's experience that directly align with the job requirements.
- Paragraph 3: A description of how they solve problems and work in teams, referencing their achievements.
- Paragraph 4: Strong concluding statement expressing enthusiasm for an interview and a call to action.

Make sure the output contains ONLY the plain-text cover letter. Do not include any meta-commentary, salutations outside the cover letter, or markdown formatting blocks (like ```).
"""

        try:
            cover_letter = await OllamaClient.generate(
                prompt=prompt,
                system=system_prompt
            )
            if mapping:
                cover_letter = PrivacyPreservingEngine.restore_text(cover_letter, mapping)
            return cover_letter.strip()
        except Exception as e:
            print(f"Error generating cover letter: {e}")
            return (
                f"Dear Hiring Team,\n\nI am writing to express my strong interest in the {target_role} position. "
                f"Based on my professional background and technical skills, I believe I would be a great fit for the role. "
                f"I look forward to discussing how my experiences match your team's goals.\n\nSincerely,\n[Your Name]"
            )
