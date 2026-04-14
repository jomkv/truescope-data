"""
Verdict normalization module for standardizing claim verdicts.
Provides a streamlined mapping for Politifact, Snopes, Verafiles, and Rappler.
"""

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
# Includes English and Tagalog terms from major fact-checking sources
VERDICT_MAPPING = {
    # TRUE variations
    "true": "TRUE",
    "tama": "TRUE",
    "totoo": "TRUE",
    "correct": "TRUE",
    "accurate": "TRUE",
    "verified": "TRUE",
    
    # MOSTLY-TRUE variations
    "mostly true": "MOSTLY-TRUE",
    "mostly-true": "MOSTLY-TRUE",
    "mostly totoo": "MOSTLY-TRUE",
    "mostly tama": "MOSTLY-TRUE",
    "largely true": "MOSTLY-TRUE",
    "partially true": "MOSTLY-TRUE",
    "broadly correct": "MOSTLY-TRUE",
    "broadly true": "MOSTLY-TRUE",
    "broadly": "MOSTLY-TRUE",
    
    # HALF-TRUE variations
    "half true": "HALF-TRUE",
    "half-true": "HALF-TRUE",
    "mixed": "HALF-TRUE",
    "mixture": "HALF-TRUE",
    "mixtures": "HALF-TRUE",
    "partial": "HALF-TRUE",
    
    # MOSTLY-FALSE variations
    "mostly false": "MOSTLY-FALSE",
    "mostly-false": "MOSTLY-FALSE",
    "mostly hindi totoo": "MOSTLY-FALSE",
    "mostly mali": "MOSTLY-FALSE",
    "largely false": "MOSTLY-FALSE",
    "barely-true": "MOSTLY-FALSE",
    
    # FALSE variations
    "false": "FALSE",
    "hindi totoo": "FALSE",
    "hindi": "FALSE",
    "mali": "FALSE",
    "incorrect": "FALSE",
    "fake": "FALSE",
    "pants-fire": "FALSE",
    "pants-on-fire": "FALSE",
    "pants on fire": "FALSE",
    "kasinungalingan": "FALSE",
    "wrong": "FALSE",
    "untrue": "FALSE",
    "sinungaling": "FALSE",
    "bulaan": "FALSE",
    "debunked": "FALSE",
    
    # UNPROVEN variations
    "unproven": "UNPROVEN",
    "walang basehan": "UNPROVEN",
    "no context": "UNPROVEN",
    "no evidence": "UNPROVEN",
    "no basis": "UNPROVEN",
    "unverified": "UNPROVEN",
    "not proven": "UNPROVEN",
    "lacks evidence": "UNPROVEN",
    
    # MISLEADING variations
    "misleading": "MISLEADING",
    "sablay": "MISLEADING",
    "naliligaw": "MISLEADING",
    "deceptive": "MISLEADING",
    "out of context": "MISLEADING",
    "misrepresented": "MISLEADING",
    
    # MISSING-CONTEXT variations
    "missing context": "MISSING-CONTEXT",
    "missing-context": "MISSING-CONTEXT",
    "kulang sa konteksto": "MISSING-CONTEXT",
    "kulang sa detalye": "MISSING-CONTEXT",
    "lacks context": "MISSING-CONTEXT",
    
    # SATIRE variations
    "satire": "SATIRE",
    "parody": "SATIRE",
    "joke": "SATIRE",
    
    # OUTDATED variations
    "outdated": "OUTDATED",
    "old": "OUTDATED",
}


class VerdictNormalizer:
    """Normalizes verdicts from multiple sources to standard categories."""
    
    def __init__(self):
        """Initialize the normalizer."""
        pass
    
    def normalize_verdict(self, verdict: Optional[str], claim_text: Optional[str] = None) -> Optional[str]:
        """
        Normalize a verdict to one of the standard categories.
        
        Logic prioritize explicit mappings and extracts prefixes/first-words for 
        paragraph-style verdicts (like Verafiles).
        """
        if not verdict or not isinstance(verdict, str):
            return "UNKNOWN"
        
        # 1. Clean and normalize the input
        verdict_cleaned = verdict.strip().lower()
        if not verdict_cleaned:
            return "UNKNOWN"
            
        # 2. Straight Mapping Check (Handles Politifact, Snopes, Rappler explicit labels)
        if verdict_cleaned in VERDICT_MAPPING:
            return VERDICT_MAPPING[verdict_cleaned]

        # 3. Prefix/First-Word Extraction (Handles Verafiles: "False: This is...")
        # Check for colon separators
        candidate = verdict_cleaned
        if ":" in verdict_cleaned:
            candidate = verdict_cleaned.split(":")[0].strip()
        # If no colon, but it's a long text, assume the first word is the verdict
        elif len(verdict_cleaned) > 20: 
            candidate = verdict_cleaned.split()[0].strip().rstrip(".,;:")

        # 4. Check the candidate against mapping
        if candidate in VERDICT_MAPPING:
            return VERDICT_MAPPING[candidate]

        # 5. Check if it's already a standard verdict name
        if verdict_cleaned.upper() in STANDARD_VERDICTS:
            return verdict_cleaned.upper()
            
        return "UNKNOWN"


# Global instance
_normalizer = None

def get_normalizer() -> VerdictNormalizer:
    """Get or create the global normalizer instance."""
    global _normalizer
    if _normalizer is None:
        _normalizer = VerdictNormalizer()
    return _normalizer


def normalize_verdict(verdict: Optional[str], claim_text: Optional[str] = None) -> Optional[str]:
    """Convenience function to normalize a verdict."""
    normalizer = get_normalizer()
    return normalizer.normalize_verdict(verdict, claim_text)
