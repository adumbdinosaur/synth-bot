import os
import json
import logging
from typing import Dict, Any
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class AutocorrectManager:
    """Manages autocorrect functionality using OpenAI API."""

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not found in environment variables")
            self.enabled = False
            self.client = None
        else:
            try:
                self.client = AsyncOpenAI(api_key=self.api_key)
                self.enabled = True
                logger.info("OpenAI client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                self.enabled = False
                self.client = None

    async def correct_spelling(self, text: str) -> Dict[str, Any]:
        """
        Correct spelling in the given text using OpenAI API.
        
        Args:
            text: The text to correct
            
        Returns:
            Dict with keys 'sentence' (corrected text) and 'count' (number of corrections)
        """
        if not self.enabled:
            logger.warning("Autocorrect is disabled - OPENAI_API_KEY not configured")
            return {"sentence": text, "count": 0}

        if not text or not text.strip():
            return {"sentence": text, "count": 0}

        try:
            # OpenAI prompt for spell checking
            prompt = (
                "You are a spell checker. You correct the spelling of words into American English standard spelling. "
                "If you do not know the spelling of a word, do not guess and leave it be. "
                "Do not change the structure of the sentence. "
                "Respond with a json object with the keys 'sentence' and 'count' where sentence is the corrected sentence "
                "and count is the number of corrections"
            )

            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ],
                max_tokens=500,
                temperature=0.1
            )

            # Parse the response
            content = response.choices[0].message.content.strip()
            
            # Try to parse JSON response
            try:
                result = json.loads(content)
                if isinstance(result, dict) and "sentence" in result and "count" in result:
                    return {
                        "sentence": result["sentence"],
                        "count": int(result["count"])
                    }
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse OpenAI JSON response: {content}")

            # Fallback if JSON parsing fails
            logger.warning("OpenAI did not return valid JSON, using original text")
            return {"sentence": text, "count": 0}

        except Exception as e:
            logger.error(f"Error in autocorrect: {e}")
            return {"sentence": text, "count": 0}


# Global instance
_autocorrect_manager = None


def get_autocorrect_manager() -> AutocorrectManager:
    """Get the global autocorrect manager instance."""
    global _autocorrect_manager
    if _autocorrect_manager is None:
        _autocorrect_manager = AutocorrectManager()
    return _autocorrect_manager
