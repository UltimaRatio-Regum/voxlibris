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
        
        name_map = self._build_speaker_normalization_map(speakers_set)
        if name_map:
            for seg in raw_segments:
                if seg.speaker and seg.speaker in name_map:
                    seg.speaker = name_map[seg.speaker]
            speakers_set = {name_map.get(s, s) for s in speakers_set}

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
    
    PRONOUNS_MALE = {"he", "him", "his"}
    PRONOUNS_FEMALE = {"she", "her", "hers"}

    def _find_speaker_improved(
        self, 
        text: str, 
        quote_start: int, 
        quote_end: int,
        speaker_history: list[str]
    ) -> Optional[str]:
        """
        Find speaker using multiple strategies:
        1. Explicit dialogue tags with named speakers
        2. Multi-word speaker names in dialogue tags (e.g. "said the old man")
        3. Pronoun-based dialogue tags resolved against nearby named characters
        4. Named character mentioned in narration immediately before the quote
        5. Turn-taking: alternate between the last two speakers
        """
        context_before = text[max(0, quote_start - 200):quote_start]
        context_after = text[quote_end:min(len(text), quote_end + 200)]

        named = self._find_named_speaker_in_tag(context_before, context_after)
        if named:
            return named

        multi = self._find_multiword_speaker_in_tag(context_after, context_before)
        if multi:
            return multi

        pronoun_speaker = self._resolve_pronoun_speaker(
            context_before, context_after, text, quote_start, speaker_history
        )
        if pronoun_speaker:
            return pronoun_speaker

        narrative_speaker = self._find_speaker_in_narration(context_before, speaker_history)
        if narrative_speaker:
            return narrative_speaker

        turn_speaker = self._infer_turn_taking(speaker_history)
        if turn_speaker:
            return turn_speaker

        return None

    STOP_WORDS_LOWER = {
        "the", "a", "an", "this", "that", "then", "but", "and", "it",
        "he", "she", "him", "her", "his", "hers", "they", "them",
        "i", "me", "my", "we", "us", "our", "you", "your",
    }

    def _find_named_speaker_in_tag(self, ctx_before: str, ctx_after: str) -> Optional[str]:
        ctx_after_clean = re.sub(r'^[\s""\u201c\u201d,]+', '', ctx_after)
        for ctx, is_after in [(ctx_after_clean, True), (ctx_before, False)]:
            for verb in self.DIALOGUE_VERBS:
                if is_after:
                    pat = rf'(?i)^\s*,?\s*{verb}[sd]?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)'
                    m = re.search(pat, ctx)
                    if not m:
                        pat2 = rf'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+{verb}[sd]?\b'
                        m = re.search(pat2, ctx)
                else:
                    pat = rf'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?i:{verb}[sd]?)\s*[,.]?\s*$'
                    m = re.search(pat, ctx)
                if m:
                    name = m.group(1).strip()
                    if name.lower() not in self.STOP_WORDS_LOWER:
                        return name
        return None

    def _find_multiword_speaker_in_tag(self, ctx_after: str, ctx_before: str) -> Optional[str]:
        for verb in self.DIALOGUE_VERBS:
            pat = rf'^\s*,?\s*{verb}[sd]?\s+(the\s+\w+(?:\s+\w+)?)'
            m = re.search(pat, ctx_after, re.IGNORECASE)
            if m:
                return m.group(1).strip()
            pat2 = rf'(the\s+\w+(?:\s+\w+)?)\s+{verb}[sd]?\s*[,.]?\s*$'
            m2 = re.search(pat2, ctx_before, re.IGNORECASE)
            if m2:
                return m2.group(1).strip()
        return None

    def _resolve_pronoun_speaker(
        self, ctx_before: str, ctx_after: str, full_text: str,
        quote_start: int, speaker_history: list[str]
    ) -> Optional[str]:
        pronoun_found = None
        ctx_after_clean = re.sub(r'^[\s""\u201c\u201d]+', '', ctx_after)

        for verb in self.DIALOGUE_VERBS:
            pat_pron_verb = rf'^(he|she)\s+{verb}[sd]?\b'
            m = re.search(pat_pron_verb, ctx_after_clean, re.IGNORECASE)
            if m:
                pronoun_found = m.group(1).lower()
                break
            pat_verb_pron = rf'^{verb}[sd]?\s+(he|she)\b'
            m2 = re.search(pat_verb_pron, ctx_after_clean, re.IGNORECASE)
            if m2:
                pronoun_found = m2.group(1).lower()
                break
            pat_before = rf'\b(he|she)\s+{verb}[sd]?\s*[,.]?\s*$'
            m3 = re.search(pat_before, ctx_before, re.IGNORECASE)
            if m3:
                pronoun_found = m3.group(1).lower()
                break

        if not pronoun_found:
            return None

        ctx_before_clean = re.sub(r'[\s""\u201c\u201d]+$', '', ctx_before)
        has_narration_gap = bool(re.search(r'[.!?]\s+[A-Z]', ctx_before_clean[-60:])) if ctx_before_clean else False

        if len(speaker_history) >= 2 and has_narration_gap:
            last_speaker = speaker_history[-1]
            for name in reversed(speaker_history[:-1]):
                if name != last_speaker:
                    return name

        if speaker_history:
            return speaker_history[-1]

        nearby_text = full_text[max(0, quote_start - 500):quote_start]
        name_pattern = re.compile(r'\b([A-Z][a-z]{2,})\b')
        nearby_names = name_pattern.findall(nearby_text)

        stop_words_upper = {
            "The", "And", "But", "Then", "This", "That", "His", "Her", "She", "He",
            "They", "Their", "When", "What", "Where", "How", "Why", "With", "From",
            "Into", "Before", "After", "About", "Just", "Even", "Still", "Already",
            "Not", "For", "Its", "All", "Some", "Any", "Each", "One", "Two",
        }
        nearby_names = [n for n in nearby_names if n not in stop_words_upper]

        if nearby_names:
            return nearby_names[-1]

        return None

    def _build_speaker_normalization_map(self, speakers: set[str]) -> dict[str, str]:
        name_map: dict[str, str] = {}
        speaker_list = sorted(speakers, key=len)

        for i, short in enumerate(speaker_list):
            for long_name in speaker_list[i+1:]:
                if short in long_name.split():
                    name_map[long_name] = short
                    break

        return name_map

    def _find_speaker_in_narration(self, ctx_before: str, speaker_history: list[str]) -> Optional[str]:
        sentences = [s for s in re.split(r'[.!?]\s+', ctx_before) if s.strip()]
        last_sentence = sentences[-1] if sentences else ctx_before

        stop_words = {
            "the", "and", "but", "then", "this", "that", "his", "her", "she", "he",
            "they", "their", "when", "what", "where", "how", "why", "with", "from",
            "into", "before", "after", "about", "just", "even", "still", "already",
            "not", "for", "its", "all", "some", "any", "each", "one", "two",
            "suddenly", "meanwhile", "however", "finally", "later", "outside",
            "inside", "perhaps", "slowly", "quickly", "meanwhile", "instead",
        }

        known = set(speaker_history)
        for name in known:
            if name in last_sentence:
                return name

        name_pattern = re.compile(r'\b([A-Z][a-z]{2,})\b')
        names_in_last = name_pattern.findall(last_sentence)
        for name in names_in_last:
            if name.lower() not in stop_words:
                if re.search(r'\b' + re.escape(name) + r'\b(?!\s+(was|is|were|are|had|has|the|a)\b)', last_sentence):
                    return name

        return None

    def _infer_turn_taking(self, speaker_history: list[str]) -> Optional[str]:
        if len(speaker_history) < 2:
            return None

        last = speaker_history[-1]
        unique_recent = []
        for sp in reversed(speaker_history):
            if sp not in unique_recent:
                unique_recent.append(sp)
            if len(unique_recent) >= 2:
                break

        if len(unique_recent) >= 2:
            return unique_recent[1] if unique_recent[0] == last else unique_recent[0]

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
