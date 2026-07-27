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

    def test_japanese_text(self, detector: LanguageDetector) -> None:
        """Japanese is unsupported and should return UNKNOWN."""
        text = (
            "今日はとても良い天気です。私は公園に散歩に行きました。"
            "木々が美しく色づいていて、とても気持ちが良かったです。"
            "帰り道に美味しいコーヒーを買って飲みました。"
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

    def test_truncates_to_2000_chars(self, detector: LanguageDetector) -> None:
        """Only the first 2000 characters should be analyzed."""
        # Create English text that's well over 2000 chars
        english_prefix = "The world is a beautiful place and we should protect it. " * 40
        # Append Spanish text after 2000 chars
        spanish_suffix = "El mundo es un lugar hermoso y debemos protegerlo. " * 50
        text = english_prefix + spanish_suffix

        # Should detect based on first 2000 chars only (English)
        assert len(english_prefix) > 2000
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


class TestSampleExpansion:
    """Requirement 7.1: Sample expanded to 2000 characters."""

    def test_max_sample_length_is_2000(self) -> None:
        """The detector should sample the first 2000 characters."""
        from app.ingestion.language import _MAX_SAMPLE_LENGTH

        assert _MAX_SAMPLE_LENGTH == 2000

    def test_uses_full_2000_char_sample(self, detector: LanguageDetector) -> None:
        """Text between 1000-2000 chars should be fully utilized for detection.

        A Spanish text that is 1500 chars long should be correctly detected,
        proving the detector uses more than the old 1000-char limit.
        """
        # Build a Spanish text that is ~1500 chars - above old 1000 limit
        spanish_segment = (
            "El reglamento establece las normas para la convivencia en el edificio. "
            "Los propietarios deben cumplir con las disposiciones establecidas por la junta. "
            "Las áreas comunes son de uso compartido entre todos los residentes del inmueble. "
        )
        # Repeat to get ~1500 chars
        text = spanish_segment * 7  # ~1500 chars
        assert 1000 < len(text) < 2000
        assert detector.detect(text) == DetectedLanguage.SPANISH


class TestPortugueseDetection:
    """Requirement 7.2: Portuguese text correctly detected."""

    def test_clear_portuguese_text(self, detector: LanguageDetector) -> None:
        """Plain Portuguese text with distinctive markers should be detected."""
        text = (
            "Ele não pode estacionar na área do edifício sem autorização. "
            "Os moradores já estão cientes das suas obrigações neste assunto. "
            "A sua participação também é muito importante ao longo do processo. "
            "Ela está bem depois da reunião em que os seus direitos foram discutidos. "
            "Este regulamento tem como objetivo mesmo esse bem estar dos condôminos. "
            "Os proprietários não podem fazer isso sem a aprovação da administração. "
            "Há uma obrigação dos moradores em manter os espaços ainda organizados. "
            "Ele tem até o prazo estabelecido ao final do mês para se regularizar."
        )
        assert detector.detect(text) == DetectedLanguage.PORTUGUESE

    def test_portuguese_with_characteristic_chars(self, detector: LanguageDetector) -> None:
        """Portuguese text with ã, õ characters should boost detection."""
        text = (
            "A organização das nações unidas apresentou um relatório sobre as condições "
            "de habitação em diversas regiões do mundo. Os cidadãos brasileiros também "
            "foram consultados sobre suas opiniões a respeito da educação pública. "
            "Não há dúvida de que isso é muito importante para o desenvolvimento."
        )
        assert detector.detect(text) == DetectedLanguage.PORTUGUESE

    def test_portuguese_paragraph(self, detector: LanguageDetector) -> None:
        """A full Portuguese paragraph should be reliably detected."""
        text = (
            "Este documento tem como objetivo apresentar as diretrizes para o uso "
            "dos espaços comuns do condomínio. Todos os moradores devem respeitar "
            "as regras estabelecidas neste regulamento. O não cumprimento das normas "
            "pode resultar em multas e outras penalidades conforme previsto em lei."
        )
        assert detector.detect(text) == DetectedLanguage.PORTUGUESE


class TestFrenchDetection:
    """Requirement 7.3: French text correctly detected."""

    def test_clear_french_text(self, detector: LanguageDetector) -> None:
        """Plain French text should be detected as French."""
        text = (
            "Le règlement intérieur établit les normes pour la vie en commun dans "
            "le bâtiment. Les propriétaires ne peuvent pas faire de bruit après "
            "vingt-deux heures. Les espaces communs sont partagés entre tous les "
            "résidents de cette copropriété pour leur bien être quotidien."
        )
        assert detector.detect(text) == DetectedLanguage.FRENCH

    def test_french_with_characteristic_chars(self, detector: LanguageDetector) -> None:
        """French text with ê, î, ù characters should boost detection."""
        text = (
            "L'être humain est une créature très intéressante. Il peut être "
            "à la fois généreux et égoïste. Les fêtes de Noël sont une période "
            "où les gens font preuve de générosité envers les autres. "
            "C'est une très belle tradition qui nous unit encore aujourd'hui."
        )
        assert detector.detect(text) == DetectedLanguage.FRENCH

    def test_french_paragraph(self, detector: LanguageDetector) -> None:
        """A full French paragraph should be reliably detected."""
        text = (
            "Ce document a pour objectif de présenter les directives pour "
            "l'utilisation des espaces communs de la copropriété. Tous les "
            "résidents doivent respecter les règles établies dans ce règlement. "
            "Le non-respect des normes peut entraîner des amendes et autres "
            "pénalités conformément aux dispositions légales en vigueur."
        )
        assert detector.detect(text) == DetectedLanguage.FRENCH


class TestNoiseStripping:
    """Requirement 7.5: Text with URLs and numbers stripped before detection."""

    def test_urls_stripped_before_detection(self, detector: LanguageDetector) -> None:
        """URLs should be removed before language analysis."""
        text = (
            "El reglamento está disponible en https://www.example.com/docs/rules "
            "y también en http://internal.server.com/v2/documents/12345. "
            "Los propietarios deben consultar las normas del edificio para "
            "conocer sus derechos y obligaciones como residentes del inmueble."
        )
        assert detector.detect(text) == DetectedLanguage.SPANISH

    def test_number_heavy_tokens_stripped(self, detector: LanguageDetector) -> None:
        """Number-heavy tokens should be removed before language analysis."""
        text = (
            "El artículo 2345 del reglamento 78901 establece que los residentes "
            "deben pagar la cuota 12345 antes del día 15 de cada mes. "
            "Los propietarios del piso 4567 también son responsables del "
            "mantenimiento según la resolución 89012 de la junta directiva."
        )
        assert detector.detect(text) == DetectedLanguage.SPANISH

    def test_camel_case_tokens_stripped(self, detector: LanguageDetector) -> None:
        """camelCase code identifiers should be removed before detection."""
        text = (
            "El sistema utiliza processDocument para iniciar el análisis. "
            "Los métodos getLanguageResult y setConfiguration son esenciales "
            "para el funcionamiento del módulo de detección de idioma. "
            "El componente buildIndex genera la estructura del documento completo."
        )
        assert detector.detect(text) == DetectedLanguage.SPANISH

    def test_snake_case_tokens_stripped(self, detector: LanguageDetector) -> None:
        """snake_case code identifiers should be removed before detection."""
        text = (
            "El módulo language_detector se encarga de detectar el idioma. "
            "Las funciones detect_language y process_text son las más importantes "
            "para el correcto funcionamiento del sistema de análisis completo. "
            "El archivo test_language contiene todas las pruebas del módulo."
        )
        assert detector.detect(text) == DetectedLanguage.SPANISH

    def test_mixed_noise_does_not_confuse_detection(self, detector: LanguageDetector) -> None:
        """Text with URLs, numbers, and code tokens still detects correctly."""
        text = (
            "El documento v2 disponible en https://docs.example.com/api/v3 "
            "describe las funciones processDocument y build_index con código "
            "de referencia 98765. Los propietarios deben leer el reglamento "
            "completo para entender las normas del edificio y sus obligaciones."
        )
        assert detector.detect(text) == DetectedLanguage.SPANISH


class TestTechnicalSpanishWithEnglishTerms:
    """Requirement 7.4: Technical Spanish with English terms detected as Spanish."""

    def test_spanish_with_english_technical_terms(self, detector: LanguageDetector) -> None:
        """Spanish documents with English technical jargon should detect as Spanish."""
        text = (
            "El sistema de machine learning utiliza un pipeline para el análisis "
            "de los documentos del proyecto. Los modelos son entrenados con los "
            "datos del servidor para obtener los mejores resultados posibles en "
            "la detección de idioma. El equipo también implementó un módulo que "
            "se encarga de verificar la calidad de las predicciones del sistema. "
            "¿Cómo se mide el rendimiento del módulo? Se evalúa con las métricas "
            "estándar del área. Además el sistema cuenta con una interfaz para "
            "que los usuarios puedan interactuar con el pipeline de forma sencilla."
        )
        assert detector.detect(text) == DetectedLanguage.SPANISH

    def test_spanish_legal_with_latin_and_english(self, detector: LanguageDetector) -> None:
        """Spanish legal text with some Latin/English phrases should detect as Spanish."""
        text = (
            "De conformidad con el artículo sobre compliance y due diligence, "
            "los propietarios están obligados a mantener el status quo del inmueble. "
            "El feedback de la comunidad será tomado en cuenta para la elaboración "
            "del nuevo reglamento según las mejores practices del sector inmobiliario."
        )
        assert detector.detect(text) == DetectedLanguage.SPANISH

    def test_spanish_software_documentation(self, detector: LanguageDetector) -> None:
        """Software documentation written in Spanish with English API terms."""
        text = (
            "La clase LanguageDetector se encarga de identificar el idioma del "
            "documento. El método detect recibe un string de texto y retorna un "
            "enum con el resultado. Para configurar el threshold se debe modificar "
            "la constante en el módulo de configuración del backend del sistema."
        )
        assert detector.detect(text) == DetectedLanguage.SPANISH
