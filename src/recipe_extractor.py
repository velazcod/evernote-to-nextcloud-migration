"""
Recipe extraction module with 3-tier fallback strategy.

This module converts HTML content from Evernote notes into structured recipe data.
It implements a progressive fallback approach:
1. recipe-scrapers library (for web-clipped recipes)
2. Heuristic pattern matching (for unstructured content)
3. Raw content fallback (for manual review)
"""

import logging
from dataclasses import dataclass
from typing import Optional
from bs4 import BeautifulSoup
import html2text

logger = logging.getLogger(__name__)

# Import heuristics module for Tier 2
try:
    from src.heuristics import heuristic_parse
except ImportError:
    from heuristics import heuristic_parse

# Import recipe-scrapers for Tier 1
try:
    from recipe_scrapers import scrape_html
    RECIPE_SCRAPERS_AVAILABLE = True
except ImportError:
    logger.warning("recipe-scrapers not available - Tier 1 extraction disabled")
    RECIPE_SCRAPERS_AVAILABLE = False


# ==============================================================================
# DATA CLASS
# ==============================================================================

@dataclass
class Recipe:
    """
    Structured recipe data for Nextcloud Cookbook export.

    Attributes:
        name: Recipe title
        description: Short description or summary
        ingredients: List of ingredient strings
        instructions: List of instruction/step strings
        prep_time: Preparation time in ISO 8601 duration format (e.g., "PT20M")
        cook_time: Cooking time in ISO 8601 duration format
        total_time: Total time in ISO 8601 duration format
        yields: Serving size/yield (e.g., "4 servings")
        category: Recipe category (set from ENEX filename)
        keywords: Comma-separated tags (set from Evernote tags)
        image_filename: Filename for recipe image (set during file writing)
        date_published: Publication date in ISO 8601 format
        date_created: Creation date in ISO 8601 format
        needs_review: Flag indicating fallback was used and manual review needed
    """
    name: str
    description: str
    ingredients: list[str]
    instructions: list[str]
    prep_time: Optional[str] = None
    cook_time: Optional[str] = None
    total_time: Optional[str] = None
    yields: Optional[str] = None
    category: str = ""
    keywords: str = ""
    image_filename: Optional[str] = None
    date_published: str = ""
    date_created: str = ""
    needs_review: bool = False


# ==============================================================================
# TIER 1: recipe-scrapers LIBRARY
# ==============================================================================

def try_recipe_scrapers(html_content: str, source_url: str) -> Optional[Recipe]:
    """
    Attempt to extract recipe using the recipe-scrapers library.

    This works well for web-clipped recipes that have schema.org metadata
    or are from known recipe websites.

    Args:
        html_content: HTML content from Evernote note
        source_url: Original URL of the web-clipped recipe

    Returns:
        Recipe object if extraction successful, None otherwise
    """
    if not RECIPE_SCRAPERS_AVAILABLE:
        logger.debug("recipe-scrapers library not available")
        return None

    if not source_url:
        logger.debug("No source URL provided for recipe-scrapers")
        return None

    try:
        logger.info(f"Attempting recipe-scrapers extraction from {source_url}")
        scraper = scrape_html(html=html_content, org_url=source_url)

        # Extract all available data from scraper
        recipe = Recipe(
            name=scraper.title() or "Untitled Recipe",
            description=_safe_scraper_call(scraper.description) or "",
            ingredients=_safe_scraper_call(scraper.ingredients) or [],
            instructions=_safe_scraper_call(scraper.instructions_list) or [],
            prep_time=_convert_minutes_to_iso(_safe_scraper_call(scraper.prep_time)),
            cook_time=_convert_minutes_to_iso(_safe_scraper_call(scraper.cook_time)),
            total_time=_convert_minutes_to_iso(_safe_scraper_call(scraper.total_time)),
            yields=_safe_scraper_call(scraper.yields),
            needs_review=False
        )

        # Validate that we got meaningful data
        if not recipe.ingredients and not recipe.instructions:
            logger.warning("recipe-scrapers returned empty ingredients and instructions")
            return None

        logger.info(f"recipe-scrapers extraction successful: {len(recipe.ingredients)} ingredients, "
                   f"{len(recipe.instructions)} instructions")
        return recipe

    except Exception as e:
        logger.warning(f"recipe-scrapers extraction failed: {e}")
        return None


