"""
Write recipe data to Nextcloud Cookbook format.

This module handles:
- Sanitizing recipe names for filesystem compatibility
- Creating output folders with duplicate handling
- Generating recipe.json in schema.org Recipe format
- Writing images as full.jpg
- Dry-run mode for testing
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Import from other modules
try:
    from src.recipe_extractor import Recipe
    from src.enex_parser import Resource
except ImportError:
    from recipe_extractor import Recipe
    from enex_parser import Resource


# ==============================================================================
# CONSTANTS
# ==============================================================================

# Characters invalid in filesystem names
INVALID_CHARS = r'[/\\:*?"<>|]'

# Maximum folder name length (conservative for cross-platform compatibility)
MAX_FOLDER_NAME_LENGTH = 200

# Image MIME types to recognize
IMAGE_MIME_TYPES = {
    'image/jpeg',
    'image/jpg',
    'image/png',
    'image/gif',
    'image/webp',
    'image/bmp'
}


# ==============================================================================
# FOLDER NAME SANITIZATION
# ==============================================================================

def sanitize_folder_name(name: str) -> str:
    """
    Make a recipe name filesystem-safe.

    Removes or replaces characters that are invalid in folder names
    across common filesystems (Windows, macOS, Linux).

    Args:
        name: Recipe name to sanitize

    Returns:
        Sanitized folder name

    Examples:
        >>> sanitize_folder_name("Chicken: The Best")
        'Chicken The Best'
        >>> sanitize_folder_name("  Pasta & Sauce  ")
        'Pasta & Sauce'
        >>> sanitize_folder_name("Recipe/With/Slashes")
        'RecipeWithSlashes'
    """
    if not name or not name.strip():
        return "Untitled Recipe"

    # Remove invalid characters
    sanitized = re.sub(INVALID_CHARS, '', name)

    # Collapse multiple spaces to single space
    sanitized = re.sub(r'\s+', ' ', sanitized)

    # Trim whitespace
    sanitized = sanitized.strip()

    # Handle empty result after sanitization
    if not sanitized:
        return "Untitled Recipe"

    # Truncate if too long, break at word boundary
    if len(sanitized) > MAX_FOLDER_NAME_LENGTH:
        sanitized = sanitized[:MAX_FOLDER_NAME_LENGTH]
        # Try to break at last space to avoid cutting words
        last_space = sanitized.rfind(' ')
        if last_space > 0:
            sanitized = sanitized[:last_space]

    return sanitized


def handle_duplicate_name(base_path: Path) -> Path:
    """
    Handle duplicate folder names by appending a number.

    If the folder already exists, appends " (2)", " (3)", etc.
    until a unique name is found.

    Args:
        base_path: Desired folder path

    Returns:
        Unique folder path (may be same as input if no conflict)

    Examples:
        If "Chicken Parmesan" exists:
        >>> handle_duplicate_name(Path("output/Chicken Parmesan"))
        Path("output/Chicken Parmesan (2)")
    """
    if not base_path.exists():
        return base_path

    logger.debug(f"Folder already exists: {base_path}")

    counter = 2
    while True:
        new_path = base_path.parent / f"{base_path.name} ({counter})"
        if not new_path.exists():
            logger.info(f"Using deduplicated name: {new_path.name}")
            return new_path
        counter += 1


# ==============================================================================
# IMAGE HANDLING
# ==============================================================================

def get_first_image_resource(resources: dict[str, Resource]) -> Optional[Resource]:
    """
    Get the first image resource from a resources dictionary.

    Searches through resources to find the first one with an image MIME type.

    Args:
        resources: Dict mapping MD5 hash to Resource objects

    Returns:
        First image Resource found, or None if no images
    """
    for resource in resources.values():
        if resource.mime_type.lower() in IMAGE_MIME_TYPES:
            logger.debug(f"Found image: {resource.mime_type}, {len(resource.data)} bytes")
            return resource

    return None


def write_image(
    resource: Resource,
    recipe_dir: Path,
    dry_run: bool = False
) -> Optional[str]:
    """
    Write an image resource as full.jpg in the recipe directory.

    The Nextcloud Cookbook expects the main recipe image to be named "full.jpg".

    Args:
        resource: Image resource to write
        recipe_dir: Directory to write image to
        dry_run: If True, only log what would be done

    Returns:
        "full.jpg" if written successfully, None otherwise

    Raises:
        OSError: If writing fails (not in dry-run mode)
    """
    # Determine output filename based on MIME type
    # Nextcloud Cookbook expects "full.jpg" but we preserve original extension
    mime_to_ext = {
        'image/jpeg': 'jpg',
        'image/jpg': 'jpg',
        'image/png': 'png',
        'image/gif': 'gif',
        'image/webp': 'webp',
        'image/bmp': 'bmp'
    }

    ext = mime_to_ext.get(resource.mime_type.lower(), 'jpg')
    filename = f"full.{ext}"
    image_path = recipe_dir / filename

    if dry_run:
        logger.info(f"[DRY RUN] Would write image: {image_path} ({len(resource.data)} bytes)")
        return filename

    try:
        image_path.write_bytes(resource.data)
        logger.debug(f"Wrote image: {image_path} ({len(resource.data)} bytes)")
        return filename

    except OSError as e:
        logger.error(f"Failed to write image {image_path}: {e}")
        raise


# ==============================================================================
# RECIPE JSON GENERATION
# ==============================================================================

def format_date_for_json(iso_datetime: str) -> str:
    """
    Convert ISO datetime string to YYYY-MM-DD format for datePublished.

    Args:
        iso_datetime: ISO 8601 datetime string (e.g., "2024-01-01T12:00:00Z")

    Returns:
        Date in YYYY-MM-DD format (e.g., "2024-01-01")
    """
    if not iso_datetime:
        return ""

    try:
        # Parse ISO datetime and extract date portion
        dt = datetime.fromisoformat(iso_datetime.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d')
    except (ValueError, AttributeError):
        # Fallback if parsing fails
        logger.warning(f"Could not parse datetime: {iso_datetime}")
        return ""


def generate_recipe_json(recipe: Recipe) -> dict:
    """
    Convert Recipe dataclass to Nextcloud Cookbook JSON format.

    Follows schema.org Recipe specification. Omits optional fields
    that are None or empty to keep JSON clean.

    Args:
        recipe: Recipe dataclass with structured data

    Returns:
        Dictionary ready for JSON serialization

    Example output:
        {
            "@type": "Recipe",
            "name": "Chicken Parmesan",
            "description": "Classic Italian-American dish...",
            "recipeIngredient": ["4 chicken breasts", "1 cup breadcrumbs"],
            "recipeInstructions": ["Preheat oven to 400°F", "Pound chicken"],
            "prepTime": "PT20M",
            "cookTime": "PT25M",
            "totalTime": "PT45M",
            "recipeYield": "4 servings",
            "recipeCategory": "Main Dishes",
            "keywords": "dinner, italian, chicken",
            "image": "full.jpg",
            "datePublished": "2024-01-01",
            "dateCreated": "2024-01-01T12:00:00Z"
        }
    """
    # Start with required fields
    recipe_dict = {
        "@type": "Recipe",
        "name": recipe.name or "Untitled Recipe",
        "recipeIngredient": recipe.ingredients or [],
        "recipeInstructions": recipe.instructions or []
    }

    # Add optional fields only if they have values
    if recipe.description:
        recipe_dict["description"] = recipe.description

    if recipe.prep_time:
        recipe_dict["prepTime"] = recipe.prep_time

    if recipe.cook_time:
        recipe_dict["cookTime"] = recipe.cook_time

    if recipe.total_time:
        recipe_dict["totalTime"] = recipe.total_time

    if recipe.yields:
        recipe_dict["recipeYield"] = recipe.yields

    if recipe.category:
        recipe_dict["recipeCategory"] = recipe.category

    if recipe.keywords:
        recipe_dict["keywords"] = recipe.keywords

    if recipe.image_filename:
        recipe_dict["image"] = recipe.image_filename

    # Handle dates
    if recipe.date_created:
        recipe_dict["dateCreated"] = recipe.date_created
        # Also set datePublished to same value (YYYY-MM-DD format)
        recipe_dict["datePublished"] = format_date_for_json(recipe.date_created)
    elif recipe.date_published:
        recipe_dict["datePublished"] = recipe.date_published

    return recipe_dict


# ==============================================================================
# MAIN WRITE FUNCTION
# ==============================================================================

def write_recipe(
    recipe: Recipe,
    resources: dict[str, Resource],
    output_dir: str | Path,
    dry_run: bool = False
) -> str:
    """
    Write a recipe to the output directory in Nextcloud Cookbook format.

    Creates a folder named after the recipe (sanitized) containing:
    - recipe.json: Recipe data in schema.org format
    - full.jpg (or .png, etc.): First image from resources (if available)

    Args:
        recipe: Recipe dataclass with structured data
        resources: Dict mapping MD5 hash to Resource objects
        output_dir: Base output directory
        dry_run: If True, only log what would be created without writing files

    Returns:
        Path to created recipe folder (as string)

    Raises:
        OSError: If directory creation or file writing fails

    Example:
        >>> write_recipe(
        ...     recipe=Recipe(name="Chicken Parmesan", ...),
        ...     resources={"abc123": Resource(...)},
        ...     output_dir="./output",
        ...     dry_run=False
        ... )
        './output/Chicken Parmesan'
    """
    output_dir = Path(output_dir)

    # Sanitize recipe name for folder name
    folder_name = sanitize_folder_name(recipe.name)
    recipe_path = output_dir / folder_name

    # Handle duplicate folder names
    recipe_path = handle_duplicate_name(recipe_path)

    if dry_run:
        logger.info(f"[DRY RUN] Would create folder: {recipe_path}")
    else:
        # Create recipe folder
        try:
            recipe_path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created folder: {recipe_path}")
        except OSError as e:
            logger.error(f"Failed to create folder {recipe_path}: {e}")
            raise

    # Handle image if available
    image_resource = get_first_image_resource(resources)
    if image_resource:
        try:
            image_filename = write_image(image_resource, recipe_path, dry_run)
            # Update recipe with image filename
            recipe.image_filename = image_filename
        except OSError as e:
            logger.warning(f"Could not write image for {recipe.name}: {e}")
            # Continue without image

    # Generate recipe.json
    recipe_data = generate_recipe_json(recipe)

    if dry_run:
        logger.info(f"[DRY RUN] Would write recipe.json:")
        logger.info(f"[DRY RUN] {json.dumps(recipe_data, indent=2, ensure_ascii=False)}")
    else:
        # Write recipe.json
        recipe_json_path = recipe_path / "recipe.json"
        try:
            with recipe_json_path.open('w', encoding='utf-8') as f:
                json.dump(recipe_data, f, indent=2, ensure_ascii=False)
                f.write('\n')  # Add trailing newline
            logger.info(f"Wrote recipe: {recipe_path.name}")
        except OSError as e:
            logger.error(f"Failed to write {recipe_json_path}: {e}")
            raise

    return str(recipe_path)


# ==============================================================================
# BATCH OPERATIONS
# ==============================================================================

def write_recipes(
    recipes: list[tuple[Recipe, dict[str, Resource]]],
    output_dir: str | Path,
    dry_run: bool = False
) -> list[str]:
    """
    Write multiple recipes to output directory.

    Convenience function for batch operations.

    Args:
        recipes: List of (Recipe, resources) tuples
        output_dir: Base output directory
        dry_run: If True, only log what would be created

    Returns:
        List of created recipe folder paths

    Example:
        >>> recipes = [
        ...     (recipe1, resources1),
        ...     (recipe2, resources2)
        ... ]
        >>> write_recipes(recipes, "./output")
        ['./output/Chicken Parmesan', './output/Beef Tacos']
    """
    created_paths = []

    for recipe, resources in recipes:
        try:
            path = write_recipe(recipe, resources, output_dir, dry_run)
            created_paths.append(path)
        except Exception as e:
            logger.error(f"Failed to write recipe '{recipe.name}': {e}")
            # Continue with remaining recipes

    logger.info(f"Wrote {len(created_paths)} of {len(recipes)} recipes")
    return created_paths
