"""
Text Parser - Separates dialogue from narration and identifies speakers
with ~10 second chunking
"""

import re
import uuid
from typing import Optional
from textblob import TextBlob

from models import TextSegment, Sentiment


class TextParser:
    """
    Parses text to separate quoted/spoken sections from narration,
    identifies speakers, and performs sentiment analysis.
    Chunks text into ~10 second intervals for TTS processing.
    """
    
    DIALOGUE_VERBS = [
        "said", "says", "asked", "replied", "answered", "exclaimed",
        "whispered", "shouted", "yelled", "muttered", "murmured",
        "called", "cried", "screamed", "sighed", "laughed", "growled",
        "snapped", "hissed", "roared", "declared", "announced",
        "inquired", "responded", "stated", "added", "continued",
        "began", "finished", "interrupted", "demanded", "pleaded",
        "begged", "insisted", "suggested", "warned", "threatened",
        "promised", "admitted", "confessed", "explained", "wondered"
    ]
    
    WORDS_PER_SECOND = 2.5
    TARGET_CHUNK_SECONDS = 10.0
    
    def parse(self, text: str, known_speakers: list[str] | None = None) -> tuple[list[TextSegment], list[str]]:
        """
        Parse text into segments and detect speakers.
        
        Args:
            text: The text to parse
            known_speakers: Optional list of speaker names from previous sections
        
        Returns:
            tuple of (segments, detected_speakers)
        """
        raw_segments: list[TextSegment] = []
        speakers_set: set[str] = set()
        speaker_history: list[str] = list(known_speakers or [])
        
        current_pos = 0
        # Match straight quotes, curly double quotes (prioritize double quotes for dialogue)
        quote_pattern = re.compile(r'["""\u201c\u201d]([^"""\u201c\u201d]+)["""\u201c\u201d]')
        
        for match in quote_pattern.finditer(text):
            quote_start = match.start()
            quote_end = match.end()
            # Get the captured group (quote content without the quote marks)
            quote_text = match.group(1) if match.group(1) else ""
            
            if quote_start > current_pos:
                narration_text = text[current_pos:quote_start].strip()
                if narration_text:
                    raw_segments.append(self._create_segment(
                        text=narration_text,
                        segment_type="narration",
                        start_index=current_pos,
                        end_index=quote_start,
                    ))
            
            speaker = self._find_speaker_improved(text, quote_start, quote_end, speaker_history)
            if speaker:
                speakers_set.add(speaker)
                speaker_history.append(speaker)
            
            raw_segments.append(self._create_segment(
                text=quote_text,
                segment_type="dialogue",
                speaker=speaker,
                start_index=quote_start,
                end_index=quote_end,
            ))
            
            current_pos = quote_end
        
        if current_pos < len(text):
            remaining_text = text[current_pos:].strip()
            if remaining_text:
                raw_segments.append(self._create_segment(
                    text=remaining_text,
                    segment_type="narration",
                    start_index=current_pos,
                    end_index=len(text),
                ))
        
        if not raw_segments and text.strip():
            raw_segments.append(self._create_segment(
                text=text.strip(),
                segment_type="narration",
                start_index=0,
                end_index=len(text),
            ))
        
        paragraph_segments = self._split_by_paragraphs(raw_segments)
        chunked_segments = self._chunk_all_segments(paragraph_segments)
        
        return chunked_segments, sorted(list(speakers_set))
    
    def _create_segment(
        self,
        text: str,
        segment_type: str,
        start_index: int,
        end_index: int,
        speaker: Optional[str] = None,
    ) -> TextSegment:
        """Create a text segment with sentiment analysis and duration estimate."""
        sentiment = self._analyze_sentiment(text)
        wc = len(text.split())
        
        return TextSegment(
            id=str(uuid.uuid4()),
            type=segment_type,
            text=text,
            speaker=speaker,
            sentiment=sentiment,
            startIndex=start_index,
            endIndex=end_index,
            wordCount=wc,
            approxDurationSeconds=round(wc / self.WORDS_PER_SECOND, 1),
        )
    
    def _find_speaker_improved(
        self, 
        text: str, 
        quote_start: int, 
        quote_end: int,
        speaker_history: list[str]
    ) -> Optional[str]:
        """
        Find speaker with improved accuracy by checking both before and after quote.
        Prioritizes post-quote attribution ("Hello," said John).
        """
        context_before = text[max(0, quote_start - 150):quote_start]
        context_after = text[quote_end:min(len(text), quote_end + 150)]
        
        for context, is_after in [(context_after, True), (context_before, False)]:
            for verb in self.DIALOGUE_VERBS:
                if is_after:
                    pattern = rf'^\s*{verb}[sd]?\s+([A-Z][a-z]+)'
                else:
                    pattern = rf'([A-Z][a-z]+)\s+{verb}[sd]?\s*[,.]?\s*$'
                
                match = re.search(pattern, context, re.IGNORECASE)
                if match:
                    return match.group(1)
        
        for verb in self.DIALOGUE_VERBS:
            after_pattern = rf'^\s*,?\s*{verb}\s+([A-Z][a-z]+)'
            match = re.search(after_pattern, context_after, re.IGNORECASE)
            if match:
                return match.group(1)
        
        for verb in self.DIALOGUE_VERBS:
            before_pattern = rf'([A-Z][a-z]+)\s+{verb}'
            match = re.search(before_pattern, context_before, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    EMOTION_KEYWORDS = {
        "fear": ["afraid", "scared", "terrified", "fear", "horror", "dread", "nervous", "frightened", "panic"],
        "angry": ["angry", "furious", "rage", "hate", "damn", "hell", "livid", "enraged", "seething"],
        "sad": ["sad", "cry", "tears", "grief", "mourn", "sorrow", "depressed", "heartbroken", "weep"],
        "excited": ["excited", "amazing", "wonderful", "fantastic", "incredible", "brilliant", "thrilled"],
        "anxious": ["anxious", "worried", "uneasy", "restless", "tense", "apprehensive", "dread"],
        "hopeful": ["hope", "hopeful", "optimistic", "promising", "looking forward", "wish"],
        "melancholy": ["melancholy", "wistful", "nostalgic", "bittersweet", "longing", "yearning"],
        "tender": ["tender", "gentle", "soft", "loving", "affectionate", "warm", "caress"],
        "proud": ["proud", "pride", "triumph", "accomplished", "victorious", "glory"],
        "disgust": ["disgust", "revolting", "nauseating", "repulsive", "vile", "gross", "sick"],
        "surprise": ["surprise", "surprised", "astonished", "shocked", "stunned", "unexpected", "gasp"],
        "calm": ["calm", "peaceful", "serene", "tranquil", "quiet", "still", "relaxed", "composed"],
    }

    def _analyze_sentiment(self, text: str) -> Sentiment:
        """
        Analyze sentiment of text using TextBlob + keyword matching.
        Returns one of the 14 canonical emotions.
        """
        try:
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity
            subjectivity = blob.sentiment.subjectivity
            text_lower = text.lower()

            keyword_hits: dict[str, int] = {}
            for emotion, keywords in self.EMOTION_KEYWORDS.items():
                hits = sum(1 for kw in keywords if kw in text_lower)
                if hits > 0:
                    keyword_hits[emotion] = hits

            if keyword_hits:
                label = max(keyword_hits, key=keyword_hits.get)
                score = min(1.0, 0.6 + keyword_hits[label] * 0.1 + subjectivity * 0.2)
            elif polarity > 0.5 and subjectivity > 0.5:
                label = "happy"
                score = 0.5 + polarity * 0.5
            elif polarity > 0.2:
                label = "hopeful"
                score = 0.4 + polarity * 0.4
            elif polarity < -0.4:
                label = "sad"
                score = 0.5 + abs(polarity) * 0.5
            elif polarity < -0.2:
                label = "melancholy"
                score = 0.4 + abs(polarity) * 0.4
            else:
                label = "neutral"
                score = 0.3 + subjectivity * 0.3

            return Sentiment(label=label, score=min(1.0, max(0.0, score)))
        except Exception:
            return Sentiment(label="neutral", score=0.5)
    
    def _split_by_paragraphs(self, segments: list[TextSegment]) -> list[TextSegment]:
        """
        Split segments at paragraph boundaries (double newlines).
        Dialogue segments are kept intact; narration segments are split
        at paragraph breaks to create natural segment boundaries.
        """
        result: list[TextSegment] = []
        
        for segment in segments:
            if segment.type == "dialogue":
                result.append(segment)
                continue
            
            paragraphs = re.split(r'\n\s*\n', segment.text)
            paragraphs = [p.strip() for p in paragraphs if p.strip()]
            
            if len(paragraphs) <= 1:
                result.append(segment)
                continue
            
            for para_text in paragraphs:
                wc = len(para_text.split())
                result.append(TextSegment(
                    id=str(uuid.uuid4()),
                    type=segment.type,
                    text=para_text,
                    speaker=segment.speaker,
                    sentiment=self._analyze_sentiment(para_text),
                    startIndex=segment.startIndex,
                    endIndex=segment.endIndex,
                    wordCount=wc,
                    approxDurationSeconds=round(wc / self.WORDS_PER_SECOND, 1),
                ))
        
        return result

    def _chunk_all_segments(self, segments: list[TextSegment]) -> list[TextSegment]:
        """
        Chunk all segments into approximately 10-second intervals.
        """
        target_words = int(self.TARGET_CHUNK_SECONDS * self.WORDS_PER_SECOND)
        chunked: list[TextSegment] = []
        
        for segment in segments:
            words = segment.text.split()
            
            if len(words) <= target_words:
                chunked.append(segment)
                continue
            
            chunks = self._split_text_smart(segment.text, target_words)
            
            for chunk_text in chunks:
                ct = chunk_text.strip()
                if not ct:
                    continue
                wc = len(ct.split())
                chunked.append(TextSegment(
                    id=str(uuid.uuid4()),
                    type=segment.type,
                    text=ct,
                    speaker=segment.speaker,
                    sentiment=self._analyze_sentiment(ct),
                    startIndex=segment.startIndex,
                    endIndex=segment.endIndex,
                    wordCount=wc,
                    approxDurationSeconds=round(wc / self.WORDS_PER_SECOND, 1),
                ))
        
        return chunked
    
    def _split_text_smart(self, text: str, target_words: int) -> list[str]:
        """
        Split text into chunks following priority:
        1. Sentence endings (. ! ?)
        2. Quote breaks
        3. Colons or semicolons
        4. Commas
        5. Conjunctions (and, but, or, etc.)
        6. Between any words (last resort)
        """
        words = text.split()
        if len(words) <= target_words:
            return [text]
        
        chunks: list[str] = []
        remaining = text
        
        while remaining.strip():
            word_count = len(remaining.split())
            if word_count <= target_words:
                chunks.append(remaining.strip())
                break
            
            target_char_pos = self._words_to_chars(remaining, target_words)
            split_pos = self._find_best_split(remaining, target_char_pos)
            
            if split_pos <= 0 or split_pos >= len(remaining) - 1:
                split_pos = target_char_pos
                space_pos = remaining.rfind(' ', 0, split_pos + 1)
                if space_pos > 0:
                    split_pos = space_pos
            
            chunk = remaining[:split_pos].strip()
            remaining = remaining[split_pos:].strip()
            
            if chunk:
                chunks.append(chunk)
        
        return chunks
    
    def _words_to_chars(self, text: str, word_count: int) -> int:
        """Convert word count to approximate character position."""
        words = text.split()
        if word_count >= len(words):
            return len(text)
        
        char_pos = 0
        current_word = 0
        for i, char in enumerate(text):
            if char.isspace():
                if i > 0 and not text[i-1].isspace():
                    current_word += 1
                    if current_word >= word_count:
                        return i
        
        avg_chars = len(text) / max(1, len(words))
        return int(word_count * avg_chars)
    
    def _find_best_split(self, text: str, target_pos: int) -> int:
        """
        Find the best split point near target_pos following priority:
        1. Sentence endings (. ! ?)
        2. Colons or semicolons
        3. Commas
        4. Conjunctions
        5. Any space
        """
        search_start = max(0, target_pos - 100)
        search_end = min(len(text), target_pos + 50)
        search_region = text[search_start:search_end]
        
        sentence_ends = list(re.finditer(r'[.!?]\s+', search_region))
        if sentence_ends:
            best = max(sentence_ends, key=lambda m: m.end())
            return search_start + best.end()
        
        colons = list(re.finditer(r'[:;]\s+', search_region))
        if colons:
            best = max(colons, key=lambda m: m.end())
            return search_start + best.end()
        
        commas = list(re.finditer(r',\s+', search_region))
        if commas:
            mid = len(search_region) // 2
            best = min(commas, key=lambda m: abs(m.end() - mid))
            return search_start + best.end()
        
        conjunctions = list(re.finditer(r'\s+(and|but|or|yet|so|for|nor)\s+', search_region, re.IGNORECASE))
        if conjunctions:
            mid = len(search_region) // 2
            best = min(conjunctions, key=lambda m: abs(m.start() - mid))
            return search_start + best.start()
        
        spaces = list(re.finditer(r'\s+', search_region))
        if spaces:
            mid = len(search_region) // 2
            best = min(spaces, key=lambda m: abs(m.start() - mid))
            return search_start + best.start()
        
        return target_pos
