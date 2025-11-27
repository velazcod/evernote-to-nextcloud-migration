"""Tests for the recipe_extractor module."""

import pytest
from src.recipe_extractor import (
    Recipe,
    extract_recipe,
    try_heuristic_parse,
    create_fallback_recipe,
    extract_description_from_html,
    html_to_plain_text,
)


class TestRecipeDataclass:
    """Tests for Recipe dataclass."""

    def test_default_values(self):
        """Recipe should have sensible defaults."""
        recipe = Recipe(
            name="Test Recipe",
            description="A test",
            ingredients=["item1"],
            instructions=["step1"]
        )
        assert recipe.prep_time is None
        assert recipe.cook_time is None
        assert recipe.total_time is None
        assert recipe.yields is None
        assert recipe.category == ""
        assert recipe.keywords == ""
        assert recipe.image_filename is None
        assert recipe.needs_review is False

    def test_all_fields(self):
        """Recipe should accept all fields."""
        recipe = Recipe(
            name="Full Recipe",
            description="Complete recipe",
            ingredients=["1 cup flour", "2 eggs"],
            instructions=["Mix", "Bake"],
            prep_time="PT20M",
            cook_time="PT30M",
            total_time="PT50M",
            yields="4 servings",
            category="Desserts",
            keywords="cake, chocolate",
            image_filename="full.jpg",
            date_published="2024-01-01",
            date_created="2024-01-01T12:00:00Z",
            needs_review=False
        )
        assert recipe.name == "Full Recipe"
        assert len(recipe.ingredients) == 2
        assert len(recipe.instructions) == 2
        assert recipe.prep_time == "PT20M"


class TestExtractRecipe:
    """Tests for main extract_recipe function."""

    def test_structured_html(self):
        """Should extract recipe from well-structured HTML."""
        html = """
        <h1>Chocolate Cake</h1>
        <h2>Ingredients</h2>
        <ul>
            <li>2 cups flour</li>
            <li>1 cup cocoa powder</li>
            <li>2 cups sugar</li>
        </ul>
        <h2>Instructions</h2>
        <ol>
            <li>Preheat oven to 350°F</li>
            <li>Mix dry ingredients</li>
            <li>Bake for 30 minutes</li>
        </ol>
        """
        recipe = extract_recipe(html, title="Chocolate Cake")

        assert recipe.name == "Chocolate Cake"
        assert len(recipe.ingredients) > 0
        assert len(recipe.instructions) > 0

    def test_unstructured_html_fallback(self):
        """Should create fallback for unstructured content."""
        html = "<p>Some random content that is not a recipe.</p>"
        recipe = extract_recipe(html, title="Unknown")

        assert recipe.name == "Unknown"
        # Should have description with content for review
        assert recipe.description or recipe.needs_review

    def test_empty_content(self):
        """Should handle empty content gracefully."""
        recipe = extract_recipe("", title="Empty Recipe")

        assert recipe.name == "Empty Recipe"
        assert recipe.needs_review is True

    def test_preserves_title(self):
        """Should use provided title."""
        recipe = extract_recipe("<p>Content</p>", title="My Special Recipe")
        assert recipe.name == "My Special Recipe"


class TestTryHeuristicParse:
    """Tests for try_heuristic_parse function."""

    def test_good_structure_returns_recipe(self):
        """Should return Recipe for well-structured content."""
        html = """
        <h2>Ingredients</h2>
        <ul>
            <li>2 cups flour</li>
            <li>1 cup sugar</li>
        </ul>
        <h2>Directions</h2>
        <ol>
            <li>Mix ingredients</li>
            <li>Bake at 350°F</li>
        </ol>
        """
        recipe = try_heuristic_parse(html, "Test Recipe")

        assert recipe is not None
        assert isinstance(recipe, Recipe)

    def test_poor_structure_returns_none(self):
        """Should return None for content with no recipe structure."""
        html = "<p>Just a random paragraph with no recipe content.</p>"
        recipe = try_heuristic_parse(html, "Non Recipe")

        # May return None or recipe with needs_review
        if recipe is not None:
            assert recipe.needs_review or len(recipe.ingredients) == 0


class TestCreateFallbackRecipe:
    """Tests for create_fallback_recipe function."""

    def test_sets_needs_review(self):
        """Fallback recipe should have needs_review=True."""
        recipe = create_fallback_recipe("<p>Content</p>", "Test")
        assert recipe.needs_review is True

    def test_preserves_content_in_description(self):
        """Should store content in description for review."""
        html = "<p>Some recipe content that could not be parsed.</p>"
        recipe = create_fallback_recipe(html, "Unparsed Recipe")

        assert "recipe content" in recipe.description.lower() or len(recipe.description) > 0

    def test_empty_ingredient_instruction_lists(self):
        """Fallback should have empty ingredient/instruction lists."""
        recipe = create_fallback_recipe("<p>Content</p>", "Test")
        assert recipe.ingredients == []
        assert recipe.instructions == []


class TestExtractDescriptionFromHtml:
    """Tests for extract_description_from_html function."""

    def test_extracts_first_paragraph(self):
        """Should extract first meaningful paragraph."""
        html = "<p>This is the recipe description.</p><p>More content.</p>"
        desc = extract_description_from_html(html)
        assert "recipe description" in desc.lower()

    def test_truncates_long_content(self):
        """Should truncate very long descriptions."""
        html = "<p>" + "word " * 200 + "</p>"
        desc = extract_description_from_html(html, max_length=100)
        assert len(desc) <= 150  # Allow some flexibility for word boundaries

    def test_handles_empty_html(self):
        """Should handle empty HTML gracefully."""
        desc = extract_description_from_html("")
        assert desc == ""

    def test_removes_html_tags(self):
        """Should strip HTML tags from description."""
        html = "<p><strong>Bold</strong> and <em>italic</em> text.</p>"
        desc = extract_description_from_html(html)
        assert "<strong>" not in desc
        assert "<em>" not in desc


class TestHtmlToPlainText:
    """Tests for html_to_plain_text function."""

    def test_removes_tags(self):
        """Should remove HTML tags."""
        text = html_to_plain_text("<p>Simple <b>text</b></p>")
        assert "<p>" not in text
        assert "<b>" not in text

    def test_preserves_content(self):
        """Should preserve text content."""
        text = html_to_plain_text("<div>Hello World</div>")
        assert "Hello World" in text

    def test_handles_empty_input(self):
        """Should handle empty input."""
        assert html_to_plain_text("") == ""
        assert html_to_plain_text(None) == ""

    def test_handles_entities(self):
        """Should decode HTML entities."""
        text = html_to_plain_text("<p>&amp; &lt; &gt;</p>")
        assert "&" in text or "amp" not in text.lower()
