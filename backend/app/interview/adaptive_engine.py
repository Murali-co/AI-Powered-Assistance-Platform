import json
import re
from typing import Dict, Any, List, Optional, Tuple
from app.llm.ollama_client import OllamaClient
from app.services.privacy_service import PrivacyPreservingEngine


class AdaptiveInterviewEngine:
    """
    AI Powered Assistance Platform Adaptive AI Interview Coach Engine:
    - Personalized question generation grounded in candidate verified profile and job spec
    - Dual rubric evaluation: STAR (Situation, Task, Action, Result) for behavioral;
      Technical rubric (correctness, depth, architecture/trade-offs, communication) for technical
    - Deterministic difficulty progression (Levels 1-5) based on empirical scoring thresholds
    - Evidence gap detection with targeted follow-up generation
    - Non-revealing scaffolding and hints
    """

    DIFFICULTY_LABELS = {
        1: "Foundational / Junior",
        2: "Associate",
        3: "Mid-Level Professional",
        4: "Senior Specialist",
        5: "Staff / Principal / Architect"
    }

    @classmethod
    def determine_question_type(cls, question: str, interview_mode: Optional[str] = None) -> str:
        """
        Classifies whether question requires STAR behavioral rubric or technical rubric.
        """
        q_lower = question.lower()
        mode_lower = (interview_mode or "").lower()

        if "behavioral" in mode_lower:
            return "behavioral"
        if "technical" in mode_lower or "coding" in mode_lower:
            return "technical"
        if "project" in mode_lower:
            return "project-based"

        # Auto-detect from question phrasing
        star_triggers = [
            "tell me about a time", "describe a situation", "give an example of",
            "how did you handle", "walk me through a time", "conflict", "leadership",
            "mistake", "deadline", "challenge you faced", "disagreement"
        ]
        if any(trigger in q_lower for trigger in star_triggers):
            return "behavioral"
        return "technical"

    @classmethod
    async def generate_question(
        cls,
        job_title: str,
        job_description: str,
        verified_skills: List[str],
        skill_gaps: List[str],
        interview_mode: str,
        difficulty_level: int,
        topics_covered: List[str],
        is_first: bool = False,
        follow_up_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates a targeted interview question using job context and candidate evidence.
        Never reveals expected answers upfront.
        """
        diff_label = cls.DIFFICULTY_LABELS.get(difficulty_level, "Mid-Level Professional")
        
        prompt = f"""
You are an expert AI Interview Coach and senior technical hiring manager.
Your task is to conduct an adaptive interview for the position: '{job_title}'.

Target Role & Job Description:
{job_description[:1200] if job_description else job_title}

Candidate Verified Skills:
{", ".join(verified_skills[:15]) if verified_skills else "General technical skills"}

Identified Skill Gaps to probe:
{", ".join(skill_gaps[:5]) if skill_gaps else "None flagged"}

Interview Mode: {interview_mode}
Difficulty Level: {difficulty_level}/5 ({diff_label})
Topics Already Covered: {", ".join(topics_covered) if topics_covered else "None"}
{"Follow-up focus required: " + follow_up_reason if follow_up_reason else ""}

Instructions:
1. Formulate a SINGLE relevant interview question suited for difficulty level {difficulty_level}.
2. Ensure the question tests real candidate evidence or explores an identified skill gap.
3. Do NOT repeat any topic already covered in: {topics_covered}.
4. Do NOT reveal expected answers, solutions, or evaluation criteria in the question.
5. Return JSON ONLY with keys: "question", "topic", "question_type" (behavioral or technical).
Example format:
{{"question": "Can you describe a scenario where you optimized a slow SQL query in production?", "topic": "Database Optimization", "question_type": "technical"}}
"""
        # Default fallback if LLM is offline or times out
        fallback_topic = "System Architecture" if difficulty_level >= 4 else "Core Competencies"
        fallback_q = (
            f"Could you walk me through how you design and implement robust APIs in production, and how you handle error resilience?"
            if interview_mode != "behavioral"
            else f"Can you describe a challenging project situation where you had to balance tight deadlines with code quality?"
        )
        
        raw_response = ""
        try:
            raw_response = await OllamaClient.generate(prompt, format="json", think=False)
            cleaned = raw_response.strip()
            if "```" in cleaned:
                parts = cleaned.split("```")
                for p in parts:
                    p_strip = p.strip()
                    if p_strip.startswith("json\n"):
                        cleaned = p_strip[5:]
                        break
                    elif p_strip.startswith("{"):
                        cleaned = p_strip
                        break
            parsed = json.loads(cleaned)
            return {
                "question": parsed.get("question", fallback_q),
                "topic": parsed.get("topic", fallback_topic),
                "question_type": parsed.get("question_type", cls.determine_question_type(fallback_q, interview_mode)),
                "difficulty_level": difficulty_level
            }
        except Exception:
            if raw_response and len(raw_response.strip()) > 5 and not raw_response.strip().startswith("{"):
                plain_q = raw_response.strip().strip('"').strip("'")
                return {
                    "question": plain_q,
                    "topic": fallback_topic,
                    "question_type": cls.determine_question_type(plain_q, interview_mode),
                    "difficulty_level": difficulty_level
                }
            return {
                "question": fallback_q,
                "topic": fallback_topic,
                "question_type": cls.determine_question_type(fallback_q, interview_mode),
                "difficulty_level": difficulty_level
            }

    @classmethod
    async def evaluate_answer(
        cls,
        question: str,
        answer: str,
        question_type: str,
        difficulty_level: int
    ) -> Dict[str, Any]:
        """
        Evaluates candidate answer against appropriate rubric:
        - Behavioral: Situation, Task, Action, Result (STAR breakdown)
        - Technical: Relevance, Technical Depth, Completeness, Evidence, Communication
        """
        if not answer or len(answer.strip()) < 10:
            return {
                "score": 25,
                "strengths": ["Answer attempted"],
                "areas_to_improve": ["Answer is too brief to evaluate properly. Provide specific details and context."],
                "rubric_scores": {
                    "relevance": 30,
                    "clarity_and_structure": 25,
                    "technical_depth": 20,
                    "completeness": 20,
                    "evidence_specificity": 20,
                    "communication": 30
                },
                "star_elements": {
                    "situation": False,
                    "task": False,
                    "action": False,
                    "result": False
                } if question_type == "behavioral" else None,
                "missing_elements": ["Context/Situation", "Specific Actions", "Measurable Outcome"],
                "suggested_structure": "Structure your response with the challenge, what you specifically executed, and the measurable outcome achieved.",
                "practice_recommendation": "Try elaborating with concrete technical steps and quantifiable results.",
                "follow_up_needed": True,
                "follow_up_reason": "Answer lacked sufficient detail and evidence."
            }

        prompt = f"""
You are a senior interview evaluator. Evaluate the candidate's answer to the following question.

Question: {question}
Question Type: {question_type}
Difficulty Level: {difficulty_level}/5

Candidate's Answer:
{answer}

Evaluation Rubric Guidelines:
If behavioral:
- Situation: Did they establish context?
- Task: Did they identify their specific role/responsibility?
- Action: Did they articulate what they personally did?
- Result: Did they describe quantifiable impact or key lessons learned?

If technical:
- Technical correctness and depth for difficulty level {difficulty_level}.
- Architecture choices and trade-off considerations.
- Handling edge cases and failure modes.
- Clarity of explanation.

Output ONLY valid JSON matching this schema:
{{
    "score": 82,
    "strengths": ["Clear explanation of personal actions", "Quantified latency reduction"],
    "areas_to_improve": ["Could elaborate more on initial system context", "Mention monitoring"],
    "rubric_scores": {{
        "relevance": 85,
        "clarity_and_structure": 80,
        "technical_depth": 80,
        "completeness": 75,
        "evidence_specificity": 85,
        "communication": 85
    }},
    "star_elements": {{
        "situation": true,
        "task": true,
        "action": true,
        "result": true
    }},
    "missing_elements": [],
    "suggested_structure": "Example structure: Outline the architecture bottleneck -> Detail the caching layer implemented -> Share the 40% speedup result.",
    "practice_recommendation": "Focus on highlighting preventive observability in future answers.",
    "follow_up_needed": false,
    "follow_up_reason": null
}}
"""
        try:
            res = await OllamaClient.generate(prompt, format="json", think=False)
            cleaned = res.strip()
            if "```" in cleaned:
                parts = cleaned.split("```")
                for p in parts:
                    p_strip = p.strip()
                    if p_strip.startswith("json\n"):
                        cleaned = p_strip[5:]
                        break
                    elif p_strip.startswith("{"):
                        cleaned = p_strip
                        break
            parsed = json.loads(cleaned)
            score = max(0, min(100, int(parsed.get("score", 70))))
            return {
                "score": score,
                "strengths": parsed.get("strengths", ["Articulated core concepts"]),
                "areas_to_improve": parsed.get("areas_to_improve", ["Add more quantifiable results"]),
                "rubric_scores": parsed.get("rubric_scores", {
                    "relevance": score,
                    "clarity_and_structure": score,
                    "technical_depth": score,
                    "completeness": score,
                    "evidence_specificity": score,
                    "communication": score
                }),
                "star_elements": parsed.get("star_elements") if question_type == "behavioral" else None,
                "missing_elements": parsed.get("missing_elements", []),
                "suggested_structure": parsed.get("suggested_structure", "Context -> Personal Action -> Verified Outcome"),
                "practice_recommendation": parsed.get("practice_recommendation", "Practice framing answers with measurable business/technical impact."),
                "follow_up_needed": bool(parsed.get("follow_up_needed", score < 60)),
                "follow_up_reason": parsed.get("follow_up_reason")
            }
        except Exception:
            # Deterministic heuristic evaluation fallback
            word_count = len(answer.split())
            score = 75
            has_numbers = bool(re.search(r'\d+', answer))
            has_first_person = bool(re.search(r'\b(I|my|we|built|implemented|designed|led|solved)\b', answer, re.IGNORECASE))
            if word_count > 60 and has_numbers and has_first_person:
                score = 85
            elif word_count < 30:
                score = 55

            return {
                "score": score,
                "strengths": ["Demonstrates subject familiarity", "Addresses core inquiry"],
                "areas_to_improve": ["Include more specific metrics and technical trade-offs"],
                "rubric_scores": {
                    "relevance": score,
                    "clarity_and_structure": score - 5,
                    "technical_depth": score,
                    "completeness": score - 5,
                    "evidence_specificity": score if has_numbers else score - 15,
                    "communication": score
                },
                "star_elements": {
                    "situation": True,
                    "task": True,
                    "action": has_first_person,
                    "result": has_numbers
                } if question_type == "behavioral" else None,
                "missing_elements": [] if (has_numbers and has_first_person) else ["Quantifiable outcome or metrics"],
                "suggested_structure": "Clearly state the situation, your direct responsibility, specific steps taken, and the end result.",
                "practice_recommendation": "Include specific percentages, timeframes, or scale metrics in answers.",
                "follow_up_needed": score < 60,
                "follow_up_reason": "Need more specific technical evidence and outcomes" if score < 60 else None
            }

    @classmethod
    def compute_adaptive_transition(
        cls,
        current_difficulty: int,
        latest_score: int,
        recent_scores: List[int]
    ) -> Tuple[int, str]:
        """
        Deterministic, testable adaptive difficulty progression:
        - Increases difficulty if current answer >= 80 and average recent score >= 75 (max 5)
        - Decreases difficulty or scaffolds if current answer < 50 (min 1)
        - Maintains difficulty level if performance is within solid range (50-79)
        """
        all_scores = recent_scores + [latest_score]
        avg_score = sum(all_scores) / len(all_scores)

        if latest_score >= 80 and avg_score >= 75:
            new_difficulty = min(5, current_difficulty + 1)
            transition_reason = (
                f"Consistently strong performance ({latest_score}%). Advanced to Level {new_difficulty} ({cls.DIFFICULTY_LABELS[new_difficulty]})."
                if new_difficulty > current_difficulty
                else f"Maintained peak difficulty Level 5 ({cls.DIFFICULTY_LABELS[5]})."
            )
        elif latest_score < 50:
            new_difficulty = max(1, current_difficulty - 1)
            transition_reason = (
                f"Candidate encountered difficulty ({latest_score}%). Scaffolding adjusted to Level {new_difficulty} ({cls.DIFFICULTY_LABELS[new_difficulty]})."
                if new_difficulty < current_difficulty
                else f"Provided scaffolding at foundational Level 1."
            )
        else:
            new_difficulty = current_difficulty
            transition_reason = f"Solid performance ({latest_score}%). Maintained Level {current_difficulty} ({cls.DIFFICULTY_LABELS[current_difficulty]})."

        return new_difficulty, transition_reason

    @classmethod
    def generate_hint(cls, question: str, question_type: str, difficulty_level: int) -> str:
        """
        Provides a constructive scaffold hint without revealing the expected answer.
        """
        if question_type == "behavioral":
            return (
                "Scaffolding Hint: Frame your response using the STAR method. "
                "Begin with the context (Situation & Task), detail your personal contribution (Action), "
                "and conclude with the outcome or what you learned (Result)."
            )
        else:
            return (
                f"Scaffolding Hint: For a Level {difficulty_level} technical question, "
                "first clarify requirements, identify key architectural trade-offs (e.g. latency vs. consistency), "
                "and explain how you would monitor and handle failure modes."
            )
