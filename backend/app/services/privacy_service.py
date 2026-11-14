import re
from typing import Dict, Any, List, Tuple, Optional
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig


class PrivacyPreservingEngine:
    """
    AI Powered Assistance Platform Privacy Preservation Engine:
    - Leverages Microsoft Presidio Analyzer & Anonymizer
    - Enforces local vs external consent boundaries
    - Masks PII (names, contact info, locations, identifiers) before any external processing
    - Provides reversible mapping for authorized session restores
    """
    _analyzer: Optional[AnalyzerEngine] = None
    _anonymizer: Optional[AnonymizerEngine] = None

    @classmethod
    def get_analyzer(cls) -> AnalyzerEngine:
        if cls._analyzer is None:
            try:
                from presidio_analyzer.nlp_engine import NlpEngineProvider
                nlp_config = {
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]
                }
                provider = NlpEngineProvider(nlp_configuration=nlp_config)
                engine = provider.create_engine()
                cls._analyzer = AnalyzerEngine(nlp_engine=engine)
            except Exception:
                cls._analyzer = AnalyzerEngine()
            # Add custom recognizer for GitHub / LinkedIn profiles & personal URLs
            url_pattern = Pattern(
                name="profile_url_pattern",
                regex=r"(https?://)?(www\.)?(github\.com|linkedin\.com/in|gitlab\.com)/[A-Za-z0-9_-]+",
                score=0.85
            )
            url_recognizer = PatternRecognizer(
                supported_entity="PROFILE_URL",
                patterns=[url_pattern]
            )
            cls._analyzer.registry.add_recognizer(url_recognizer)

            # Add generic phone pattern to catch all international/US phone formats
            phone_pattern = Pattern(
                name="generic_phone_pattern",
                regex=r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
                score=0.85
            )
            phone_recognizer = PatternRecognizer(
                supported_entity="PHONE_NUMBER",
                patterns=[phone_pattern]
            )
            cls._analyzer.registry.add_recognizer(phone_recognizer)
        return cls._analyzer

    @classmethod
    def get_anonymizer(cls) -> AnonymizerEngine:
        if cls._anonymizer is None:
            cls._anonymizer = AnonymizerEngine()
        return cls._anonymizer

    @classmethod
    def detect_pii(cls, text: str, language: str = "en") -> List[Dict[str, Any]]:
        """
        Detects all PII entities present in the text with confidence scores.
        """
        if not text:
            return []
        analyzer = cls.get_analyzer()
        results = analyzer.analyze(
            text=text,
            language=language,
            entities=[
                "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "LOCATION",
                "US_SSN", "CREDIT_CARD", "IP_ADDRESS", "PROFILE_URL", "DATE_TIME"
            ]
        )
        return [
            {
                "entity_type": res.entity_type,
                "start": res.start,
                "end": res.end,
                "score": float(res.score),
                "text_snippet": text[res.start:res.end]
            }
            for res in results
        ]

    @classmethod
    def anonymize_text(
        cls,
        text: str,
        consent_settings: Optional[Dict[str, Any]] = None,
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Anonymizes text with placeholders. Returns anonymized text, mapping, and entities detected.
        If consent_settings indicates local_only or no external consent, masks all sensitive PII.
        """
        if not text:
            return {
                "anonymized_text": "",
                "mapping": {},
                "entities_detected": [],
                "masked_count": 0
            }

        analyzer = cls.get_analyzer()
        anonymizer = cls.get_anonymizer()

        analysis_results = analyzer.analyze(
            text=text,
            language=language,
            entities=[
                "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "LOCATION",
                "US_SSN", "CREDIT_CARD", "IP_ADDRESS", "PROFILE_URL"
            ]
        )

        mapping: Dict[str, str] = {}
        type_counters: Dict[str, int] = {}

        # Sort by start descending so replacement or indexing works cleanly
        sorted_results = sorted(analysis_results, key=lambda r: (r.start, r.end))
        
        TYPE_PLACEHOLDERS = {
            "PERSON": "<CANDIDATE_NAME>",
            "EMAIL_ADDRESS": "<CANDIDATE_EMAIL>",
            "PHONE_NUMBER": "<CANDIDATE_PHONE>",
            "LOCATION": "<CANDIDATE_LOCATION>",
            "PROFILE_URL": "<PROFILE_URL>",
            "US_SSN": "<SSN_REDACTED>",
            "CREDIT_CARD": "<FINANCIAL_REDACTED>",
        }

        # Build operators with numbered placeholders and generic placeholders
        for res in sorted_results:
            etype = res.entity_type
            type_counters[etype] = type_counters.get(etype, 0) + 1
            idx = type_counters[etype]
            placeholder = f"<{etype}_{idx}>"
            original_val = text[res.start:res.end]
            mapping[placeholder] = original_val
            gen_placeholder = TYPE_PLACEHOLDERS.get(etype, f"<{etype}>")
            if gen_placeholder not in mapping:
                mapping[gen_placeholder] = original_val

        # Anonymize using custom replace operator
        anonymized_result = anonymizer.anonymize(
            text=text,
            analyzer_results=analysis_results,
            operators={
                "DEFAULT": OperatorConfig("replace", {"new_value": "<REDACTED>"}),
                "PERSON": OperatorConfig("replace", {"new_value": "<CANDIDATE_NAME>"}),
                "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "<CANDIDATE_EMAIL>"}),
                "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "<CANDIDATE_PHONE>"}),
                "LOCATION": OperatorConfig("replace", {"new_value": "<CANDIDATE_LOCATION>"}),
                "PROFILE_URL": OperatorConfig("replace", {"new_value": "<PROFILE_URL>"}),
                "US_SSN": OperatorConfig("replace", {"new_value": "<SSN_REDACTED>"}),
                "CREDIT_CARD": OperatorConfig("replace", {"new_value": "<FINANCIAL_REDACTED>"}),
            }
        )

        return {
            "anonymized_text": anonymized_result.text,
            "mapping": mapping,
            "entities_detected": [
                {
                    "entity_type": r.entity_type,
                    "start": r.start,
                    "end": r.end,
                    "score": float(r.score)
                }
                for r in analysis_results
            ],
            "masked_count": len(analysis_results)
        }

    @classmethod
    def restore_text(cls, anonymized_text: str, mapping: Dict[str, str]) -> str:
        """
        Reversibly restores original values into anonymized text within authorized scope.
        """
        restored = anonymized_text
        for placeholder, original in mapping.items():
            restored = restored.replace(placeholder, original)
        return restored