def _safe_scraper_call(method):
    """
    Safely call a scraper method that might not be implemented.

    Args:
        method: Scraper method to call (already bound)

    Returns:
        Method result or None if error
    """
    try:
        return method()
    except (NotImplementedError, AttributeError, Exception):
        return None


def _convert_minutes_to_iso(minutes: Optional[int]) -> Optional[str]:
    """
    Convert minutes to ISO 8601 duration format.

    Args:
        minutes: Duration in minutes

    Returns:
        ISO 8601 duration string (e.g., "PT20M") or None
    """
    if minutes is None or minutes <= 0:
        return None

    # Handle hours if >= 60 minutes
    if minutes >= 60:
        hours = minutes // 60
        remaining_mins = minutes % 60
        if remaining_mins > 0:
            return f"PT{hours}H{remaining_mins}M"
        else:
            return f"PT{hours}H"
    else:
        return f"PT{minutes}M"


# ==============================================================================
# TIER 2: HEURISTIC PARSING
# ==============================================================================

def try_heuristic_parse(html_content: str, title: str = "Untitled Recipe") -> Optional[Recipe]:
    """
    Attempt to extract recipe using pattern matching heuristics.

    Uses the heuristics module to identify ingredients and instructions
    based on common patterns and keywords.

    Args:
        html_content: HTML content from Evernote note
        title: Recipe title to use if extraction succeeds

    Returns:
        Recipe object if confidence >= 0.5, None otherwise
    """
    try:
        logger.info("Attempting heuristic parsing")
        ingredients, instructions, confidence = heuristic_parse(html_content)

        logger.debug(f"Heuristic parse results: confidence={confidence:.2f}, "
                    f"{len(ingredients)} ingredients, {len(instructions)} instructions")

        # Only accept results with reasonable confidence
        if confidence < 0.5:
            logger.warning(f"Heuristic confidence too low: {confidence:.2f}")
            return None

        # Require at least some ingredients or instructions
        if not ingredients and not instructions:
            logger.warning("Heuristic parsing returned no ingredients or instructions")
            return None

        # Extract a description from the HTML
        description = extract_description_from_html(html_content)

        recipe = Recipe(
            name=title,
            description=description,
            ingredients=ingredients,
            instructions=instructions,
            needs_review=False  # Confidence is acceptable
        )

        logger.info(f"Heuristic parsing successful (confidence={confidence:.2f})")
        return recipe

    except Exception as e:
        logger.error(f"Heuristic parsing failed with exception: {e}", exc_info=True)
        return None


# ==============================================================================
# TIER 3: FALLBACK
# ==============================================================================

