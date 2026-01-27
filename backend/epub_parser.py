"""
EPUB Parser - Extracts chapters and text from EPUB files.
"""
import re
from typing import List, Tuple
from bs4 import BeautifulSoup
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
    
    logger.info(f"Extracted {len(chapters)} chapters from EPUB")
    return chapters


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
