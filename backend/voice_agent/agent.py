import logging
from agents.agent import Agent as MyGPTAgent
from llm import ask_llm, LLMError

logger = logging.getLogger("MyGPT.Voice.Agent")

_mygpt_agent = MyGPTAgent()


class VoiceAgent:
    def process(self, text: str, chat_id: int, user_id: int, language: str = "auto") -> dict:
        try:
            result = _mygpt_agent.run(text, chat_id, user_id)
            answer = ask_llm(result["prompt"])
            return {
                "user_text": text,
                "response": answer,
                "action": result.get("action"),
                "tool_results": result.get("tool_results"),
            }
        except LLMError:
            raise
        except Exception as exc:
            logger.error(f"Voice agent error: {exc}")
            raise
