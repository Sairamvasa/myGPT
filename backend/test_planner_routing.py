"""Focused planner routing tests. Tests only decide() output, no execution."""
import pytest

from agents.planner import decide, ACTION_CHAT, ACTION_PYTHON, ACTION_WEB, ACTION_RAG, ACTION_TIME, ACTION_CODE, ACTION_CODE_EXPLANATION, ACTION_CURRENT_INFO, ACTION_WEB_RESEARCH, ACTION_GENERAL_KNOWLEDGE, ACTION_MATH, ACTION_CREATIVE


class TestPlannerRouting:
    """Tests for planner routing decisions."""

    # --- Arithmetic without "calculate" ---
    def test_multiplication_without_keyword(self):
        assert decide("What is 27 * 43?") == ACTION_PYTHON

    def test_addition_without_keyword(self):
        assert decide("What is 125 + 378?") == ACTION_PYTHON

    def test_division_without_keyword(self):
        assert decide("What is 144 / 12?") == ACTION_PYTHON

    def test_how_much_is_multiplication(self):
        assert decide("How much is 99 * 17?") == ACTION_PYTHON

    # --- Arithmetic with "calculate" ---
    def test_calculate_multiplication(self):
        assert decide("Calculate 27 * 43") == ACTION_PYTHON

    def test_compute_addition(self):
        assert decide("Compute 125 + 378") == ACTION_PYTHON

    # --- Percentage calculation ---
    def test_percentage_calculation(self):
        assert decide("25% of 800?") == ACTION_PYTHON

    # --- Subtraction word problem ---
    def test_subtraction_word_problem(self):
        assert decide("If I have 5 apples and give away 2, how many remain?") == ACTION_PYTHON

    # --- Programming questions with math symbols (must stay chat) ---
    def test_operator_question_in_python(self):
        assert decide("What does * mean in Python?") == ACTION_CHAT

    def test_code_explanation_with_numbers(self):
        assert decide("Explain 27 * 43 in this code") == ACTION_CHAT

    # --- Sequence question stays chat ---
    def test_sequence_question_stays_chat(self):
        assert decide("What comes next: 2, 4, 8, 16, ?") == ACTION_CHAT

    # --- Current/fresh factual routes web ---
    def test_capital_question_routes_web(self):
        assert decide("What is the capital of Andhra Pradesh?") == ACTION_WEB

    def test_population_question_routes_web(self):
        assert decide("What is the population of India?") == ACTION_WEB

    def test_current_leader_routes_web(self):
        assert decide("Who is the president of India?") == ACTION_WEB

    # --- Stable factual stays general_knowledge ---
    def test_stable_literary_fact_routes_general_knowledge(self):
        assert decide("Who wrote Romeo and Juliet?") == ACTION_GENERAL_KNOWLEDGE

    def test_stable_geographic_fact_routes_general_knowledge(self):
        assert decide("What is the largest ocean?") == ACTION_GENERAL_KNOWLEDGE

    # --- Code generation routes code ---
    def test_java_gcd_code_generation(self):
        assert decide("Write a Java program to find GCD of two numbers") == ACTION_CODE

    def test_python_script_generation(self):
        assert decide("Write a Python script to sort a list") == ACTION_CODE

    def test_function_generation(self):
        assert decide("Generate a function to calculate factorial") == ACTION_CODE

    # --- Code explanation routes code_explanation ---
    def test_code_explanation_line_by_line(self):
        assert decide("Explain this code line by line") == ACTION_CODE_EXPLANATION

    def test_code_explanation_routes_code_explanation(self):
        assert decide("Explain this code") == ACTION_CODE_EXPLANATION

    def test_what_does_code_do_routes_code_explanation(self):
        assert decide("What does this code do?") == ACTION_CODE_EXPLANATION

    # --- Existing RAG routing unchanged ---
    def test_output_question_routes_general_knowledge(self):
        # "What is the output?" without code/document context should be general_knowledge
        assert decide("What is the output?") == ACTION_GENERAL_KNOWLEDGE

    def test_code_review_routes_rag(self):
        assert decide("Find any problems in this code") == ACTION_RAG

    # --- Current info routes current_info ---
    def test_petrol_price_routes_current_info(self):
        assert decide("Today's petrol price in India") == ACTION_CURRENT_INFO

    def test_bitcoin_price_routes_current_info(self):
        assert decide("Current Bitcoin price") == ACTION_CURRENT_INFO

    def test_weather_today_routes_current_info(self):
        assert decide("Weather today") == ACTION_CURRENT_INFO

    # --- Web research routes web_research ---
    def test_latest_news_routes_web_research(self):
        assert decide("Latest AI news") == ACTION_WEB_RESEARCH

    def test_recent_developments_routes_web_research(self):
        assert decide("Recent developments in AI") == ACTION_WEB_RESEARCH

    # --- Existing web routing unchanged ---
    def test_weather_today_routes_current_info_2(self):
        assert decide("What is the weather today?") == ACTION_CURRENT_INFO

    def test_latest_news_headlines_routes_web_research(self):
        assert decide("What are the latest AI news headlines?") == ACTION_WEB_RESEARCH

    # --- Existing time routing unchanged ---
    def test_time_question_routes_time(self):
        assert decide("What time is it?") == ACTION_TIME

    def test_date_question_routes_time(self):
        assert decide("What is today's date?") == ACTION_TIME

    # --- Existing chat routing unchanged ---
    def test_greeting_stays_chat(self):
        assert decide("hi") == ACTION_CHAT

    def test_hello_stays_chat(self):
        assert decide("hello") == ACTION_CHAT

    def test_how_are_you_stays_chat(self):
        assert decide("How are you?") == ACTION_CHAT

    def test_joke_routes_creative(self):
        assert decide("Tell me a joke") == ACTION_CREATIVE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])