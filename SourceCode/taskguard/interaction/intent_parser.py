"""Intent parser: natural language to structured tool calls.

Relates-to: FR-4
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from taskguard.interaction.prompts import INTENT_SYSTEM_PROMPT
from taskguard.llm.base import BaseProvider, LLMError, Message

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IntentParseResult:
    """Result of parsing natural language input."""

    tool_name: str
    params: dict[str, Any]
    missing_params: list[str]
    confidence: float


class IntentParser:
    """Parse natural language into structured intent using LLM."""

    def __init__(self, provider: BaseProvider | None) -> None:
        self._provider = provider

    async def parse(self, user_input: str) -> IntentParseResult:
        """Parse user input into structured intent.

        Falls back to unknown if LLM is unavailable or parsing fails.
        """
        if self._provider is None:
            return IntentParseResult(
                tool_name="unknown",
                params={},
                missing_params=[],
                confidence=0.0,
            )

        try:
            messages = [Message(role="user", content=user_input)]
            response = await self._provider.complete(
                system=INTENT_SYSTEM_PROMPT,
                messages=messages,
            )

            content = response.content.strip()
            # Some models wrap JSON in markdown code blocks
            if content.startswith("```"):
                lines = content.splitlines()
                # Remove first and last lines if they are markdown fences
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines).strip()

            parsed = json.loads(content)

            return IntentParseResult(
                tool_name=parsed.get("tool_name", "unknown"),
                params=parsed.get("params", {}),
                missing_params=parsed.get("missing_params", []),
                confidence=float(parsed.get("confidence", 0.0)),
            )
        except (LLMError, json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Intent parsing failed: %s", exc)
            return IntentParseResult(
                tool_name="unknown",
                params={},
                missing_params=[],
                confidence=0.0,
            )
