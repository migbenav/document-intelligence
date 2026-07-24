"""Unit tests for the LanguageDetector module.

Validates Requirements 4.1, 4.2, 4.3:
- 4.1: Spanish documents are identified as Spanish
- 4.2: English documents are identified as English
- 4.3: Unsupported languages return UNKNOWN without blocking
"""

import pytest

from app.ingestion.language import LanguageDetector
from app.models.document import DetectedLanguage


@pytest.fixture
def detector() -> LanguageDetector:
    """Provide a fresh LanguageDetector instance."""
    return LanguageDetector()


class TestEnglishDetection:
    """Requirement 4.2: English documents identified as English."""

    def test_clear_english_text(self, detector: LanguageDetector) -> None:
        text = (
            "The quick brown fox jumps over the lazy dog. "
            "This is a simple sentence that contains many common English words. "
            "It was written for the purpose of testing language detection."
        )
        assert detector.detect(text) == DetectedLanguage.ENGLISH

    def test_english_paragraph(self, detector: LanguageDetector) -> None:
        text = (
            "In the beginning, there was nothing but darkness and silence. "
            "Then a light appeared on the horizon, and with it came the sounds "
            "of life. The birds began to sing, the rivers started to flow, and "
            "the world was transformed into something beautiful and alive."
        )
        assert detector.detect(text) == DetectedLanguage.ENGLISH

    def test_english_technical_text(self, detector: LanguageDetector) -> None:
        text = (
            "The system architecture is designed with scalability in mind. "
            "Each component can be deployed independently, and they communicate "
            "through well-defined interfaces. This approach has been validated "
            "by our engineering team after extensive testing."
        )
        assert detector.detect(text) == DetectedLanguage.ENGLISH


class TestSpanishDetection:
    """Requirement 4.1: Spanish documents identified as Spanish."""

    def test_clear_spanish_text(self, detector: LanguageDetector) -> None:
        text = (
            "El rápido zorro marrón salta sobre el perro perezoso. "
            "Esta es una oración simple que contiene muchas palabras comunes en español. "
            "Fue escrita con el propósito de probar la detección de idioma."
        )
        assert detector.detect(text) == DetectedLanguage.SPANISH

    def test_spanish_paragraph(self, detector: LanguageDetector) -> None:
        text = (
            "En el principio no había nada más que oscuridad y silencio. "
            "Entonces una luz apareció en el horizonte, y con ella llegaron los "
            "sonidos de la vida. Los pájaros comenzaron a cantar, los ríos "
            "empezaron a fluir, y el mundo se transformó en algo hermoso."
        )
        assert detector.detect(text) == DetectedLanguage.SPANISH

    def test_spanish_with_special_characters(self, detector: LanguageDetector) -> None:
        text = (
            "¿Cómo estás? El niño pequeño jugaba en el parque con su mamá. "
            "¡Qué bonito día! La señora preparó una comida deliciosa para todos."
        )
        assert detector.detect(text) == DetectedLanguage.SPANISH

    def test_spanish_character_patterns_boost(self, detector: LanguageDetector) -> None:
        """Spanish character patterns (ñ, ¿, ¡) should boost Spanish score."""
        text = (
            "El señor García enseña español en la universidad. "
            "¿Sabías que el español es una de las lenguas más habladas del mundo?"
        )
        assert detector.detect(text) == DetectedLanguage.SPANISH


class TestUnknownDetection:
    """Requirement 4.3: Unsupported languages return UNKNOWN."""

    def test_empty_string(self, detector: LanguageDetector) -> None:
        assert detector.detect("") == DetectedLanguage.UNKNOWN

    def test_very_short_text(self, detector: LanguageDetector) -> None:
        """Text with fewer than 5 words should return UNKNOWN."""
        assert detector.detect("hello world") == DetectedLanguage.UNKNOWN

    def test_single_word(self, detector: LanguageDetector) -> None:
        assert detector.detect("test") == DetectedLanguage.UNKNOWN

    def test_french_text(self, detector: LanguageDetector) -> None:
        """French is unsupported and should return UNKNOWN."""
        text = (
            "Bonjour le monde. Je suis très content aujourd'hui. "
            "Cette phrase est écrite en français pour tester la détection. "
            "Il fait beau temps dehors et je vais me promener bientôt."
        )
        assert detector.detect(text) == DetectedLanguage.UNKNOWN

    def test_german_text(self, detector: LanguageDetector) -> None:
        """German is unsupported and should return UNKNOWN."""
        text = (
            "Guten Morgen allerseits. Heute ist ein wunderschöner Tag. "
            "Ich gehe jetzt nach Hause und werde dort ein Buch lesen. "
            "Die Kinder spielen draußen im Garten und haben viel Spaß."
        )
        assert detector.detect(text) == DetectedLanguage.UNKNOWN

    def test_numbers_only(self, detector: LanguageDetector) -> None:
        """Pure numeric content should return UNKNOWN."""
        text = "12345 67890 11111 22222 33333 44444 55555 66666"
        assert detector.detect(text) == DetectedLanguage.UNKNOWN


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_truncates_to_1000_chars(self, detector: LanguageDetector) -> None:
        """Only the first 1000 characters should be analyzed."""
        # Create English text that's well over 1000 chars
        english_prefix = "The world is a beautiful place and we should protect it. " * 20
        # Append Spanish text after 1000 chars
        spanish_suffix = "El mundo es un lugar hermoso y debemos protegerlo. " * 50
        text = english_prefix + spanish_suffix

        # Should detect based on first 1000 chars only (English)
        assert len(english_prefix) > 1000
        assert detector.detect(text) == DetectedLanguage.ENGLISH

    def test_mixed_language_balanced(self, detector: LanguageDetector) -> None:
        """Balanced mix of languages should return UNKNOWN or dominant language."""
        # Roughly balanced English/Spanish - result depends on exact scoring
        text = (
            "The cat is on the table. El gato está en la mesa. "
            "The dog is in the garden. El perro está en el jardín. "
            "This is a test of mixed language content for detection purposes."
        )
        result = detector.detect(text)
        # With mixed content, either a confident detection or UNKNOWN is acceptable
        assert result in (
            DetectedLanguage.ENGLISH,
            DetectedLanguage.SPANISH,
            DetectedLanguage.UNKNOWN,
        )

    def test_whitespace_only(self, detector: LanguageDetector) -> None:
        """Whitespace-only input should return UNKNOWN."""
        assert detector.detect("   \t\n   ") == DetectedLanguage.UNKNOWN

    def test_case_insensitive(self, detector: LanguageDetector) -> None:
        """Detection should work regardless of text case."""
        text = (
            "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG. "
            "THIS IS A SIMPLE SENTENCE THAT CONTAINS MANY COMMON ENGLISH WORDS. "
            "IT WAS WRITTEN FOR THE PURPOSE OF TESTING LANGUAGE DETECTION."
        )
        assert detector.detect(text) == DetectedLanguage.ENGLISH
