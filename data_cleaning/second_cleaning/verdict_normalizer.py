"""
Verdict normalization module for standardizing claim verdicts.
Uses zero-shot classification for paragraph-form verdicts.
"""

from transformers import pipeline, XLMRobertaTokenizer
from typing import Optional

# Standard verdict categories
STANDARD_VERDICTS = {
    "TRUE",
    "MOSTLY-TRUE",
    "HALF-TRUE",
    "MOSTLY-FALSE",
    "FALSE",
    "UNPROVEN",
    "MISLEADING",
    "SATIRE",
    "MISSING-CONTEXT",
    "OUTDATED",
    "UNKNOWN",
}

# Mapping of common verdict variations to standard verdicts
VERDICT_MAPPING = {
    # TRUE variations
    "true": "TRUE",
    "correct": "TRUE",
    "correct.": "TRUE",  # High-frequency from Full Fact (197 occurrences)
    "correct,": "TRUE",  # Common variant from Full Fact (100 occurrences)
    "accurate": "TRUE",
    "verified": "TRUE",
    "fact-check: true": "TRUE",
    # MOSTLY-TRUE variations
    "mostly true": "MOSTLY-TRUE",
    "mostly-true": "MOSTLY-TRUE",
    "largely true": "MOSTLY-TRUE",
    "partially true": "MOSTLY-TRUE",
    "broadly": "MOSTLY-TRUE",  # High-frequency from Full Fact (19 occurrences, e.g., "Broadly correct...")
    "broadly correct": "MOSTLY-TRUE",
    # HALF-TRUE variations
    "half true": "HALF-TRUE",
    "half-true": "HALF-TRUE",
    "mixed": "HALF-TRUE",
    "partial": "HALF-TRUE",
    # MOSTLY-FALSE variations
    "mostly false": "MOSTLY-FALSE",
    "mostly-false": "MOSTLY-FALSE",
    "largely false": "MOSTLY-FALSE",
    "partially false": "MOSTLY-FALSE",
    "barely-true": "MOSTLY-FALSE",  # Politifact variation
    # FALSE variations
    "false": "FALSE",
    "false.": "FALSE",  # High-frequency from Full Fact (491 occurrences)
    "fake": "FALSE",  # Snopes "FAKE" verdict
    "pants-fire": "FALSE",  # Politifact variation
    "pants-on-fire": "FALSE",  # Politifact variation
    "incorrect": "FALSE",
    "incorrect.": "FALSE",  # High-frequency from Full Fact (302 occurrences)
    "inaccurate": "FALSE",
    "debunked": "FALSE",
    "fact-check: false": "FALSE",
    "do not": "FALSE",
    "does not": "FALSE",
    "don't": "FALSE",
    "doesn't": "FALSE",
    "not true": "FALSE",
    # UNPROVEN variations
    "unproven": "UNPROVEN",
    "unverified": "UNPROVEN",
    "not proven": "UNPROVEN",
    "lacks evidence": "UNPROVEN",
    # MISLEADING variations
    "misleading": "MISLEADING",
    "deceptive": "MISLEADING",
    "out of context": "MISLEADING",
    # SATIRE variations
    "satire": "SATIRE",
    "parody": "SATIRE",
    "joke": "SATIRE",
    # MISSING-CONTEXT variations
    "missing context": "MISSING-CONTEXT",
    "missing-context": "MISSING-CONTEXT",
    "lacks context": "MISSING-CONTEXT",
    "out-of-context": "MISSING-CONTEXT",
    # OUTDATED variations
    "outdated": "OUTDATED",
    "old": "OUTDATED",
    "no longer accurate": "OUTDATED",
    # UNKNOWN variations
    "unknown": "UNKNOWN",
    "unclear": "UNKNOWN",
    "no verdict": "UNKNOWN",
    "n/a": "UNKNOWN",
}