def create_fallback_recipe(html_content: str, title: str = "Untitled Recipe") -> Recipe:
    """
    Create a fallback recipe with raw content for manual review.

    This is the last resort when structured extraction fails. The raw
    HTML content is converted to plain text and stored in the description
    field for manual review and editing in Nextcloud Cookbook.

    Args:
        html_content: HTML content from Evernote note
        title: Recipe title

    Returns:
        Recipe object with needs_review=True
    """
    logger.warning(f"Creating fallback recipe for: {title}")

    # Convert HTML to clean plain text
    plain_text = html_to_plain_text(html_content)

    recipe = Recipe(
        name=title,
        description=plain_text,
        ingredients=[],
        instructions=[],
        needs_review=True
    )

    logger.info(f"Fallback recipe created: {len(plain_text)} characters")
    return recipe


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def extract_description_from_html(html_content: str, max_length: int = 500) -> str:
    """
    Extract a short description from the beginning of HTML content.

    Attempts to find the first meaningful paragraph or text block to use
    as a recipe description.

    Args:
        html_content: HTML content to extract from
        max_length: Maximum description length in characters

    Returns:
        Extracted description text
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        # Remove unwanted elements
        for element in soup(['script', 'style', 'meta', 'link']):
            element.decompose()

        # Try to find first paragraph
        first_p = soup.find('p')
        if first_p:
            text = first_p.get_text(strip=True)
            if text and len(text) > 20:  # Meaningful content
                return text[:max_length]

        # Fallback: get all text and take first chunk
        all_text = soup.get_text(separator=' ', strip=True)
        if all_text:
            # Take first sentence or max_length characters
            sentences = all_text.split('. ')
            if sentences and len(sentences[0]) < max_length:
                return sentences[0] + '.'
            return all_text[:max_length]

        return ""

    except Exception as e:
        logger.warning(f"Failed to extract description: {e}")
        return ""


def html_to_plain_text(html_content: str) -> str:
    """
    Convert HTML to clean plain text.

    Uses html2text library to convert HTML to readable plain text format,
    preserving basic structure like lists and paragraphs.

    Args:
        html_content: HTML content to convert

    Returns:
        Plain text representation
    """
    if not html_content:
        return ""

    try:
        # Configure html2text
        h = html2text.HTML2Text()
        h.ignore_links = False  # Keep URLs for reference
        h.ignore_images = True
        h.ignore_emphasis = False  # Keep bold/italic markers
        h.body_width = 0  # Don't wrap lines
        h.unicode_snob = True  # Use unicode characters

        # Convert HTML to text
        text = h.handle(html_content)

        # Clean up excessive blank lines
        lines = text.split('\n')
        cleaned_lines = []
        prev_blank = False

        for line in lines:
            is_blank = not line.strip()
            if is_blank and prev_blank:
                continue  # Skip consecutive blank lines
            cleaned_lines.append(line)
            prev_blank = is_blank

        return '\n'.join(cleaned_lines).strip()

    except Exception as e:
        logger.error(f"html2text conversion failed: {e}")

        # Fallback: simple text extraction with BeautifulSoup
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            return soup.get_text(separator='\n', strip=True)
        except Exception as e2:
            logger.error(f"BeautifulSoup fallback failed: {e2}")
            return html_content  # Last resort: return raw HTML


# ==============================================================================
# MAIN EXTRACTION FUNCTION
# ==============================================================================

def extract_recipe(
    html_content: str,
    source_url: Optional[str] = None,
    title: str = "Untitled Recipe"
) -> Recipe:
    """
    Extract recipe data from HTML content using 3-tier fallback strategy.

    Extraction tiers (tried in order):
    1. recipe-scrapers library (if source_url provided)
    2. Heuristic pattern matching
    3. Fallback with raw content (always succeeds)

    Args:
        html_content: HTML content from Evernote note
        source_url: Original URL if web-clipped (enables Tier 1)
        title: Recipe title from note title

    Returns:
        Recipe object with extracted data
    """
    logger.info(f"Extracting recipe: {title}")

    if not html_content or not html_content.strip():
        logger.warning(f"Empty HTML content for recipe: {title}")
        return create_fallback_recipe("<p>No content</p>", title)

    # Tier 1: Try recipe-scrapers if we have a source URL
    if source_url:
        recipe = try_recipe_scrapers(html_content, source_url)
        if recipe:
            logger.info(f"Tier 1 (recipe-scrapers) successful for: {title}")
            recipe.name = title  # Use Evernote title instead of scraped title
            return recipe

    # Tier 2: Try heuristic parsing
    recipe = try_heuristic_parse(html_content, title)
    if recipe:
        logger.info(f"Tier 2 (heuristics) successful for: {title}")
        return recipe

    # Tier 3: Fallback to raw content
    logger.info(f"Tier 3 (fallback) used for: {title}")
    return create_fallback_recipe(html_content, title)
