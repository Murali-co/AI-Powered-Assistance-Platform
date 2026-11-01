import re
import unicodedata
from typing import Dict, List

class ResumeCleaner:
    @staticmethod
    def clean_text(text: str) -> str:
        # Normalize unicode
        text = unicodedata.normalize("NFKC", text)
        
        # Remove page numbers (e.g., "Page 1 of 2", "Page 2", "1 / 3")
        text = re.sub(r'(?i)\bpage\s+\d+(\s+of\s+\d+)?\b', '', text)
        text = re.sub(r'\b\d+\s*/\s*\d+\b', '', text)
        
        # Replace multiple spaces with a single space (keep newlines)
        lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in text.splitlines()]
        
        # Remove empty lines
        lines = [line for line in lines if line]
        
        return "\n".join(lines)

    @classmethod
    def segment_sections(cls, text: str) -> Dict[str, str]:
        cleaned = cls.clean_text(text)
        lines = cleaned.splitlines()
        
        # Define header categories and regex patterns
        patterns = {
            "summary": re.compile(r'(?i)^\s*(summary|professional summary|about me|profile|objective|career objective|about)\s*:??\s*$'),
            "experience": re.compile(r'(?i)^\s*(experience|work experience|employment|work history|professional experience|employment history)\s*:??\s*$'),
            "education": re.compile(r'(?i)^\s*(education|academic background|academic history|qualifications)\s*:??\s*$'),
            "skills": re.compile(r'(?i)^\s*(skills|technical skills|key skills|core competencies|expertise|technologies)\s*:??\s*$'),
            "projects": re.compile(r'(?i)^\s*(projects|academic projects|key projects|personal projects)\s*:??\s*$'),
            "certifications": re.compile(r'(?i)^\s*(certifications|licenses|certifications & licenses|awards|achievements)\s*:??\s*$')
        }
        
        sections: Dict[str, List[str]] = {
            "summary": [],
            "experience": [],
            "education": [],
            "skills": [],
            "projects": [],
            "certifications": []
        }
        
        current_section = "summary"  # Default section
        
        for line in lines:
            # Check if this line matches a header
            matched = False
            for sec_name, pattern in patterns.items():
                if pattern.match(line):
                    current_section = sec_name
                    matched = True
                    break
            
            if matched:
                continue
                
            # If not a header, append to the active section
            sections[current_section].append(line)
            
        # Reconstruct texts
        result = {}
        for sec_name, content in sections.items():
            result[sec_name] = "\n".join(content).strip()
            
        # Fallback: if everything is in "summary" and no headers were matched, keep the original text as summary
        return result
