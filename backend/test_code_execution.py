"""Focused tests for code-execution routing in planner.py."""
import pytest

from agents.planner import decide


class TestCodeExecutionRouting:
    """Tests for code-execution routing decisions."""

    # --- Should route to python ---
    def test_what_is_output_of_code(self):
        assert decide("What is the output of:\nx = 10\ny = 20\nprint(x + y)") == "python"

    def test_run_this_python_code(self):
        assert decide("Run this Python code:\nx = 10\ny = 20\nprint(x + y)") == "python"

    def test_execute_code(self):
        assert decide("Execute:\nx = 10\ny = 20\nprint(x + y)") == "python"

    def test_what_does_python_code_output(self):
        assert decide("What does this Python code output?\nx = 10\ny = 20\nprint(x + y)") == "python"

    def test_fenced_python_block(self):
        assert decide("```python\nx = 10\ny = 20\nprint(x + y)\n```") == "python"

    def test_what_is_output_of_function_definition(self):
        assert decide("What is the output of:\ndef add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)") == "python"

    # --- Should NOT route to python (preserve RAG for document questions) ---
    def test_what_is_output_no_code_general_knowledge(self):
        assert decide("What is the output?") == "general_knowledge"

    def test_what_is_output_of_document_rag(self):
        assert decide("What is the output of the document?") == "rag"

    # --- Should stay chat (programming explanation, not execution) ---
    def test_operator_explanation(self):
        assert decide("What does * mean in Python?") == "chat"

    def test_explain_code_with_numbers(self):
        assert decide("Explain 27 * 43 in this code.") == "chat"

    # --- Existing routing must not regress ---
    def test_arithmetic_expression(self):
        assert decide("What is 27 * 43?") == "python"

    def test_fresh_factual(self):
        assert decide("What is the capital of Andhra Pradesh?") == "web"

    def test_weather_current_info(self):
        assert decide("What is the weather today?") == "current_info"

    def test_time(self):
        assert decide("What time is it?") == "time"

    def test_code_explanation_keyword(self):
        assert decide("Explain this code") == "code_explanation"

    def test_greeting(self):
        assert decide("hi") == "chat"

    def test_sequence_stays_chat(self):
        assert decide("What comes next: 2, 4, 8, 16, ?") == "chat"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])