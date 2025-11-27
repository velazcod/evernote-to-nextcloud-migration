"""
Recipe heuristics module for pattern-based extraction of ingredients and instructions.

This module provides pattern matching functions to identify recipe components in
unstructured HTML content. It implements a scoring-based approach to classify
lines as ingredients vs instructions when clear section headers are not present.
"""

import re
import logging
from typing import Tuple, Dict, List
from bs4 import BeautifulSoup
import html2text

logger = logging.getLogger(__name__)

# ==============================================================================
# INGREDIENT PATTERNS
# ==============================================================================

# Regex patterns that indicate a line is likely an ingredient
INGREDIENT_PATTERNS = [
    r'^\d+[\s/\d]*\s*(cup|cups|tbsp|tsp|tablespoon|tablespoons|teaspoon|teaspoons|oz|ounce|ounces|lb|lbs|pound|pounds|g|gram|grams|kg|kilogram|ml|milliliter|l|liter)',
    # Starts with quantity + unit: "2 cups flour"

    r'^\d+[\s/\d]*\s+\w+',
    # Starts with number + word: "3 eggs", "1/2 onion"

    r'^[\u00BC-\u00BE\u2150-\u215E]',
    # Starts with fraction character: ¼, ½, ¾, ⅓, ⅔, etc.

    r'^[-•*]\s*\d',
    # Bullet + number: "- 2 eggs", "• 1 cup"

    r'^\d+\s*[-–]\s*\d+',
    # Range: "2-3 cloves", "1-2 pounds"
]

# Common measurement units and ingredient-related keywords
INGREDIENT_KEYWORDS = [
    'cup', 'cups', 'tablespoon', 'tablespoons', 'tbsp', 'tbs',
    'teaspoon', 'teaspoons', 'tsp', 'ounce', 'ounces', 'oz',
    'pound', 'pounds', 'lb', 'lbs', 'gram', 'grams', 'g',
    'kilogram', 'kilograms', 'kg', 'milliliter', 'milliliters', 'ml',
    'liter', 'liters', 'l', 'quart', 'quarts', 'qt', 'pint', 'pints', 'pt',
    'gallon', 'gallons', 'gal', 'fluid', 'fl',
    'pinch', 'dash', 'clove', 'cloves', 'bunch', 'bunches', 'handful',
    'package', 'packages', 'pkg', 'can', 'cans', 'jar', 'jars',
    'slice', 'slices', 'piece', 'pieces', 'whole', 'half', 'halves',
    'chopped', 'diced', 'minced', 'sliced', 'grated', 'shredded',
    'fresh', 'dried', 'frozen', 'canned', 'cooked', 'raw',
    'large', 'medium', 'small', 'extra', 'optional',
]

# Section headers that indicate ingredient list
INGREDIENT_HEADERS = [
    'ingredients', 'ingredient', 'you will need', "you'll need",
    'what you need', 'shopping list', 'grocery list',
    'for the', 'for garnish', 'for serving', 'for topping',
]

# ==============================================================================
# INSTRUCTION PATTERNS
# ==============================================================================

# Regex patterns that indicate a line is likely an instruction/step
INSTRUCTION_PATTERNS = [
    r'^\d+[\.\)]\s+',
    # Numbered step: "1. Mix" or "1) Mix"

    r'^step\s+\d+',
    # "Step 1", "Step 2", etc. (case insensitive handled separately)

    r'^\d+\.\s*[A-Z]',
    # Numbered step starting with capital: "1. Preheat"
]

