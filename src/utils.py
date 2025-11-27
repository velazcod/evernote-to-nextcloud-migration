"""
Shared utilities for the Evernote to Nextcloud Cookbook migration tool.

Provides logging configuration, text processing, and helper functions
used across multiple modules.
"""

import logging
import re
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any


def setup_logging(
    log_file: str | Path | None = None,
    verbose: bool = False,
    log_to_console: bool = True
) -> logging.Logger:
    """
    Configure logging to console and optionally to file.

    Args:
        log_file: Path to log file, or None for console-only
        verbose: If True, set DEBUG level; otherwise INFO
        log_to_console: If True, also log to stdout

    Returns:
        Root logger configured for the application
    """
    # Determine log level
    level = logging.DEBUG if verbose else logging.INFO

    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # File handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return root_logger


def normalize_whitespace(text: str) -> str:
    """
    Collapse multiple whitespace characters to single space.

    Args:
        text: Input string with potential multiple whitespace

    Returns:
        String with normalized whitespace

    Examples:
        >>> normalize_whitespace("hello   world")
        'hello world'
        >>> normalize_whitespace("  leading and trailing  ")
        'leading and trailing'
    """
    if not text:
        return ""
    # Replace multiple whitespace (including newlines, tabs) with single space
    result = re.sub(r'\s+', ' ', text)
    return result.strip()


def html_to_text(html: str) -> str:
    """
    Convert HTML to plain text, preserving basic structure.

    Uses html2text for conversion with sensible defaults.

    Args:
        html: HTML content to convert

    Returns:
        Plain text version of the HTML

    Note:
        This is a simple wrapper. For more complex needs,
        use html2text directly with custom configuration.
    """
    if not html:
        return ""

    try:
        import html2text
        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = True
        converter.ignore_emphasis = False
        converter.body_width = 0  # No line wrapping
        return converter.handle(html).strip()
    except ImportError:
        # Fallback: simple tag stripping
        import html as html_module
        text = re.sub(r'<[^>]+>', ' ', html)
        text = html_module.unescape(text)
        return normalize_whitespace(text)


def parse_iso_duration(duration_str: str) -> timedelta | None:
    """
    Parse ISO 8601 duration (PT1H30M) to timedelta.

    Args:
        duration_str: ISO 8601 duration string (e.g., "PT1H30M", "PT45M")

    Returns:
        timedelta object, or None if parsing fails

    Examples:
        >>> parse_iso_duration("PT1H30M")
        datetime.timedelta(seconds=5400)
        >>> parse_iso_duration("PT45M")
        datetime.timedelta(seconds=2700)
        >>> parse_iso_duration("PT2H")
        datetime.timedelta(seconds=7200)
    """
    if not duration_str or not duration_str.startswith("PT"):
        return None

    try:
        # Remove PT prefix
        duration = duration_str[2:]

        hours = 0
        minutes = 0
        seconds = 0

        # Extract hours
        h_match = re.search(r'(\d+)H', duration)
        if h_match:
            hours = int(h_match.group(1))

        # Extract minutes
        m_match = re.search(r'(\d+)M', duration)
        if m_match:
            minutes = int(m_match.group(1))

        # Extract seconds
        s_match = re.search(r'(\d+)S', duration)
        if s_match:
            seconds = int(s_match.group(1))

        return timedelta(hours=hours, minutes=minutes, seconds=seconds)
    except Exception:
        return None


def format_iso_duration(minutes: int) -> str:
    """
    Format minutes as ISO 8601 duration.

    Args:
        minutes: Number of minutes

    Returns:
        ISO 8601 duration string (e.g., "PT45M", "PT1H30M")

    Examples:
        >>> format_iso_duration(45)
        'PT45M'
        >>> format_iso_duration(90)
        'PT1H30M'
        >>> format_iso_duration(120)
        'PT2H'
    """
    if minutes <= 0:
        return "PT0M"

    hours = minutes // 60
    remaining_minutes = minutes % 60

    parts = ["PT"]
    if hours > 0:
        parts.append(f"{hours}H")
    if remaining_minutes > 0 or hours == 0:
        parts.append(f"{remaining_minutes}M")

    return "".join(parts)


def safe_get(dict_obj: dict, *keys, default: Any = None) -> Any:
    """
    Safely navigate nested dictionaries.

    Args:
        dict_obj: Dictionary to navigate
        *keys: Sequence of keys to follow
        default: Value to return if any key is missing

    Returns:
        Value at the nested key path, or default if not found

    Examples:
        >>> d = {"a": {"b": {"c": 1}}}
        >>> safe_get(d, "a", "b", "c")
        1
        >>> safe_get(d, "a", "x", default="not found")
        'not found'
    """
    current = dict_obj
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate string to max length, adding suffix if truncated.

    Tries to break at word boundaries.

    Args:
        text: String to truncate
        max_length: Maximum length including suffix
        suffix: String to append if truncated

    Returns:
        Truncated string
    """
    if not text or len(text) <= max_length:
        return text or ""

    # Calculate available length for content
    available = max_length - len(suffix)
    if available <= 0:
        return suffix[:max_length]

    # Try to break at word boundary
    truncated = text[:available]
    last_space = truncated.rfind(' ')
    if last_space > available // 2:  # Only use word break if reasonable
        truncated = truncated[:last_space]

    return truncated.rstrip() + suffix


def count_words(text: str) -> int:
    """
    Count words in text.

    Args:
        text: Text to count words in

    Returns:
        Number of words
    """
    if not text:
        return 0
    return len(text.split())


def extract_numbers(text: str) -> list[float]:
    """
    Extract all numbers from text.

    Args:
        text: Text containing numbers

    Returns:
        List of numbers found (as floats)

    Examples:
        >>> extract_numbers("Add 2 cups and 1/2 teaspoon")
        [2.0, 0.5]
    """
    if not text:
        return []

    numbers = []

    # Match integers, decimals, and fractions
    patterns = [
        r'(\d+\.?\d*)',  # Integers and decimals
        r'(\d+)/(\d+)',  # Fractions like 1/2
    ]

    # Find integers and decimals
    for match in re.finditer(r'\d+\.?\d*', text):
        try:
            numbers.append(float(match.group()))
        except ValueError:
            pass

    # Find and convert fractions
    for match in re.finditer(r'(\d+)/(\d+)', text):
        try:
            numerator = float(match.group(1))
            denominator = float(match.group(2))
            if denominator != 0:
                numbers.append(numerator / denominator)
        except (ValueError, ZeroDivisionError):
            pass

    return numbers


def is_likely_recipe(text: str) -> bool:
    """
    Quick heuristic check if text is likely a recipe.

    Args:
        text: Text to check

    Returns:
        True if text appears to contain recipe content
    """
    if not text or len(text) < 50:
        return False

    text_lower = text.lower()

    # Look for common recipe indicators
    recipe_keywords = [
        'ingredient', 'cup', 'tablespoon', 'teaspoon', 'tsp', 'tbsp',
        'preheat', 'bake', 'cook', 'mix', 'stir', 'serve', 'oven',
        'minutes', 'hours', 'degrees', 'temperature'
    ]

    keyword_count = sum(1 for kw in recipe_keywords if kw in text_lower)

    # Consider it a recipe if at least 3 keywords found
    return keyword_count >= 3


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size string (e.g., "1.5 MB")
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
