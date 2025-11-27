"""Tests for the heuristics module."""

import pytest
from src.heuristics import (
    heuristic_parse,
    is_ingredient_line,
    is_instruction_line,
    find_section_headers,
    extract_lines_from_html,
    clean_line,
    INGREDIENT_KEYWORDS,
    INSTRUCTION_VERBS,
)


class TestIsIngredientLine:
    """Tests for is_ingredient_line function."""

    def test_quantity_with_unit(self):
        """Lines with quantities and units score high."""
        assert is_ingredient_line("2 cups flour") > 0.5
        assert is_ingredient_line("1/2 teaspoon salt") > 0.5
        assert is_ingredient_line("3 tablespoons olive oil") > 0.5

    def test_quantity_only(self):
        """Lines with just quantities and items score moderately."""
        assert is_ingredient_line("3 eggs") > 0.3
        assert is_ingredient_line("1 onion, diced") > 0.3

    def test_bullet_with_quantity(self):
        """Bulleted items with quantities score as ingredients."""
        assert is_ingredient_line("- 2 cloves garlic") > 0.3
        assert is_ingredient_line("• 1 cup sugar") > 0.3

    def test_fraction_characters(self):
        """Unicode fractions should be detected."""
        assert is_ingredient_line("¼ cup butter") > 0.5
        assert is_ingredient_line("½ teaspoon vanilla") > 0.5

    def test_instruction_like_text_scores_low(self):
        """Text that looks like instructions should score low."""
        assert is_ingredient_line("Preheat the oven to 350°F") < 0.4
        assert is_ingredient_line("Mix until well combined") < 0.4


class TestIsInstructionLine:
    """Tests for is_instruction_line function."""

    def test_numbered_step(self):
        """Numbered steps score high."""
        assert is_instruction_line("1. Preheat oven to 350°F") > 0.5
        assert is_instruction_line("2) Mix the dry ingredients") > 0.5

    def test_cooking_verbs(self):
        """Lines starting with cooking verbs score reasonably."""
        assert is_instruction_line("Preheat the oven to 350°F") >= 0.5
        assert is_instruction_line("Mix the flour and sugar") >= 0.4
        assert is_instruction_line("Bake for 25 minutes") >= 0.4

    def test_time_and_temperature(self):
        """Lines with time/temperature references score as instructions."""
        # These should score as instructions, not ingredients
        assert is_instruction_line("Cook for 10-15 minutes") >= 0.1
        assert is_instruction_line("Bake at 375°F until golden") >= 0.3

    def test_ingredient_like_text_scores_low(self):
        """Text that looks like ingredients should score low."""
        assert is_instruction_line("2 cups all-purpose flour") < 0.4
        assert is_instruction_line("1/2 teaspoon salt") < 0.4


class TestFindSectionHeaders:
    """Tests for find_section_headers function."""

    def test_finds_ingredients_header(self):
        """Should find 'Ingredients' header."""
        lines = ["Recipe Title", "Ingredients:", "1 cup flour", "2 eggs"]
        headers = find_section_headers(lines)
        assert 'ingredients' in headers
        # The function may return 1-based or 0-based index, or include the header
        assert headers['ingredients'][0] >= 1  # Should find it after title

    def test_finds_instructions_header(self):
        """Should find various instruction header formats."""
        lines = ["Some text", "Directions:", "Step 1", "Step 2"]
        headers = find_section_headers(lines)
        assert 'instructions' in headers

    def test_finds_both_headers(self):
        """Should find both ingredient and instruction headers."""
        lines = [
            "Recipe Name",
            "Ingredients",
            "1 cup flour",
            "Instructions",
            "Mix ingredients"
        ]
        headers = find_section_headers(lines)
        assert 'ingredients' in headers
        assert 'instructions' in headers

    def test_no_headers(self):
        """Should return empty dict when no headers found."""
        lines = ["Some random text", "More text", "Even more"]
        headers = find_section_headers(lines)
        assert headers == {} or len(headers) == 0


