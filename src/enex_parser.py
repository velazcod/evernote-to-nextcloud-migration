"""Parse ENEX (Evernote Export) XML files and extract notes with resources.

This module handles:
- Streaming XML parsing for memory efficiency with large files
- CDATA extraction from content elements
- Base64 decoding of embedded images
- MD5 hash calculation for image matching
- HTML entity handling
- Datetime parsing from Evernote format
"""

import base64
import hashlib
import html
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from lxml import etree

logger = logging.getLogger(__name__)


@dataclass
class Resource:
    """Embedded resource (image or attachment) from an Evernote note.

    Attributes:
        data: Raw bytes of the resource (decoded from base64)
        mime_type: MIME type (e.g., "image/jpeg", "image/png")
        filename: Original filename if available
        md5_hash: MD5 hash of the data bytes (used for matching en-media references)
    """
    data: bytes
    mime_type: str
    filename: str | None
    md5_hash: str


@dataclass
class Note:
    """Parsed Evernote note with content and resources.

    Attributes:
        title: Note title
        content_html: HTML content extracted from CDATA
        created: Creation timestamp (timezone-aware)
        updated: Last update timestamp (timezone-aware) or None
        tags: List of tag names
        source_url: Original URL if web-clipped
        resources: Dict mapping MD5 hash to Resource objects
    """
    title: str
    content_html: str
    created: datetime
    updated: datetime | None = None
    tags: list[str] = field(default_factory=list)
    source_url: str | None = None
    resources: dict[str, Resource] = field(default_factory=dict)


def parse_evernote_datetime(dt_string: str) -> datetime:
    """Parse Evernote datetime format to timezone-aware datetime.

    Evernote uses format: YYYYMMDDTHHMMSSZ (e.g., "20240101T120000Z")

    Args:
        dt_string: Datetime string in Evernote format

    Returns:
        Timezone-aware datetime object (UTC)

    Raises:
        ValueError: If datetime string is malformed
    """
    # Remove any whitespace
    dt_string = dt_string.strip()

    # Handle various formats Evernote might use
    # Standard: 20240101T120000Z
    # Sometimes: 2024-01-01T12:00:00Z
    if '-' in dt_string:
        # ISO format with dashes
        dt_string = dt_string.replace('-', '').replace(':', '')

    # Remove trailing Z and parse
    if dt_string.endswith('Z'):
        dt_string = dt_string[:-1]

    try:
        dt = datetime.strptime(dt_string, "%Y%m%dT%H%M%S")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError as e:
        logger.warning(f"Failed to parse datetime '{dt_string}': {e}")
        raise


def decode_content(cdata_content: str) -> str:
    """Extract and clean HTML content from CDATA section.

    The content in ENEX files is XHTML wrapped in CDATA with its own
    XML declaration and DOCTYPE. This function extracts the inner HTML
    and handles entity encoding.

    Args:
        cdata_content: Raw CDATA content string

    Returns:
        Cleaned HTML content
    """
    if not cdata_content:
        return ""

    # Unescape HTML entities
    content = html.unescape(cdata_content)

    # Remove XML declaration if present
    content = re.sub(r'<\?xml[^?]*\?>', '', content)

    # Remove DOCTYPE if present
    content = re.sub(r'<!DOCTYPE[^>]*>', '', content)

    # Extract content from en-note element if present
    en_note_match = re.search(r'<en-note[^>]*>(.*?)</en-note>', content, re.DOTALL | re.IGNORECASE)
    if en_note_match:
        content = en_note_match.group(1)

    # Clean up whitespace
    content = content.strip()

    return content


def extract_resources(note_element: etree._Element) -> dict[str, Resource]:
    """Extract all resources (images/attachments) from a note element.

    Resources are stored as base64-encoded data with MIME types.
    The MD5 hash is calculated from the decoded bytes to match
    with <en-media> references in the content.

    Args:
        note_element: lxml Element representing a <note>

    Returns:
        Dict mapping MD5 hash to Resource object
    """
    resources = {}

    for resource_elem in note_element.findall('resource'):
        try:
            # Get base64 data
            data_elem = resource_elem.find('data')
            if data_elem is None or data_elem.text is None:
                logger.warning("Resource missing data element")
                continue

            # Decode base64
            # Clean whitespace from base64 string
            base64_data = ''.join(data_elem.text.split())
            try:
                raw_data = base64.b64decode(base64_data)
            except Exception as e:
                logger.warning(f"Failed to decode base64 data: {e}")
                continue

            # Calculate MD5 hash
            md5_hash = hashlib.md5(raw_data).hexdigest()

            # Get MIME type
            mime_elem = resource_elem.find('mime')
            mime_type = mime_elem.text if mime_elem is not None and mime_elem.text else 'application/octet-stream'

            # Get filename from resource-attributes
            filename = None
            attrs_elem = resource_elem.find('resource-attributes')
            if attrs_elem is not None:
                filename_elem = attrs_elem.find('file-name')
                if filename_elem is not None and filename_elem.text:
                    filename = filename_elem.text

            resource = Resource(
                data=raw_data,
                mime_type=mime_type,
                filename=filename,
                md5_hash=md5_hash
            )

            resources[md5_hash] = resource
            logger.debug(f"Extracted resource: {mime_type}, {len(raw_data)} bytes, hash={md5_hash[:8]}...")

        except Exception as e:
            logger.error(f"Failed to extract resource: {e}")
            continue

    return resources


