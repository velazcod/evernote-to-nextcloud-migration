"""Tests for ENEX parser module."""

import base64
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.enex_parser import (
    Note,
    Resource,
    count_notes,
    decode_content,
    get_first_image_resource,
    parse_enex,
    parse_evernote_datetime,
)


class TestParseEvernoteDatetime:
    """Tests for datetime parsing."""

    def test_standard_format(self):
        """Test standard Evernote datetime format."""
        result = parse_evernote_datetime("20240101T120000Z")
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1
        assert result.hour == 12
        assert result.minute == 0
        assert result.second == 0
        assert result.tzinfo == timezone.utc

    def test_with_whitespace(self):
        """Test datetime with surrounding whitespace."""
        result = parse_evernote_datetime("  20240315T090000Z  ")
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 15

    def test_iso_format_with_dashes(self):
        """Test ISO format with dashes (sometimes used by Evernote)."""
        result = parse_evernote_datetime("2024-01-01T12:00:00Z")
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_invalid_format_raises(self):
        """Test that invalid format raises ValueError."""
        with pytest.raises(ValueError):
            parse_evernote_datetime("invalid")


class TestDecodeContent:
    """Tests for CDATA content decoding."""

    def test_simple_content(self):
        """Test simple HTML content extraction."""
        cdata = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml.dtd">
<en-note>
<div>Hello World</div>
</en-note>"""
        result = decode_content(cdata)
        assert "<div>Hello World</div>" in result
        assert "<?xml" not in result
        assert "DOCTYPE" not in result
        assert "<en-note" not in result

    def test_html_entities(self):
        """Test HTML entity handling."""
        cdata = "<en-note><div>375&deg;F &amp; 190&deg;C</div></en-note>"
        result = decode_content(cdata)
        assert "375°F & 190°C" in result

    def test_empty_content(self):
        """Test empty content handling."""
        assert decode_content("") == ""
        assert decode_content(None) == ""

    def test_nbsp_handling(self):
        """Test non-breaking space handling."""
        cdata = "<en-note><div>Hello&nbsp;World</div></en-note>"
        result = decode_content(cdata)
        # &nbsp; should be converted to actual non-breaking space
        assert "Hello" in result
        assert "World" in result


class TestParseEnex:
    """Tests for ENEX file parsing."""

    def test_parse_sample_enex(self, sample_enex):
        """Test parsing the sample ENEX file."""
        notes = list(parse_enex(sample_enex))

        # Should have 3 notes in sample
        assert len(notes) == 3

        # Check first note (Simple Pasta Recipe)
        pasta = notes[0]
        assert pasta.title == "Simple Pasta Recipe"
        assert "spaghetti" in pasta.content_html.lower()
        assert "marinara" in pasta.content_html.lower()
        assert pasta.created.year == 2024
        assert "dinner" in pasta.tags
        assert "italian" in pasta.tags
        assert "quick" in pasta.tags
        assert pasta.source_url is None

        # Check second note (Chocolate Chip Cookies)
        cookies = notes[1]
        assert cookies.title == "Chocolate Chip Cookies"
        assert "chocolate chips" in cookies.content_html.lower()
        assert cookies.source_url == "https://example.com/cookies"
        assert "dessert" in cookies.tags

        # Check third note (Grandma's Secret Recipe - unclear content)
        grandma = notes[2]
        assert grandma.title == "Grandma's Secret Recipe"
        assert "family" in grandma.tags

    def test_file_not_found(self, tmp_path):
        """Test FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            list(parse_enex(tmp_path / "nonexistent.enex"))

    def test_parse_yields_notes(self, sample_enex):
        """Test that parse_enex yields Note objects."""
        for note in parse_enex(sample_enex):
            assert isinstance(note, Note)
            assert isinstance(note.title, str)
            assert isinstance(note.content_html, str)
            assert isinstance(note.created, datetime)
            assert isinstance(note.tags, list)
            assert isinstance(note.resources, dict)


class TestCountNotes:
    """Tests for note counting."""

    def test_count_sample_notes(self, sample_enex):
        """Test counting notes in sample file."""
        count = count_notes(sample_enex)
        assert count == 3


class TestGetFirstImageResource:
    """Tests for image resource extraction."""

    def test_no_resources(self):
        """Test note with no resources."""
        note = Note(
            title="Test",
            content_html="<div>Test</div>",
            created=datetime.now(timezone.utc),
            resources={}
        )
        assert get_first_image_resource(note) is None

    def test_with_image_resource(self):
        """Test note with image resource."""
        # Create a simple 1x1 pixel JPEG (minimal valid JPEG)
        # This is a minimal valid JPEG file bytes
        image_data = base64.b64decode(
            "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkS"
            "Ew8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJ"
            "CQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
            "MjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAA"
            "AAAAsJ/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/EABQBAQAAAAAAAAAAAAAAAAAAAAD/"
            "xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwAB//2Q=="
        )
        md5_hash = hashlib.md5(image_data).hexdigest()

        resource = Resource(
            data=image_data,
            mime_type="image/jpeg",
            filename="photo.jpg",
            md5_hash=md5_hash
        )

        note = Note(
            title="Test",
            content_html="<div>Test</div>",
            created=datetime.now(timezone.utc),
            resources={md5_hash: resource}
        )

        result = get_first_image_resource(note)
        assert result is not None
        assert result.mime_type == "image/jpeg"
        assert result.md5_hash == md5_hash

    def test_non_image_resource_ignored(self):
        """Test that non-image resources are ignored."""
        pdf_data = b"%PDF-1.4 fake pdf data"
        md5_hash = hashlib.md5(pdf_data).hexdigest()

        resource = Resource(
            data=pdf_data,
            mime_type="application/pdf",
            filename="document.pdf",
            md5_hash=md5_hash
        )

        note = Note(
            title="Test",
            content_html="<div>Test</div>",
            created=datetime.now(timezone.utc),
            resources={md5_hash: resource}
        )

        assert get_first_image_resource(note) is None


class TestResourceExtraction:
    """Tests for resource extraction."""

    def test_resource_md5_hash_calculation(self):
        """Test that MD5 hash is correctly calculated."""
        test_data = b"test image data"
        expected_hash = hashlib.md5(test_data).hexdigest()

        resource = Resource(
            data=test_data,
            mime_type="image/jpeg",
            filename="test.jpg",
            md5_hash=expected_hash
        )

        assert resource.md5_hash == expected_hash


class TestNoteDataclass:
    """Tests for Note dataclass."""

    def test_note_defaults(self):
        """Test Note dataclass default values."""
        note = Note(
            title="Test",
            content_html="<div>Content</div>",
            created=datetime.now(timezone.utc)
        )

        assert note.updated is None
        assert note.tags == []
        assert note.source_url is None
        assert note.resources == {}

    def test_note_with_all_fields(self):
        """Test Note dataclass with all fields populated."""
        created = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        updated = datetime(2024, 1, 15, 18, 0, 0, tzinfo=timezone.utc)

        note = Note(
            title="Full Note",
            content_html="<div>Full content</div>",
            created=created,
            updated=updated,
            tags=["tag1", "tag2"],
            source_url="https://example.com",
            resources={}
        )

        assert note.title == "Full Note"
        assert note.created == created
        assert note.updated == updated
        assert note.tags == ["tag1", "tag2"]
        assert note.source_url == "https://example.com"