# Negation patterns that indicate FALSE verdicts
NEGATION_PATTERNS = [
    "do not",
    "does not",
    "don't",
    "doesn't",
    "did not",
    "didn't",
    "was not",
    "wasn't",
    "were not",
    "weren't",
    "not true",
    "is false",
    "are false",
    "no evidence",
    "there is no evidence",
    "there isn't evidence",
    "there is not evidence",
    "was filmed in",
    "was filmed at",
    "was taken in",
    "was taken at",
    "was posted in",
]

# Uncertainty patterns that indicate UNPROVEN verdicts
UNCERTAINTY_PATTERNS = [
    "we don't know",
    "we do not know",
    "there isn't evidence",
    "there is not evidence",
    "unclear",
    "uncertain",
]


class VerdictNormalizer:
    """Normalizes verdicts to standard categories using mapping and NLP classification."""

    def __init__(self):
        """Initialize the zero-shot classifier."""
        # Load slow tokenizer directly to avoid fast tokenizer conversion issues
        tokenizer = XLMRobertaTokenizer.from_pretrained(
            "joeddav/xlm-roberta-large-xnli"
        )
        self.classifier = pipeline(
            "zero-shot-classification",
            model="joeddav/xlm-roberta-large-xnli",
            tokenizer=tokenizer,
        )

    def normalize_verdict(
        self, verdict: Optional[str], claim_text: Optional[str] = None
    ) -> Optional[str]:
        """
        Normalize a verdict to one of the standard categories.

        Args:
            verdict: The original verdict text
            claim_text: The claim text (used for NLP-based classification if verdict is in paragraph form)

        Returns:
            Normalized verdict from STANDARD_VERDICTS or UNKNOWN if unable to determine
        """
        if not verdict or not isinstance(verdict, str):
            return "UNKNOWN"

        # Clean and normalize the input
        verdict_cleaned = verdict.strip().lower()

        # Check for verdicts starting with labels followed by a colon
        # e.g., "Fake: Alex Eala...", "True: Ferdinand Marcos...", "Misleading: The news..."
        if ":" in verdict_cleaned:
            prefix = verdict_cleaned.split(":")[0].strip()
            if prefix in ["fake", "false", "incorrect", "wrong"]:
                return "FALSE"
            if prefix in ["true", "accurate", "correct"]:
                return "TRUE"
            if prefix in ["misleading", "misrepresented"]:
                return "MISLEADING"
            if prefix in ["unproven", "unverified"]:
                return "UNPROVEN"

        # Check for verdicts starting with FALSE indicators
        # e.g., "Incorrect. The ruling...", "False. This claim...", "This is not true..."
        false_starts = [
            "incorrect.",
            "false.",
            "inappropriate.",
            "wrong.",
            "untrue.",
            "not true.",
            "this is not true",
            "fake.",
        ]
        if any(verdict_cleaned.startswith(start) for start in false_starts):
            return "FALSE"

        # Check for verdicts stating something is "misleading" or "misrepresented"
        # e.g., "This is misleading.", "This claim is misleading..."
        if verdict_cleaned.startswith("this is misleading"):
            return "MISLEADING"

        # Check for terms being "imprecise", "undefined", "ambiguous", etc.
        # e.g., "Heart disease is an imprecise term...", "X is undefined/ambiguous"
        # These indicate the claim uses unclear terminology → MISLEADING
        imprecise_term_patterns = [
            "is an imprecise term",
            "is an undefined term",
            "is an ambiguous term",
            "is imprecise",
            "is undefined",
            "is ambiguous",
            "is a very broad",
            "is broad and undefined",
        ]
        if any(pattern in verdict_cleaned for pattern in imprecise_term_patterns):
            return "MISLEADING"

        # High-frequency Full Fact patterns: verdicts starting with "there is no evidence"
        # (348 occurrences) - these are UNPROVEN verdicts
        if verdict_cleaned.startswith(
            "there is no evidence"
        ) or verdict_cleaned.startswith("there isn't evidence"):
            return "UNPROVEN"

        # High-frequency Full Fact patterns: verdicts starting with "we"
        # (124 occurrences) - these typically indicate "we don't know" → UNPROVEN
        if verdict_cleaned.startswith(
            "we can find no evidence"
        ) or verdict_cleaned.startswith("we could find no evidence"):
            return "UNPROVEN"

        # Check for negation patterns via substring matching (before exact dictionary match)
        # This handles verdicts like "mRNA vaccines do not change genes"
        for negation_pattern in NEGATION_PATTERNS:
            if negation_pattern in verdict_cleaned:
                return "FALSE"

        # Check for uncertainty patterns that indicate UNPROVEN
        # e.g., "We don't know how long...", "There isn't evidence that...", "a matter of judgement"
        for uncertainty_pattern in UNCERTAINTY_PATTERNS:
            if verdict_cleaned.startswith(uncertainty_pattern):
                return "UNPROVEN"

        # Check for verdicts saying something is subjective/a matter of judgment
        # e.g., "Whether X is a matter of judgement", "This is a matter of opinion"
        if (
            "matter of judgement" in verdict_cleaned
            or "matter of judgment" in verdict_cleaned
        ):
            return "UNPROVEN"

        # Check for verdicts that are purely descriptive/explanatory without a clear judgment
        # e.g., "Between X and Y...", "Mrs X made a number of claims for..." (no clear true/false)
        # These are often MISSING-CONTEXT verdicts when they don't make a clear judgment
        if verdict_cleaned.startswith("between ") and (
            "made a number of" in verdict_cleaned or "made several" in verdict_cleaned
        ):
            return "MISSING-CONTEXT"

        # Direct mapping check
        if verdict_cleaned in VERDICT_MAPPING:
            return VERDICT_MAPPING[verdict_cleaned]

        # If verdict is already in standard form (case-insensitive)
        if verdict_cleaned.upper() in STANDARD_VERDICTS:
            return verdict_cleaned.upper()

        # Check for "correct" or "true" with contextualizing words (Full Fact pattern)
        # e.g., "That's correct, but...", "It's true that..., but..."
        # Note: We only mark as MISLEADING if it says something is correct/true but then contradicts it
        # e.g., "That's correct, but actually it's false"
        # Verdicts like "Correct, although..." where the claim is still correct are still TRUE
        misleading_contradictions = [
            "but actually",
            "but it's false",
            "but it's incorrect",
            "but this is wrong",
            "however, this is",
            "though it's actually",
        ]
        if ("correct" in verdict_cleaned or "true" in verdict_cleaned) and any(
            phrase in verdict_cleaned for phrase in misleading_contradictions
        ):
            return "MISLEADING"

        # Check for simple affirmations at the start (without contradictory qualifiers)
        # e.g., "Correct it was...", "True. The claim...", "Correct, although..." (still TRUE)
        affirmative_starts = [
            "correct.",
            "correct ",
            "correct,",
            "correct, ",
            "true.",
            "true ",
            "accurate.",
            "accurate ",
        ]
        if any(verdict_cleaned.startswith(start) for start in affirmative_starts):
            return "TRUE"

        # Check for "Broadly correct" or "Broadly true" patterns (High-frequency from Full Fact - 19 occurrences)
        if verdict_cleaned.startswith("broadly "):
            return "MOSTLY-TRUE"

        # Check for partial support with caveats about magnitude/significance
        # e.g., "While X does support..., the effect is small/minimal/negligible"
        partial_support_patterns = [
            "while at least one study",
            "while some studies",
            "while research",
            "does support this claim",
            "supports this claim",
        ]
        magnitude_qualifiers = [
            "appears to be small",
            "appears to be minimal",
            "appears to be negligible",
            "is small",
            "is minimal",
            "is negligible",
            "likely to be minimal",
            "amount lost",
            "effect is",
        ]
        if any(
            pattern in verdict_cleaned for pattern in partial_support_patterns
        ) and any(qual in verdict_cleaned for qual in magnitude_qualifiers):
            return "MOSTLY-TRUE"

        # Check for verdicts that indicate data misrepresentation or misuse
        # e.g., "These figures appear to refer to...", "This refers to X, not Y"
        misrepresentation_phrases = [
            "appear to refer to",
            "appears to refer to",
            "actually refer",
            "different from what",
        ]
        if any(phrase in verdict_cleaned for phrase in misrepresentation_phrases):
            return "MISLEADING"

        # Check for verdicts that confirm numbers/facts but express uncertainty about details
        # e.g., "There are X..., but we don't know..."
        uncertainty_phrases = [
            "we don't know",
            "we do not know",
            "unclear",
            "uncertain",
            "can't confirm",
            "cannot confirm",
            "not clear",
            "isn't clear",
            "data doesn't tell us",
        ]
        if any(phrase in verdict_cleaned for phrase in uncertainty_phrases):
            # If it starts with affirmative language, it's likely MISSING-CONTEXT
            affirmative_starts = [
                "there are",
                "there were",
                "around",
                "approximately",
                "about",
                "roughly",
                "close to",
            ]
            if any(verdict_cleaned.startswith(start) for start in affirmative_starts):
                return "MISSING-CONTEXT"

        # Only use NLP for verdicts that are likely explanatory paragraphs (e.g., > 150 chars)
        if len(verdict_cleaned) > 150:
            return self._classify_with_nlp(verdict, claim_text)

        # If verdict is short but not in mapping, return UNKNOWN
        return "UNKNOWN"

    def _classify_with_nlp(
        self, verdict_text: str, claim_text: Optional[str] = None
    ) -> str:
        """
        Use zero-shot classification to determine verdict from text.

        Args:
            verdict_text: The verdict text to classify
            claim_text: The claim text for additional context

        Returns:
            The predicted verdict category
        """
        try:
            # Combine verdict and claim for better context
            if claim_text and len(claim_text) > 0:
                input_text = f"Claim: {claim_text[:500]} Verdict: {verdict_text[:500]}"
            else:
                input_text = verdict_text[:500]

            # Use more relevant label categories for fact-checking verdicts
            # Focus on the most common categories seen in Full Fact data
            candidate_labels = [
                "TRUE",
                "MOSTLY-TRUE",
                "FALSE",
                "MOSTLY-FALSE",
                "MISLEADING",
                "MISSING-CONTEXT",
                "UNPROVEN",
            ]

            # Use hypothesis template to guide classification
            result = self.classifier(
                input_text,
                candidate_labels,
                hypothesis_template="This fact-check verdict indicates the claim is {}.",
                multi_label=False,
            )

            # Return the top prediction
            if result and len(result["labels"]) > 0:
                top_label = result["labels"][0]
                top_score = result["scores"][0]

                # If confidence is low and verdict contains contextualizing language,
                # default to MISLEADING
                if top_score < 0.4 and any(
                    word in verdict_text.lower()
                    for word in ["but", "however", "although", "though", "context"]
                ):
                    return "MISLEADING"

                return top_label

        except Exception as e:
            print(f"Error during NLP classification: {e}")

        # Fallback to UNKNOWN if classification fails
        return "UNKNOWN"


# Global instance
_normalizer = None


def get_normalizer() -> VerdictNormalizer:
    """Get or create the global normalizer instance."""
    global _normalizer
    if _normalizer is None:
        _normalizer = VerdictNormalizer()
    return _normalizer


def normalize_verdict(
    verdict: Optional[str], claim_text: Optional[str] = None
) -> Optional[str]:
    """
    Convenience function to normalize a verdict.

    Args:
        verdict: The original verdict text
        claim_text: The claim text (used for NLP-based classification)

    Returns:
        Normalized verdict from STANDARD_VERDICTS or UNKNOWN
    """
    normalizer = get_normalizer()
    return normalizer.normalize_verdict(verdict, claim_text)