# Common cooking action verbs
INSTRUCTION_VERBS = [
    'preheat', 'heat', 'warm', 'boil', 'simmer', 'reduce', 'cook',
    'fry', 'sauté', 'saute', 'pan-fry', 'stir-fry',
    'bake', 'roast', 'broil', 'grill', 'barbecue',
    'steam', 'poach', 'blanch', 'parboil',
    'mix', 'stir', 'whisk', 'beat', 'blend', 'fold', 'combine', 'incorporate',
    'chop', 'dice', 'mince', 'slice', 'cut', 'julienne', 'cube',
    'trim', 'peel', 'core', 'seed', 'debone', 'skin',
    'add', 'pour', 'drizzle', 'pour in', 'stir in', 'mix in',
    'place', 'put', 'set', 'arrange', 'lay', 'spread',
    'season', 'sprinkle', 'coat', 'brush', 'rub', 'marinate',
    'cover', 'wrap', 'seal', 'close', 'uncover',
    'bring', 'let', 'allow', 'leave', 'keep', 'maintain',
    'rest', 'cool', 'chill', 'refrigerate', 'freeze',
    'remove', 'discard', 'drain', 'strain', 'squeeze', 'press',
    'transfer', 'move', 'flip', 'turn', 'rotate', 'shake',
    'serve', 'garnish', 'top', 'finish', 'plate', 'present',
    'enjoy', 'taste', 'adjust', 'check', 'test',
    'reduce', 'thicken', 'dissolve', 'melt', 'caramelize',
    'brown', 'sear', 'char', 'toast', 'crisp',
]

# Section headers that indicate instruction list
INSTRUCTION_HEADERS = [
    'instructions', 'instruction', 'directions', 'direction',
    'method', 'methods', 'steps', 'procedure', 'procedures',
    'how to make', 'how to prepare', 'preparation',
    'cooking instructions', 'cooking directions', 'cooking method',
    'to make', 'to prepare', 'making', 'preparing',
    'technique', 'techniques', 'proceso', 'preparación',  # Added missing
]

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def clean_line(line: str) -> str:
    """
    Clean up a line of text by normalizing whitespace and removing formatting.

    Args:
        line: Raw text line

    Returns:
        Cleaned line with normalized whitespace
    """
    # Remove excessive whitespace
    line = ' '.join(line.split())

    # Remove leading bullets/markers (but keep the content)
    line = re.sub(r'^[•\-*◦▪▫○●]\s*', '', line)

    # Remove trailing punctuation that might interfere with scoring
    line = line.strip()

    return line


def extract_list_items(html: str) -> List[str]:
    """
    Extract items from HTML lists (<ul>, <ol>, <li>) while preserving structure.

    Args:
        html: Raw HTML content

    Returns:
        List of text items from HTML lists
    """
    soup = BeautifulSoup(html, 'html.parser')
    items = []

    # Find all list items
    for li in soup.find_all('li'):
        text = li.get_text(strip=True)
        if text:
            items.append(text)

    return items


def is_ingredient_line(line: str) -> float:
    """
    Score a line as likely being an ingredient (0.0 to 1.0).

    Uses pattern matching and keyword detection to assign a confidence score.

    Args:
        line: Text line to evaluate

    Returns:
        Float score from 0.0 (definitely not ingredient) to 1.0 (definitely ingredient)
    """
    if not line or len(line) < 2:
        return 0.0

    score = 0.0
    line_lower = line.lower()

    # Check against ingredient patterns
    for pattern in INGREDIENT_PATTERNS:
        if re.match(pattern, line, re.IGNORECASE):
            score += 0.4
            break  # Only count one pattern match

    # Check for measurement keywords
    words = line_lower.split()
    for word in words:
        # Strip punctuation for matching
        clean_word = re.sub(r'[^\w]', '', word)
        if clean_word in INGREDIENT_KEYWORDS:
            score += 0.3
            break  # Only count one keyword match

    # Boost score if line starts with a number
    if re.match(r'^\d', line):
        score += 0.2

    # Boost score if line contains fraction characters
    if re.search(r'[\u00BC-\u00BE\u2150-\u215E]', line):
        score += 0.2

    # Penalize if line is very long (likely an instruction)
    if len(line) > 100:
        score -= 0.3

    # Penalize if line contains instruction verbs
    for verb in INSTRUCTION_VERBS:
        if line_lower.startswith(verb + ' ') or line_lower.startswith(verb + '.'):
            score -= 0.4
            break

    # Penalize if line has numbered step pattern
    if re.match(r'^\d+[\.\)]\s+', line):
        score -= 0.3

    # Cap score between 0 and 1
    return max(0.0, min(1.0, score))


