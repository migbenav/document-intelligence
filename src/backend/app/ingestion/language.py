"""Language detection for ingested documents.

Lightweight, library-free language detection using stopword frequency
matching and character pattern analysis. Supports English and Spanish
classification with an UNKNOWN fallback for low-confidence results.
"""

from app.models.document import DetectedLanguage

# Maximum characters to sample from input text
_MAX_SAMPLE_LENGTH = 1000

# Minimum word count required for a meaningful detection
_MIN_WORD_COUNT = 5

# Confidence threshold: the winning language score must exceed this
# fraction of total stopword hits to be considered confident.
_CONFIDENCE_THRESHOLD = 0.6

# Minimum density: stopword hits must represent at least this fraction
# of total words to avoid false positives from incidental overlap.
_MIN_STOPWORD_DENSITY = 0.15

# Bonus weight applied per Spanish-specific character found
_CHAR_PATTERN_WEIGHT = 3

# English stopwords for frequency matching
_ENGLISH_STOPWORDS: set[str] = {
    "the", "is", "and", "a", "of", "to", "in", "it", "that", "for",
    "was", "on", "are", "with", "as", "this", "be", "at", "by", "from",
    "or", "an", "have", "has", "not", "but", "what", "which", "their",
    "will", "been", "would", "could", "should", "there", "about", "were",
    "they", "each", "than", "other", "them", "into", "its", "when",
    "only", "can", "these", "some", "then", "very", "more", "also",
    "after", "our", "just",
}

# Spanish stopwords for frequency matching
_SPANISH_STOPWORDS: set[str] = {
    "el", "la", "de", "que", "en", "un", "una", "es", "se", "no",
    "por", "con", "los", "las", "del", "para", "lo", "su", "como",
    "al", "más", "pero", "ya", "o", "entre", "cuando", "todo", "esta",
    "ser", "son", "dos", "también", "fue", "había", "era", "tiene",
    "le", "me", "sin", "sus", "muy", "nos", "ni", "otro", "ese",
    "todos", "ella", "donde", "bien", "estos", "desde", "poco", "hay",
    "hasta", "aquí",
}

# Characters that are strong indicators of Spanish text
_SPANISH_CHAR_PATTERNS: set[str] = {"ñ", "¿", "¡"}


class LanguageDetector:
    """Detects the dominant language of a text sample.

    Uses stopword frequency matching and character pattern analysis
    to classify text as English, Spanish, or Unknown. Operates entirely
    locally with no network or LLM dependencies.
    """

    def detect(self, text_sample: str) -> DetectedLanguage:
        """Detect the language of the given text sample.

        Args:
            text_sample: Raw text to analyze. Only the first 1000
                characters are used for detection.

        Returns:
            DetectedLanguage.ENGLISH, DetectedLanguage.SPANISH, or
            DetectedLanguage.UNKNOWN if confidence is below threshold.
        """
        # Sample first 1000 characters
        sample = text_sample[:_MAX_SAMPLE_LENGTH]

        # Tokenize: lowercase and split on non-alpha boundaries
        words = sample.lower().split()
        # Strip punctuation from word boundaries
        words = [w.strip(".,;:!?\"'()[]{}—–-") for w in words]
        words = [w for w in words if w]

        # If text is too short, return UNKNOWN
        if len(words) < _MIN_WORD_COUNT:
            return DetectedLanguage.UNKNOWN

        # Count stopword hits
        english_score = sum(1 for w in words if w in _ENGLISH_STOPWORDS)
        spanish_score = sum(1 for w in words if w in _SPANISH_STOPWORDS)

        # Apply character pattern bonus for Spanish indicators
        sample_lower = sample.lower()
        for char in _SPANISH_CHAR_PATTERNS:
            if char in sample_lower:
                spanish_score += _CHAR_PATTERN_WEIGHT

        total_score = english_score + spanish_score

        # If no stopwords matched at all, return UNKNOWN
        if total_score == 0:
            return DetectedLanguage.UNKNOWN

        # Check minimum stopword density to avoid false positives from
        # languages that incidentally share a few words
        max_score = max(english_score, spanish_score)
        if max_score / len(words) < _MIN_STOPWORD_DENSITY:
            return DetectedLanguage.UNKNOWN

        # Determine winner and check confidence
        if english_score > spanish_score:
            confidence = english_score / total_score
            if confidence >= _CONFIDENCE_THRESHOLD:
                return DetectedLanguage.ENGLISH
        elif spanish_score > english_score:
            confidence = spanish_score / total_score
            if confidence >= _CONFIDENCE_THRESHOLD:
                return DetectedLanguage.SPANISH

        # Scores are tied or below confidence threshold
        return DetectedLanguage.UNKNOWN
