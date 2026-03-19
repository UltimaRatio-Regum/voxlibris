"""
EPUB Parser - Extracts chapters, text, and metadata from EPUB files.
"""
import re
from typing import List, Tuple, Dict, Any, Optional
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub

import logging
logger = logging.getLogger(__name__)


def extract_text_from_html(html_content: bytes) -> str:
    """Extract clean text from HTML content."""
    soup = BeautifulSoup(html_content, 'lxml')
    
    for script in soup(["script", "style", "meta", "link"]):
        script.decompose()
    
    text = soup.get_text(separator='\n')
    
    lines = [line.strip() for line in text.splitlines()]
    text = '\n'.join(line for line in lines if line)
    
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def extract_title_from_html(html_content: bytes) -> str:
    """Extract title/heading from HTML content."""
    soup = BeautifulSoup(html_content, 'lxml')
    
    for tag in ['h1', 'h2', 'h3', 'title']:
        heading = soup.find(tag)
        if heading:
            title = heading.get_text().strip()
            if title and len(title) < 200:
                return title
    
    return ""


def _extract_epub_metadata(book) -> Dict[str, Any]:
    """Extract metadata (title, author, year, description, cover image) from an EPUB book object."""
    metadata: Dict[str, Any] = {
        "title": None,
        "author": None,
        "year": None,
        "description": None,
        "cover_image": None,
    }

    def _first_dc(field: str) -> Optional[str]:
        vals = book.get_metadata('DC', field)
        if vals:
            val = vals[0]
            if isinstance(val, tuple):
                return str(val[0]).strip() if val[0] else None
            return str(val).strip() if val else None
        return None

    metadata["title"] = _first_dc("title")
    metadata["author"] = _first_dc("creator")
    metadata["description"] = _first_dc("description")

    date_val = _first_dc("date")
    if date_val:
        year_match = re.search(r'\b(\d{4})\b', date_val)
        if year_match:
            metadata["year"] = year_match.group(1)

    try:
        cover_id = None
        cover_meta = book.get_metadata('OPF', 'cover')
        if cover_meta:
            for item in cover_meta:
                if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], dict):
                    cover_id = item[1].get('content')
                    break

        if cover_id:
            for item in book.get_items():
                if item.get_id() == cover_id:
                    metadata["cover_image"] = item.get_content()
                    break

        if not metadata["cover_image"]:
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_COVER:
                    metadata["cover_image"] = item.get_content()
                    break

        if not metadata["cover_image"]:
            for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
                name_lower = item.get_name().lower()
                if 'cover' in name_lower:
                    metadata["cover_image"] = item.get_content()
                    break
    except Exception as e:
        logger.warning(f"Failed to extract cover image: {e}")

    return metadata


def _extract_chapters(book) -> List[Tuple[str, str]]:
    """Extract chapter (title, text) tuples from an EPUB book object."""
    chapters = []
    chapter_index = 0

    for item in book.get_items_of_type(9):  # ITEM_DOCUMENT
        content = item.get_content()

        text = extract_text_from_html(content)

        if len(text.strip()) < 100:
            continue

        title = extract_title_from_html(content)
        if not title:
            chapter_index += 1
            title = f"Chapter {chapter_index}"
        else:
            chapter_index += 1

        chapters.append((title, text))

    return chapters


def parse_epub(file_content: bytes) -> List[Tuple[str, str]]:
    """
    Parse an EPUB file and extract chapters.
    
    Args:
        file_content: Raw bytes of the EPUB file
        
    Returns:
        List of (title, text) tuples for each chapter
    """
    import io
    
    book = epub.read_epub(io.BytesIO(file_content))
    chapters = _extract_chapters(book)
    
    logger.info(f"Extracted {len(chapters)} chapters from EPUB")
    return chapters


def parse_epub_with_metadata(file_content: bytes) -> Dict[str, Any]:
    """
    Parse an EPUB file and extract chapters along with book metadata.
    
    Args:
        file_content: Raw bytes of the EPUB file
        
    Returns:
        Dict with "chapters" (list of (title, text) tuples) and "metadata" dict
    """
    import io

    book = epub.read_epub(io.BytesIO(file_content))
    chapters = _extract_chapters(book)
    metadata = _extract_epub_metadata(book)

    logger.info(f"Extracted {len(chapters)} chapters and metadata from EPUB (title={metadata.get('title')}, author={metadata.get('author')})")
    return {"chapters": chapters, "metadata": metadata}


def parse_txt(file_content: bytes) -> List[Tuple[str, str]]:
    """
    Parse a TXT file.
    
    Args:
        file_content: Raw bytes of the TXT file
        
    Returns:
        List with single (title, text) tuple
    """
    for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
        try:
            text = file_content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = file_content.decode('utf-8', errors='replace')
    
    text = text.strip()
    
    first_line = text.split('\n')[0].strip()
    if len(first_line) < 100 and first_line:
        title = first_line
    else:
        title = "Uploaded Text"
    
    return [(title, text)]