def is_instruction_line(line: str) -> float:
    """
    Score a line as likely being an instruction (0.0 to 1.0).

    Uses pattern matching and verb detection to assign a confidence score.

    Args:
        line: Text line to evaluate

    Returns:
        Float score from 0.0 (definitely not instruction) to 1.0 (definitely instruction)
    """
    if not line or len(line) < 2:
        return 0.0

    score = 0.0
    line_lower = line.lower()

    # Check against instruction patterns
    for pattern in INSTRUCTION_PATTERNS:
        if re.match(pattern, line, re.IGNORECASE):
            score += 0.5
            break  # Only count one pattern match

    # Check for cooking verbs at start of line
    first_word = line_lower.split()[0] if line_lower.split() else ''
    first_word_clean = re.sub(r'[^\w]', '', first_word)

    if first_word_clean in INSTRUCTION_VERBS:
        score += 0.4

    # Check for cooking verbs anywhere in line (weaker signal)
    for verb in INSTRUCTION_VERBS:
        if verb in line_lower:
            score += 0.1
            break

    # Boost if line is longer (instructions tend to be sentences)
    if len(line) > 50:
        score += 0.2

    # Boost if line contains time indicators
    if re.search(r'\d+\s*(minute|min|hour|hr|second|sec)', line_lower):
        score += 0.2

    # Boost if line contains temperature indicators
    if re.search(r'\d+\s*(degree|°|fahrenheit|celsius|f|c)', line_lower):
        score += 0.2

    # Penalize if line looks like an ingredient (starts with number + unit)
    if re.match(r'^\d+[\s/\d]*\s*(cup|tbsp|tsp|oz|lb|g|kg)', line, re.IGNORECASE):
        score -= 0.5

    # Penalize if line contains measurement units
    words = line_lower.split()
    for word in words:
        clean_word = re.sub(r'[^\w]', '', word)
        if clean_word in ['cup', 'cups', 'tbsp', 'tsp', 'oz', 'lb']:
            score -= 0.2
            break

    # Cap score between 0 and 1
    return max(0.0, min(1.0, score))


def normalize_header(line: str) -> str:
    """
    Normalize a header line by removing markdown formatting and punctuation.

    Handles:
    - Markdown headers: # Header, ## Header, ### Header
    - Trailing colons: Ingredients:
    - Leading/trailing whitespace

    Args:
        line: Raw header line

    Returns:
        Normalized header text in lowercase
    """
    # Remove markdown header markers
    line = re.sub(r'^#+\s*', '', line)
    # Remove trailing colon and whitespace
    line = re.sub(r'[:\s]*$', '', line)
    # Remove leading whitespace
    line = line.strip()
    return line.lower()


def is_header_match(line: str, headers: List[str]) -> bool:
    """
    Check if a line matches any header in the list.

    Handles various formats:
    - Plain: "Ingredients"
    - With colon: "Ingredients:"
    - Markdown: "# Ingredients", "## Ingredients", "### Ingredients"
    - Mixed: "## Ingredients:"

    Args:
        line: Line to check
        headers: List of header strings to match against

    Returns:
        True if line matches any header
    """
    # Normalize the line
    normalized = normalize_header(line)

    # Check exact match
    if normalized in headers:
        return True

    # Check if any header is contained at the start
    for header in headers:
        if normalized == header:
            return True
        # Handle "for the ..." variations like "for the sauce"
        if header.startswith('for ') and normalized.startswith(header):
            return True

    return False