def parse_note(note_element: etree._Element) -> Note:
    """Parse a single note element into a Note dataclass.

    Args:
        note_element: lxml Element representing a <note>

    Returns:
        Parsed Note object

    Raises:
        ValueError: If required fields are missing
    """
    # Title (required)
    title_elem = note_element.find('title')
    if title_elem is None or not title_elem.text:
        # Generate fallback title
        title = "Untitled Note"
        logger.warning("Note missing title, using fallback")
    else:
        title = title_elem.text.strip()

    # Content (required for recipes, but handle missing)
    content_elem = note_element.find('content')
    if content_elem is not None and content_elem.text:
        content_html = decode_content(content_elem.text)
    else:
        content_html = ""
        logger.warning(f"Note '{title}' has no content")

    # Created timestamp (required)
    created_elem = note_element.find('created')
    if created_elem is not None and created_elem.text:
        try:
            created = parse_evernote_datetime(created_elem.text)
        except ValueError:
            created = datetime.now(timezone.utc)
            logger.warning(f"Note '{title}' has invalid created date, using current time")
    else:
        created = datetime.now(timezone.utc)
        logger.warning(f"Note '{title}' missing created date, using current time")

    # Updated timestamp (optional)
    updated = None
    updated_elem = note_element.find('updated')
    if updated_elem is not None and updated_elem.text:
        try:
            updated = parse_evernote_datetime(updated_elem.text)
        except ValueError:
            pass  # Updated is optional, ignore parse errors

    # Tags (optional, multiple)
    tags = []
    for tag_elem in note_element.findall('tag'):
        if tag_elem.text:
            tags.append(tag_elem.text.strip())

    # Source URL (optional)
    source_url = None
    note_attrs = note_element.find('note-attributes')
    if note_attrs is not None:
        source_url_elem = note_attrs.find('source-url')
        if source_url_elem is not None and source_url_elem.text:
            source_url = source_url_elem.text.strip()

    # Resources (images/attachments)
    resources = extract_resources(note_element)

    return Note(
        title=title,
        content_html=content_html,
        created=created,
        updated=updated,
        tags=tags,
        source_url=source_url,
        resources=resources
    )


def parse_enex(enex_path: Path | str) -> Iterator[Note]:
    """Parse an ENEX file and yield Note objects.

    Uses iterparse for memory efficiency with large files.
    Continues processing even if individual notes fail to parse.

    Args:
        enex_path: Path to the ENEX file

    Yields:
        Note objects for each successfully parsed note

    Raises:
        FileNotFoundError: If ENEX file doesn't exist
        etree.XMLSyntaxError: If XML is severely malformed
    """
    enex_path = Path(enex_path)

    if not enex_path.exists():
        raise FileNotFoundError(f"ENEX file not found: {enex_path}")

    logger.info(f"Parsing ENEX file: {enex_path}")

    # Use iterparse for memory efficiency
    # We need to build the full note element to extract resources
    context = etree.iterparse(
        str(enex_path),
        events=('end',),
        tag='note',
        recover=True  # Try to recover from malformed XML
    )

    note_count = 0
    error_count = 0

    for event, note_element in context:
        try:
            note = parse_note(note_element)
            note_count += 1
            logger.debug(f"Parsed note {note_count}: {note.title}")
            yield note

        except Exception as e:
            error_count += 1
            # Try to get title for error message
            title_elem = note_element.find('title')
            title = title_elem.text if title_elem is not None and title_elem.text else "Unknown"
            logger.error(f"Failed to parse note '{title}': {e}")

        finally:
            # Clear element to free memory
            note_element.clear()
            # Also clear parent references
            while note_element.getprevious() is not None:
                del note_element.getparent()[0]

    logger.info(f"Finished parsing {enex_path.name}: {note_count} notes, {error_count} errors")


def count_notes(enex_path: Path | str) -> int:
    """Count the number of notes in an ENEX file without full parsing.

    Args:
        enex_path: Path to the ENEX file

    Returns:
        Number of <note> elements in the file
    """
    enex_path = Path(enex_path)
    count = 0

    context = etree.iterparse(str(enex_path), events=('end',), tag='note', recover=True)
    for event, elem in context:
        count += 1
        elem.clear()

    return count


def get_first_image_resource(note: Note) -> Resource | None:
    """Get the first image resource from a note.

    Looks for resources with image MIME types.

    Args:
        note: Parsed Note object

    Returns:
        First image Resource or None if no images
    """
    image_mime_types = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp'}

    for resource in note.resources.values():
        if resource.mime_type.lower() in image_mime_types:
            return resource

    return None