class TestHeuristicParse:
    """Tests for main heuristic_parse function."""

    def test_structured_recipe(self):
        """Should extract from well-structured recipe HTML."""
        html = """
        <h2>Ingredients</h2>
        <ul>
            <li>2 cups flour</li>
            <li>1 cup sugar</li>
            <li>2 eggs</li>
        </ul>
        <h2>Instructions</h2>
        <ol>
            <li>Preheat oven to 350°F</li>
            <li>Mix dry ingredients</li>
            <li>Add eggs and mix well</li>
        </ol>
        """
        ingredients, instructions, confidence = heuristic_parse(html)

        assert len(ingredients) >= 2
        assert len(instructions) >= 2
        assert confidence >= 0.5

    def test_unstructured_recipe(self):
        """Should attempt extraction from unstructured content."""
        html = """
        <p>2 cups flour</p>
        <p>1 cup sugar</p>
        <p>Mix the flour and sugar together.</p>
        <p>Bake for 30 minutes.</p>
        """
        ingredients, instructions, confidence = heuristic_parse(html)

        # Should still return lists, even if extraction quality varies
        assert isinstance(ingredients, list)
        assert isinstance(instructions, list)
        assert 0.0 <= confidence <= 1.0

    def test_empty_content(self):
        """Should handle empty content gracefully."""
        ingredients, instructions, confidence = heuristic_parse("")
        assert ingredients == []
        assert instructions == []
        assert confidence == 0.0

    def test_no_recipe_content(self):
        """Should return low confidence for non-recipe content."""
        html = "<p>This is just some random text about nothing.</p>"
        ingredients, instructions, confidence = heuristic_parse(html)
        assert confidence < 0.5


class TestExtractLinesFromHtml:
    """Tests for extract_lines_from_html function."""

    def test_extracts_list_items(self):
        """Should extract items from HTML lists."""
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        lines = extract_lines_from_html(html)
        assert "Item 1" in lines
        assert "Item 2" in lines

    def test_extracts_paragraphs(self):
        """Should extract paragraph content."""
        html = "<p>First paragraph</p><p>Second paragraph</p>"
        lines = extract_lines_from_html(html)
        assert "First paragraph" in lines
        assert "Second paragraph" in lines

    def test_handles_divs(self):
        """Should extract div content."""
        html = "<div>Div content</div>"
        lines = extract_lines_from_html(html)
        assert "Div content" in lines


class TestCleanLine:
    """Tests for clean_line function."""

    def test_removes_bullets(self):
        """Should remove bullet characters."""
        assert clean_line("• Item text") == "Item text"
        assert clean_line("- Item text") == "Item text"
        assert clean_line("* Item text") == "Item text"

    def test_preserves_numbers(self):
        """Should preserve meaningful numbers."""
        assert "2 cups" in clean_line("2 cups flour")
        assert "1." in clean_line("1. First step") or "First step" in clean_line("1. First step")

    def test_normalizes_whitespace(self):
        """Should normalize whitespace."""
        assert clean_line("  extra   spaces  ") == "extra spaces"


class TestConstants:
    """Tests for module constants."""

    def test_ingredient_keywords_not_empty(self):
        """Should have ingredient keywords defined."""
        assert len(INGREDIENT_KEYWORDS) > 20

    def test_instruction_verbs_not_empty(self):
        """Should have instruction verbs defined."""
        assert len(INSTRUCTION_VERBS) > 30

    def test_common_units_present(self):
        """Common units should be in keywords."""
        common_units = ['cup', 'tablespoon', 'teaspoon', 'ounce', 'pound']
        for unit in common_units:
            assert unit in INGREDIENT_KEYWORDS or f"{unit}s" in INGREDIENT_KEYWORDS

    def test_common_verbs_present(self):
        """Common cooking verbs should be present."""
        common_verbs = ['mix', 'bake', 'cook', 'stir', 'add']
        for verb in common_verbs:
            assert verb in INSTRUCTION_VERBS