def find_section_headers(lines: List[str]) -> Dict[str, Tuple[int, int]]:
    """
    Find ingredient and instruction section boundaries by detecting headers.

    Args:
        lines: List of text lines from the recipe

    Returns:
        Dictionary with 'ingredients' and 'instructions' keys, each containing
        (start_index, end_index) tuples. Returns empty dict if no headers found.
    """
    sections = {}
    ingredient_start = None
    instruction_start = None

    for i, line in enumerate(lines):
        line_stripped = line.strip()

        # Skip very short lines
        if len(line_stripped) < 3:
            continue

        # Check for ingredient headers
        if ingredient_start is None:
            if is_header_match(line_stripped, INGREDIENT_HEADERS):
                ingredient_start = i + 1  # Start after header
                logger.debug(f"Found ingredient header at line {i}: {line}")

        # Check for instruction headers (can override ingredient end)
        if instruction_start is None:
            if is_header_match(line_stripped, INSTRUCTION_HEADERS):
                instruction_start = i + 1  # Start after header
                logger.debug(f"Found instruction header at line {i}: {line}")

    # Determine section boundaries
    if ingredient_start is not None and instruction_start is not None:
        # Both sections found
        if ingredient_start < instruction_start:
            sections['ingredients'] = (ingredient_start, instruction_start - 1)
            sections['instructions'] = (instruction_start, len(lines))
        else:
            sections['instructions'] = (instruction_start, ingredient_start - 1)
            sections['ingredients'] = (ingredient_start, len(lines))
    elif ingredient_start is not None:
        # Only ingredients found - assume rest is instructions or unknown
        sections['ingredients'] = (ingredient_start, len(lines))
    elif instruction_start is not None:
        # Only instructions found - assume earlier content is ingredients
        sections['instructions'] = (instruction_start, len(lines))
        if instruction_start > 0:
            sections['ingredients'] = (0, instruction_start - 1)

    return sections


def extract_lines_from_html(html: str) -> List[str]:
    """
    Convert HTML to clean text lines, preserving list structure.

    Args:
        html: Raw HTML content

    Returns:
        List of cleaned text lines
    """
    # Try html2text first - it handles markdown conversion better
    try:
        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True
        h.ignore_emphasis = False  # Keep emphasis for header detection
        h.body_width = 0  # Don't wrap lines
        h.unicode_snob = True

        text = h.handle(html)

        # Process lines - preserve markdown headers and numbered lists
        lines = []
        for line in text.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue

            # Preserve markdown headers as-is (for header detection)
            if stripped.startswith('#'):
                lines.append(stripped)
                continue

            # Clean up bullet markers from ingredient lists
            # Handle "  * item" and "  - item" (with leading spaces)
            if re.match(r'^\s*[\*\-]\s+', line):
                cleaned = re.sub(r'^\s*[\*\-]\s+', '', line).strip()
                if cleaned:
                    lines.append(cleaned)
            else:
                # Keep numbered items and regular text as-is
                lines.append(stripped)

        if lines:
            return lines
    except Exception as e:
        logger.warning(f"html2text extraction failed: {e}")

    # Fallback to BeautifulSoup
    try:
        soup = BeautifulSoup(html, 'html.parser')

        # Remove script and style elements
        for script in soup(['script', 'style', 'meta', 'link']):
            script.decompose()

        lines = []
        processed_elements = set()

        # Extract text from each block-level element, avoiding nested duplicates
        for element in soup.find_all(['p', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'span']):
            # Skip if this element is inside another we've already processed
            if element in processed_elements:
                continue

            # Skip if any parent has already been processed
            skip = False
            for parent in element.parents:
                if parent in processed_elements:
                    skip = True
                    break

            if not skip:
                text = element.get_text(strip=True)
                if text:
                    lines.append(text)
                    processed_elements.add(element)

        # If we got good results, return them
        if lines:
            return lines
    except Exception as e:
        logger.warning(f"BeautifulSoup extraction failed: {e}")

    # Last resort: simple text extraction
    try:
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(separator='\n')
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return lines
    except Exception:
        return []


