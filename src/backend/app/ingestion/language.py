"""Language detection for ingested documents.

Lightweight, library-free language detection using stopword frequency
matching and character pattern analysis. Supports English, Spanish,
Portuguese, and French classification with an UNKNOWN fallback for
low-confidence results.
"""

import re

from app.models.document import DetectedLanguage

# Maximum characters to sample from input text
_MAX_SAMPLE_LENGTH = 2000

# Minimum word count required for a meaningful detection
_MIN_WORD_COUNT = 5

# Confidence threshold: the winning language score must exceed this
# fraction of total stopword hits to be considered confident.
_CONFIDENCE_THRESHOLD = 0.55

# Minimum density: stopword hits must represent at least this fraction
# of total words to avoid false positives from incidental overlap.
_MIN_STOPWORD_DENSITY = 0.15

# Bonus weight applied per language-specific character found
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

# Portuguese stopwords for frequency matching (top 50)
_PORTUGUESE_STOPWORDS: set[str] = {
    "de", "que", "em", "um", "uma", "para", "com", "não", "por",
    "mais", "se", "na", "os", "ao", "dos", "da", "das", "do", "no",
    "como", "ou", "mas", "foi", "ele", "ela", "são", "tem", "seu",
    "sua", "há", "já", "muito", "também", "isso", "nos", "quando",
    "até", "ser", "está", "esse", "este", "entre", "depois", "sem",
    "mesmo", "aos", "seus", "ainda", "bem", "pode",
}

# French stopwords for frequency matching (top 50)
_FRENCH_STOPWORDS: set[str] = {
    "le", "la", "de", "et", "les", "des", "en", "un", "une", "du",
    "que", "est", "pas", "sur", "ce", "qui", "dans", "au", "il",
    "sont", "pour", "ne", "plus", "avec", "par", "son", "se", "mais",
    "nous", "cette", "tout", "aux", "ses", "aussi", "comme", "elle",
    "été", "leur", "ou", "ont", "très", "bien", "fait", "peut",
    "même", "ces", "alors", "entre", "vous", "encore",
}

# Characters that are strong indicators of Spanish text
_SPANISH_CHAR_PATTERNS: set[str] = {"ñ", "¿", "¡"}

# Characters that are strong indicators of Portuguese text
_PORTUGUESE_CHAR_PATTERNS: set[str] = {"ã", "õ", "ç"}

# Characters that are strong indicators of French text
_FRENCH_CHAR_PATTERNS: set[str] = {"ç", "œ", "ù", "î", "ê"}

# Regex patterns for preprocessing noise removal
_URL_PATTERN = re.compile(r"https?://\S+")
_NUMBER_HEAVY_PATTERN = re.compile(r"\b\w*\d{2,}\w*\b")
_CAMEL_CASE_PATTERN = re.compile(r"\b[a-z]+[A-Z][a-zA-Z]*\b")
_SNAKE_CASE_PATTERN = re.compile(r"\b\w+_\w+\b")


def _preprocess(text: str) -> str:
    """Strip noise tokens from text before language detection.

    Removes URLs, number-heavy tokens, camelCase identifiers, and
    snake_case identifiers that would dilute stopword frequency analysis.
    """
    # Strip URLs
    text = _URL_PATTERN.sub("", text)
    # Strip number-heavy tokens (tokens containing 2+ consecutive digits)
    text = _NUMBER_HEAVY_PATTERN.sub("", text)
    # Strip camelCase tokens
    text = _CAMEL_CASE_PATTERN.sub("", text)
    # Strip snake_case tokens
    text = _SNAKE_CASE_PATTERN.sub("", text)
    return text


class LanguageDetector:
    """Detects the dominant language of a text sample.

    Uses stopword frequency matching and character pattern analysis
    to classify text as English, Spanish, Portuguese, French, or Unknown.
    Operates entirely locally with no network or LLM dependencies.
    """

    def detect(self, text_sample: str) -> DetectedLanguage:
        """Detect the language of the given text sample.

        Args:
            text_sample: Raw text to analyze. Only the first 2000
                characters are used for detection.

        Returns:
            DetectedLanguage.ENGLISH, DetectedLanguage.SPANISH,
            DetectedLanguage.PORTUGUESE, DetectedLanguage.FRENCH, or
            DetectedLanguage.UNKNOWN if confidence is below threshold.
        """
        # Sample first 2000 characters
        sample = text_sample[:_MAX_SAMPLE_LENGTH]

        # Preprocess: strip noise before tokenization
        cleaned = _preprocess(sample)

        # Tokenize: lowercase and split on non-alpha boundaries
        words = cleaned.lower().split()
        # Strip punctuation from word boundaries
        words = [w.strip(".,;:!?\"'()[]{}—–-") for w in words]
        words = [w for w in words if w]

        # If text is too short, return UNKNOWN
        if len(words) < _MIN_WORD_COUNT:
            return DetectedLanguage.UNKNOWN

        # Count stopword hits for each language
        english_score = sum(1 for w in words if w in _ENGLISH_STOPWORDS)
        spanish_score = sum(1 for w in words if w in _SPANISH_STOPWORDS)
        portuguese_score = sum(1 for w in words if w in _PORTUGUESE_STOPWORDS)
        french_score = sum(1 for w in words if w in _FRENCH_STOPWORDS)

        # Apply character pattern bonuses for language-specific indicators
        sample_lower = sample.lower()
        for char in _SPANISH_CHAR_PATTERNS:
            if char in sample_lower:
                spanish_score += _CHAR_PATTERN_WEIGHT

        for char in _PORTUGUESE_CHAR_PATTERNS:
            if char in sample_lower:
                portuguese_score += _CHAR_PATTERN_WEIGHT

        for char in _FRENCH_CHAR_PATTERNS:
            if char in sample_lower:
                french_score += _CHAR_PATTERN_WEIGHT

        # Build scores mapping
        scores = {
            DetectedLanguage.ENGLISH: english_score,
            DetectedLanguage.SPANISH: spanish_score,
            DetectedLanguage.PORTUGUESE: portuguese_score,
            DetectedLanguage.FRENCH: french_score,
        }

        # Total is the number of words that matched ANY language stopword set.
        # This avoids inflating the denominator when a word belongs to multiple
        # languages (e.g., "de" is Spanish, Portuguese, and French).
        total_matched_words = sum(
            1 for w in words
            if w in _ENGLISH_STOPWORDS
            or w in _SPANISH_STOPWORDS
            or w in _PORTUGUESE_STOPWORDS
            or w in _FRENCH_STOPWORDS
        )

        # If no stopwords matched at all, return UNKNOWN
        if total_matched_words == 0:
            return DetectedLanguage.UNKNOWN

        # Find the winner (including character pattern bonuses)
        winner = max(scores, key=scores.get)  # type: ignore[arg-type]
        max_score = scores[winner]

        # Check minimum stopword density to avoid false positives from
        # languages that incidentally share a few words
        if max_score / len(words) < _MIN_STOPWORD_DENSITY:
            return DetectedLanguage.UNKNOWN

        # Check confidence: winner must have enough of the total matched words
        # plus any character pattern bonuses
        total_score = sum(scores.values())
        confidence = max_score / total_score
        if confidence >= _CONFIDENCE_THRESHOLD:
            return winner

        # Below confidence threshold
        return DetectedLanguage.UNKNOWN
