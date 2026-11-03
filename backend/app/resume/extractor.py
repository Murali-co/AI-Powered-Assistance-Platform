import re
from typing import List, Dict, Any, Optional

# Lazy-loaded spaCy model
_nlp = None

def get_spacy_model():
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
        except Exception:
            _nlp = None
    return _nlp

# Hardcoded skill taxonomy for validation and matching
SKILL_TAXONOMY = {
    # Programming Languages
    "python": "Python", "javascript": "JavaScript", "typescript": "TypeScript", 
    "golang": "Go", "go": "Go", "rust": "Rust", "c++": "C++", "c#": "C#", 
    "java": "Java", "kotlin": "Kotlin", "swift": "Swift", "ruby": "Ruby", 
    "php": "PHP", "html": "HTML", "css": "CSS", "sql": "SQL", "bash": "Bash", 
    "r": "R", "scala": "Scala", "shell": "Shell",
    
    # Frameworks & Libraries
    "react": "React", "vue": "Vue.js", "angular": "Angular", "nextjs": "Next.js", 
    "svelte": "Svelte", "express": "Express", "fastify": "Fastify", "nestjs": "NestJS", 
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI", "spring": "Spring Boot", 
    "spring boot": "Spring Boot", "rails": "Ruby on Rails", "laravel": "Laravel", 
    "tailwind": "TailwindCSS", "bootstrap": "Bootstrap", "pandas": "Pandas", 
    "numpy": "NumPy", "tensorflow": "TensorFlow", "pytorch": "PyTorch", 
    "keras": "Keras", "scikit-learn": "Scikit-Learn", "scikit learn": "Scikit-Learn",
    "react native": "React Native", "flutter": "Flutter",
    
    # Cloud & DevOps
    "aws": "AWS", "amazon web services": "AWS", "azure": "Azure", "gcp": "GCP", 
    "google cloud": "GCP", "docker": "Docker", "kubernetes": "Kubernetes", "k8s": "Kubernetes", 
    "terraform": "Terraform", "ansible": "Ansible", "jenkins": "Jenkins", 
    "gitlab ci": "GitLab CI", "github actions": "GitHub Actions", "nginx": "Nginx", 
    "apache": "Apache", "ci/cd": "CI/CD", "prometheus": "Prometheus", "grafana": "Grafana",
    
    # Databases & Vector DBs
    "postgresql": "PostgreSQL", "postgres": "PostgreSQL", "mysql": "MySQL", 
    "mongodb": "MongoDB", "redis": "Redis", "sqlite": "SQLite", "cassandra": "Cassandra", 
    "elasticsearch": "Elasticsearch", "dynamodb": "DynamoDB", "mariadb": "MariaDB", 
    "oracle": "Oracle", "firestore": "Firestore", "chromadb": "ChromaDB", 
    "chroma": "ChromaDB", "pinecone": "Pinecone", "supabase": "Supabase", "milvus": "Milvus",
    
    # Tools & Methodologies
    "git": "Git", "github": "GitHub", "gitlab": "GitLab", "postman": "Postman", 
    "jira": "Jira", "confluence": "Confluence", "linux": "Linux", "windows": "Windows", 
    "macos": "macOS", "vscode": "VS Code", "docker-compose": "Docker Compose", 
    "graphql": "GraphQL", "grpc": "gRPC", "rest api": "REST API", "websockets": "WebSockets",
    "agile": "Agile", "scrum": "Scrum", "kanban": "Kanban", "microservices": "Microservices",
    "machine learning": "Machine Learning", "deep learning": "Deep Learning", "nlp": "NLP",
    "llm": "LLM", "generative ai": "Generative AI",
    
    # Soft Skills
    "communication": "Communication", "leadership": "Leadership", "teamwork": "Teamwork", 
    "problem solving": "Problem Solving", "critical thinking": "Critical Thinking", 
    "time management": "Time Management", "collaboration": "Collaboration", 
    "presentation": "Presentation", "mentoring": "Mentoring", "negotiation": "Negotiation"
}

class SkillExtractor:
    @staticmethod
    def extract_skills(text: str, sections: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        extracted: Dict[str, Dict[str, Any]] = {}
        text_lower = text.lower()

        # 1. Regex Match against Taxonomy
        for keyword, standardized_name in SKILL_TAXONOMY.items():
            # Use boundary patterns. Be careful with characters like C++ or C#
            escaped_kw = re.escape(keyword)
            # Adjust boundaries for keywords ending with ++ or #
            if keyword.endswith("++") or keyword.endswith("#"):
                pattern = rf"\b{escaped_kw}"
            else:
                pattern = rf"\b{escaped_kw}\b"
                
            # Case sensitivity for short/common word exceptions
            if keyword in ["go", "r"]:
                pattern_cs = rf"\b{keyword.capitalize()}\b"
                if re.search(pattern_cs, text):
                    extracted[standardized_name] = {
                        "skill": standardized_name,
                        "confidence": 0.85,
                        "source": "taxonomy_regex"
                    }
            else:
                if re.search(pattern, text_lower):
                    extracted[standardized_name] = {
                        "skill": standardized_name,
                        "confidence": 0.85,
                        "source": "taxonomy_regex"
                    }

        # 2. Section Boost: If skill found in "skills" section, raise confidence to 0.95
        if sections and "skills" in sections and sections["skills"]:
            skills_sec_lower = sections["skills"].lower()
            for skill_name in list(extracted.keys()):
                # Find the corresponding keyword
                matching_kw = [k for k, v in SKILL_TAXONOMY.items() if v == skill_name]
                for kw in matching_kw:
                    escaped_kw = re.escape(kw)
                    pattern = rf"\b{escaped_kw}" if (kw.endswith("++") or kw.endswith("#")) else rf"\b{escaped_kw}\b"
                    if re.search(pattern, skills_sec_lower):
                        extracted[skill_name]["confidence"] = 0.95
                        extracted[skill_name]["source"] = "skills_section"
                        break

        # 3. spaCy NER Extraction for entities like ORG, PRODUCT, WORK_OF_ART
        try:
            nlp = get_spacy_model()
            if nlp is not None:
                doc = nlp(text)
                for ent in doc.ents:
                    if ent.label_ in ["ORG", "PRODUCT", "WORK_OF_ART"]:
                        ent_text = ent.text.strip()
                        ent_lower = ent_text.lower()
                        # If this is inside taxonomy but not yet extracted
                        if ent_lower in SKILL_TAXONOMY:
                            std_name = SKILL_TAXONOMY[ent_lower]
                            if std_name not in extracted:
                                extracted[std_name] = {
                                    "skill": std_name,
                                    "confidence": 0.75,
                                    "source": "spacy_ner"
                                }
                            else:
                                # Boost confidence if also found via spaCy NER
                                current_conf = float(extracted[std_name]["confidence"])
                                extracted[std_name]["confidence"] = min(0.99, current_conf + 0.05)
        except Exception as e:
            print(f"spaCy NER skill extraction warning: {e}")

        return list(extracted.values())