def group_consecutive_lines(line_scores: List[Tuple[str, float, float]], threshold: float = 0.3) -> Tuple[List[str], List[str]]:
    """
    Group consecutive lines based on their ingredient vs instruction scores.

    Args:
        line_scores: List of (line, ingredient_score, instruction_score) tuples
        threshold: Minimum score difference to consider a line as one type

    Returns:
        Tuple of (ingredients, instructions) lists
    """
    ingredients = []
    instructions = []

    for line, ing_score, inst_score in line_scores:
        # Determine which type this line is
        if ing_score > inst_score and ing_score >= threshold:
            ingredients.append(line)
        elif inst_score > ing_score and inst_score >= threshold:
            instructions.append(line)
        # If scores are too close or too low, we skip ambiguous lines

    return ingredients, instructions


# ==============================================================================
# MAIN HEURISTIC PARSING FUNCTION
# ==============================================================================

def heuristic_parse(html: str) -> Tuple[List[str], List[str], float]:
    """
    Parse HTML content to extract ingredients and instructions using heuristics.

    This function implements a multi-stage approach:
    1. Convert HTML to text lines
    2. Look for explicit section headers (ingredients, instructions)
    3. If headers found, extract content from those sections
    4. If no headers, score each line and group by type
    5. Return results with confidence score

    Args:
        html: Raw HTML content from Evernote note

    Returns:
        Tuple of (ingredients, instructions, confidence_score)
        - ingredients: List of ingredient strings
        - instructions: List of instruction strings
        - confidence_score: 0.0 to 1.0 indicating extraction quality
    """
    logger.debug("Starting heuristic parsing")

    if not html or not html.strip():
        logger.warning("Empty HTML content")
        return [], [], 0.0

    # Extract lines from HTML
    lines = extract_lines_from_html(html)

    if not lines:
        logger.warning("No text lines extracted from HTML")
        return [], [], 0.0

    logger.debug(f"Extracted {len(lines)} lines from HTML")

    # Clean all lines
    lines = [clean_line(line) for line in lines if line.strip()]

    # Try to find section headers first
    sections = find_section_headers(lines)

    ingredients = []
    instructions = []
    confidence = 0.0

    if sections:
        logger.debug(f"Found sections: {list(sections.keys())}")

        # Extract ingredients from their section
        if 'ingredients' in sections:
            start, end = sections['ingredients']
            ingredients = [line for line in lines[start:end] if line.strip()]
            logger.debug(f"Extracted {len(ingredients)} ingredients from section")

        # Extract instructions from their section
        if 'instructions' in sections:
            start, end = sections['instructions']
            instructions = [line for line in lines[start:end] if line.strip()]
            logger.debug(f"Extracted {len(instructions)} instructions from section")

        # High confidence if we found both sections
        if 'ingredients' in sections and 'instructions' in sections:
            confidence = 0.9
        elif sections:
            confidence = 0.6

    else:
        logger.debug("No section headers found, using line scoring")

        # Score each line
        line_scores = []
        for line in lines:
            ing_score = is_ingredient_line(line)
            inst_score = is_instruction_line(line)
            line_scores.append((line, ing_score, inst_score))

        # Group lines by type
        ingredients, instructions = group_consecutive_lines(line_scores)

        logger.debug(f"Scored extraction: {len(ingredients)} ingredients, {len(instructions)} instructions")

        # Lower confidence for scored extraction
        if ingredients and instructions:
            confidence = 0.5
        elif ingredients or instructions:
            confidence = 0.3
        else:
            confidence = 0.1

    # Further adjust confidence based on results
    if ingredients and instructions:
        # Boost confidence if we have reasonable amounts of both
        if len(ingredients) >= 3 and len(instructions) >= 2:
            confidence = min(1.0, confidence + 0.1)
    else:
        # Lower confidence if missing one component
        confidence *= 0.5

    logger.info(f"Heuristic parse complete: {len(ingredients)} ingredients, "
                f"{len(instructions)} instructions, confidence={confidence:.2f}")

    return ingredients, instructions, confidence
