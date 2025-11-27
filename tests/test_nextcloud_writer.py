"""Tests for the nextcloud_writer module."""

import json
import pytest
from pathlib import Path
from src.nextcloud_writer import (
    sanitize_folder_name,
    handle_duplicate_name,
    generate_recipe_json,
    get_first_image_resource,
    format_date_for_json,
)
from src.recipe_extractor import Recipe
from src.enex_parser import Resource


class TestSanitizeFolderName:
    """Tests for sanitize_folder_name function."""

    def test_normal_name(self):
        """Normal names should pass through."""
        assert sanitize_folder_name("Chicken Parmesan") == "Chicken Parmesan"

    def test_removes_invalid_characters(self):
        """Should remove filesystem-invalid characters."""
        assert "/" not in sanitize_folder_name("Recipe/Name")
        assert "\\" not in sanitize_folder_name("Recipe\\Name")
        assert ":" not in sanitize_folder_name("Recipe: Name")
        assert "*" not in sanitize_folder_name("Recipe*Name")
        assert "?" not in sanitize_folder_name("Recipe?Name")
        assert '"' not in sanitize_folder_name('Recipe"Name')
        assert "<" not in sanitize_folder_name("Recipe<Name")
        assert ">" not in sanitize_folder_name("Recipe>Name")
        assert "|" not in sanitize_folder_name("Recipe|Name")

    def test_collapses_spaces(self):
        """Should collapse multiple spaces."""
        assert sanitize_folder_name("Recipe   Name") == "Recipe Name"

    def test_trims_whitespace(self):
        """Should trim leading/trailing whitespace."""
        assert sanitize_folder_name("  Recipe Name  ") == "Recipe Name"

    def test_empty_name_fallback(self):
        """Should use fallback for empty names."""
        assert sanitize_folder_name("") == "Untitled Recipe"
        assert sanitize_folder_name("   ") == "Untitled Recipe"

    def test_truncates_long_names(self):
        """Should truncate very long names."""
        long_name = "A" * 300
        result = sanitize_folder_name(long_name)
        assert len(result) <= 200


class TestHandleDuplicateName:
    """Tests for handle_duplicate_name function."""

    def test_unique_name_unchanged(self, tmp_path):
        """Non-existing path should be returned unchanged."""
        base_path = tmp_path / "Recipe Name"
        result = handle_duplicate_name(base_path)
        assert result == base_path

    def test_duplicate_gets_number(self, tmp_path):
        """Existing path should get number appended."""
        base_path = tmp_path / "Recipe Name"
        base_path.mkdir()

        result = handle_duplicate_name(base_path)
        assert result == tmp_path / "Recipe Name (2)"

    def test_multiple_duplicates(self, tmp_path):
        """Multiple duplicates should increment number."""
        base_path = tmp_path / "Recipe Name"
        base_path.mkdir()
        (tmp_path / "Recipe Name (2)").mkdir()

        result = handle_duplicate_name(base_path)
        assert result == tmp_path / "Recipe Name (3)"


class TestGenerateRecipeJson:
    """Tests for generate_recipe_json function."""

    def test_required_fields_present(self):
        """Should include all required fields."""
        recipe = Recipe(
            name="Test Recipe",
            description="A test recipe",
            ingredients=["1 cup flour", "2 eggs"],
            instructions=["Mix", "Bake"],
            category="Desserts",
            keywords="test, recipe"
        )
        result = generate_recipe_json(recipe)

        assert result["@type"] == "Recipe"
        assert result["name"] == "Test Recipe"
        assert result["description"] == "A test recipe"
        assert result["recipeIngredient"] == ["1 cup flour", "2 eggs"]
        assert result["recipeInstructions"] == ["Mix", "Bake"]
        assert result["recipeCategory"] == "Desserts"
        assert result["keywords"] == "test, recipe"

    def test_omits_empty_optional_fields(self):
        """Should omit None/empty optional fields."""
        recipe = Recipe(
            name="Minimal Recipe",
            description="",
            ingredients=["item"],
            instructions=["step"],
            prep_time=None,
            cook_time=None,
            yields=None
        )
        result = generate_recipe_json(recipe)

        # These fields should either be absent or empty
        assert result.get("prepTime") is None or "prepTime" not in result
        assert result.get("cookTime") is None or "cookTime" not in result
        assert result.get("recipeYield") is None or "recipeYield" not in result

    def test_includes_times_when_present(self):
        """Should include time fields when provided."""
        recipe = Recipe(
            name="Timed Recipe",
            description="",
            ingredients=["item"],
            instructions=["step"],
            prep_time="PT20M",
            cook_time="PT30M",
            total_time="PT50M"
        )
        result = generate_recipe_json(recipe)

        assert result.get("prepTime") == "PT20M"
        assert result.get("cookTime") == "PT30M"
        assert result.get("totalTime") == "PT50M"

    def test_valid_json_output(self):
        """Result should be JSON-serializable."""
        recipe = Recipe(
            name="JSON Test",
            description="Testing JSON",
            ingredients=["item1", "item2"],
            instructions=["step1", "step2"]
        )
        result = generate_recipe_json(recipe)

        # Should not raise
        json_str = json.dumps(result)
        assert isinstance(json_str, str)

        # Should round-trip
        parsed = json.loads(json_str)
        assert parsed["name"] == "JSON Test"


class TestGetFirstImageResource:
    """Tests for get_first_image_resource function."""

    def test_no_resources(self):
        """Should return None when no resources."""
        result = get_first_image_resource({})
        assert result is None

    def test_finds_jpeg(self):
        """Should find JPEG image."""
        resource = Resource(
            data=b"fake image data",
            mime_type="image/jpeg",
            filename="photo.jpg",
            md5_hash="abc123"
        )
        resources = {"abc123": resource}

        result = get_first_image_resource(resources)
        assert result is not None
        assert result.mime_type == "image/jpeg"

    def test_finds_png(self):
        """Should find PNG image."""
        resource = Resource(
            data=b"fake png data",
            mime_type="image/png",
            filename="photo.png",
            md5_hash="def456"
        )
        resources = {"def456": resource}

        result = get_first_image_resource(resources)
        assert result is not None
        assert result.mime_type == "image/png"

    def test_ignores_non_images(self):
        """Should ignore non-image resources."""
        resource = Resource(
            data=b"fake pdf data",
            mime_type="application/pdf",
            filename="doc.pdf",
            md5_hash="ghi789"
        )
        resources = {"ghi789": resource}

        result = get_first_image_resource(resources)
        assert result is None


class TestFormatDateForJson:
    """Tests for format_date_for_json function."""

    def test_iso_datetime(self):
        """Should convert ISO datetime to date."""
        result = format_date_for_json("2024-01-15T10:30:00Z")
        assert result == "2024-01-15"

    def test_already_date(self):
        """Should handle date-only format."""
        result = format_date_for_json("2024-01-15")
        assert result == "2024-01-15"

    def test_empty_string(self):
        """Should handle empty string."""
        result = format_date_for_json("")
        assert result == ""

    def test_preserves_valid_date(self):
        """Should preserve valid date format."""
        result = format_date_for_json("2024-12-25")
        assert result == "2024-12-25"
