"""
AURA Voice Agent — thin wrapper around the shared MyGPT Agent pipeline.

AURA is purely a voice *interface*:
    STT  →  MyGPTAgent.run()  →  ask_llm_routed()  →  verification  →  TTS

There is NO separate intelligence here.  All planning, memory, RAG, tool
execution, and LLM generation happen inside MyGPTAgent — identical to the
text-chat path in app.py.

The only difference from the text-chat path is:
  - Input arrives as text that has already been transcribed by STT.
  - Output is handed back to the caller for TTS synthesis.

Bug fix (Phase 1):
  Previously this module called ask_llm() directly, bypassing:
    - ask_llm_routed() (action-aware LLM routing)
    - RAG grounding  (agents.rag_verifier.is_answer_safe_for_context)
    - Current-info grounding  (agents.grounding._enforce_current_info_grounding)
  All three steps are now applied, matching app.py exactly.
"""

import logging

from agents.agent import Agent as MyGPTAgent
from agents.grounding import _enforce_current_info_grounding
from agents.rag_verifier import is_answer_safe_for_context
from llm import ask_llm_routed, LLMError

logger = logging.getLogger("MyGPT.Voice.Agent")

_mygpt_agent = MyGPTAgent()


class VoiceAgent:
    """
    Voice interface wrapper.

    Delegates all intelligence to the shared MyGPTAgent so that voice
    and text requests always reach the same pipeline.
    """

    def process(
        self,
        text: str,
        chat_id: int | None,
        user_id: int,
        language: str = "auto",
    ) -> dict:
        """
        Process a voice request through the shared MyGPT Agent pipeline.

        Steps (mirrors app.py /chat and /stream endpoints):
          1. Run shared agent (planner → memory/RAG/tools → build_prompt)
          2. Generate response via ask_llm_routed() — NOT ask_llm()
          3. Apply RAG grounding if action == 'rag'
          4. Apply current-info grounding if action in ('current_info', 'web_research')

        Returns:
            dict with keys: user_text, response, action, tool_results
        Raises:
            LLMError  — re-raised as-is so the caller (routes.py) can
                        return the correct HTTP error code.
        """
        try:
            # ── Step 1: Shared agent pipeline ───────────────────────────────
            result = _mygpt_agent.run(text, chat_id, user_id)
            action = result.get("action", "chat")

            # ── Step 2: LLM generation via routed provider ───────────────────
            # ask_llm_routed() applies the same action-aware routing and
            # token limits used by the text-chat path.  ask_llm() was the
            # previous (incorrect) call that bypassed all of this.
            if result.get("answer"):
                # Agent returned a direct answer (time, sequence, image_gen …)
                answer = result["answer"]
            else:
                answer = ask_llm_routed(result["prompt"], action)

            # ── Step 3: RAG grounding ────────────────────────────────────────
            # Mirrors app.py line: if action == "rag" and result.get("context")
            if action == "rag" and result.get("context"):
                is_safe = is_answer_safe_for_context(
                    answer, result["context"], text
                )
                if not is_safe:
                    # Fallback identical to app.py
                    answer = (
                        "Based on the uploaded document, I can see the code defines "
                        "functions and variables. The exact output would require "
                        "executing the code. The document shows: "
                        f"{result['context'][:500]}..."
                    )

            # ── Step 4: Current-info / web-research grounding ────────────────
            # Mirrors app.py line: if action in ("current_info", "web_research")
            if action in ("current_info", "web_research"):
                answer = _enforce_current_info_grounding(
                    answer, result.get("tool_results")
                )

            if not answer or not answer.strip():
                answer = (
                    "⚠️ I couldn't generate an answer for this request. "
                    "Please try again."
                )

            return {
                "user_text": text,
                "response": answer,
                "action": action,
                "tool_results": result.get("tool_results"),
            }

        except LLMError:
            # Re-raise so routes.py can return the correct HTTP status code.
            raise
        except Exception as exc:
            logger.error("Voice agent error: %s", exc, exc_info=True)
            raise
