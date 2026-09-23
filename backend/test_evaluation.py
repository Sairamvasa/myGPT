#!/usr/bin/env python3
"""
Comprehensive AI Evaluation Test Suite for MyGPT.

Tests model behavior across multiple categories without modifying production code.
Records metrics: latency, RAG usage, pass/fail, hallucination detection.
"""

import os
import sys
import time
import tempfile
import shutil
import json
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any

sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from agents.planner import decide
from llm import ask_llm, OLLAMA_MODEL, _generation_options
from rag import process_text_file, search_pdf


@dataclass
class TestResult:
    test_name: str
    category: str
    question: str
    model_answer: str
    expected_criteria: str
    passed: bool
    latency_ms: float
    rag_used: bool
    model_name: str
    action: str
    hallucination: bool = False
    details: str = ""


class EvaluationSuite:
    def __init__(self):
        self.agent = Agent()
        self.results: List[TestResult] = []
        self.user_id = 8888
        self.chat_id = 1
        self.rag_dir = os.path.join("rag_indexes", str(self.user_id))
        
    def setup_rag(self):
        """Upload calculator.py for RAG tests."""
        if os.path.exists(self.rag_dir):
            shutil.rmtree(self.rag_dir)
            
        CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(CALC)
            tmp = f.name
            
        process_text_file(tmp, self.user_id, source_filename="calculator.py")
        os.unlink(tmp)
        
    def cleanup_rag(self):
        if os.path.exists(self.rag_dir):
            shutil.rmtree(self.rag_dir)
    
    def run_test(self, test_name: str, category: str, question: str, 
                 expected_criteria: str, check_fn, use_rag: bool = False,
                 history: list = None, memories: list = None) -> TestResult:
        """Run a single test and record results."""
        
        start_time = time.perf_counter()
        
        # Run through agent to get action and context
        result = self.agent.run(
            question, 
            chat_id=self.chat_id, 
            user_id=self.user_id if use_rag else None
        )
        
        # Get model answer
        try:
            model_answer = ask_llm(result["prompt"])
        except Exception as e:
            model_answer = f"[LLM Error: {e}]"
        
        latency_ms = (time.perf_counter() - start_time) * 1000
        
        # Check if RAG was used
        rag_used = result.get("context") is not None
        action = result.get("action", "unknown")
        
        # Evaluate
        passed, hallucination, details = check_fn(model_answer, expected_criteria)
        
        test_result = TestResult(
            test_name=test_name,
            category=category,
            question=question,
            model_answer=model_answer[:500],  # truncate for report
            expected_criteria=expected_criteria,
            passed=passed,
            latency_ms=round(latency_ms, 2),
            rag_used=rag_used,
            model_name=OLLAMA_MODEL,
            action=action,
            hallucination=hallucination,
            details=details
        )
        
        self.results.append(test_result)
        return test_result
    
    def print_result(self, result: TestResult):
        status = "PASS" if result.passed else "FAIL"
        hall = " [HALLUCINATION]" if result.hallucination else ""
        print(f"  [{status}] {result.test_name}{hall}")
        print(f"      Question: {result.question}")
        print(f"      Answer: {result.model_answer[:200]}...")
        print(f"      Expected: {result.expected_criteria}")
        print(f"      Latency: {result.latency_ms}ms | RAG: {result.rag_used} | Action: {result.action}")
        if result.details:
            print(f"      Details: {result.details}")
        print()

    def run_all_tests(self):
        """Run all evaluation tests."""
        
        print("=" * 70)
        print("MyGPT COMPREHENSIVE AI EVALUATION")
        print("=" * 70)
        print(f"Model: {OLLAMA_MODEL}")
        print(f"Temperature: {_generation_options().get('temperature')}")
        print()
        
        # ========== 1. GENERAL KNOWLEDGE ==========
        print("\n" + "=" * 70)
        print("CATEGORY 1: GENERAL KNOWLEDGE")
        print("=" * 70)
        
        def check_capital_ap(answer, criteria):
            answer_lower = answer.lower()
            # Correct: Amaravati is the capital (post-2014)
            # Hallucination: Visakhapatnam (old), Hyderabad (old), or any other
            if "amaravati" in answer_lower:
                return True, False, "Correctly identifies Amaravati"
            elif "visakhapatnam" in answer_lower:
                return False, True, "Hallucination: Visakhapatnam is not the capital (was temporary)"
            elif "hyderabad" in answer_lower:
                return False, True, "Hallucination: Hyderabad was pre-2014"
            else:
                return False, True, f"Wrong answer or no clear capital stated"
        
        self.run_test(
            "Capital of Andhra Pradesh",
            "General Knowledge",
            "What is the capital of Andhra Pradesh?",
            "Amaravati",
            check_capital_ap
        )
        
        def check_capital_india(answer, criteria):
            if "new delhi" in answer.lower() or "delhi" in answer.lower():
                return True, False, "Correct"
            return False, True, "Incorrect capital"
        
        self.run_test(
            "Capital of India",
            "General Knowledge",
            "What is the capital of India?",
            "New Delhi",
            check_capital_india
        )
        
        def check_romeo_juliet(answer, criteria):
            if "shakespeare" in answer.lower() or "william shakespeare" in answer.lower():
                return True, False, "Correct"
            return False, True, "Incorrect author"
        
        self.run_test(
            "Author of Romeo and Juliet",
            "General Knowledge",
            "Who wrote Romeo and Juliet?",
            "William Shakespeare",
            check_romeo_juliet
        )
        
        # ========== 2. BASIC REASONING ==========
        print("\n" + "=" * 70)
        print("CATEGORY 2: BASIC REASONING")
        print("=" * 70)
        
        def check_apples(answer, criteria):
            if "3" in answer and ("apple" in answer.lower() or "remain" in answer.lower()):
                return True, False, "Correct arithmetic"
            return False, True, "Wrong arithmetic"
        
        self.run_test(
            "Apple subtraction",
            "Basic Reasoning",
            "If I have 5 apples and give away 2, how many remain?",
            "3 apples",
            check_apples
        )
        
        def check_sequence(answer, criteria):
            # Sequence: 2, 4, 8, 16, ? -> 32 (powers of 2)
            if "32" in answer:
                return True, False, "Correct pattern recognition"
            return False, True, "Wrong pattern"
        
        self.run_test(
            "Number sequence 2,4,8,16,?",
            "Basic Reasoning",
            "What comes next: 2, 4, 8, 16, ?",
            "32",
            check_sequence
        )
        
        # ========== 3. MATH ==========
        print("\n" + "=" * 70)
        print("CATEGORY 3: MATH")
        print("=" * 70)
        
        def check_mul_27_43(answer, criteria):
            # 27 * 43 = 1161
            if "1161" in answer:
                return True, False, "Correct multiplication"
            return False, True, "Wrong multiplication result"
        
        self.run_test(
            "27 * 43",
            "Math",
            "What is 27 * 43?",
            "1161",
            check_mul_27_43
        )
        
        def check_add_125_378(answer, criteria):
            # 125 + 378 = 503
            if "503" in answer:
                return True, False, "Correct addition"
            return False, True, "Wrong addition result"
        
        self.run_test(
            "125 + 378",
            "Math",
            "What is 125 + 378?",
            "503",
            check_add_125_378
        )
        
        def check_div_144_12(answer, criteria):
            # 144 / 12 = 12
            if "12" in answer:
                return True, False, "Correct division"
            return False, True, "Wrong division result"
        
        self.run_test(
            "144 / 12",
            "Math",
            "What is 144 / 12?",
            "12",
            check_div_144_12
        )
        
        # ========== 4. CODING ==========
        print("\n" + "=" * 70)
        print("CATEGORY 4: CODING")
        print("=" * 70)
        
        def check_factorial_code(answer, criteria):
            has_code = "```" in answer
            has_factorial = "factorial" in answer.lower()
            has_recursion_or_loop = ("def factorial" in answer.lower() or 
                                      "for" in answer or "while" in answer)
            if has_code and has_factorial and has_recursion_or_loop:
                return True, False, "Valid factorial implementation"
            return False, False, "Missing code or incomplete"
        
        self.run_test(
            "Write factorial function",
            "Coding",
            "Write a Python function to calculate factorial.",
            "Python function with factorial logic",
            check_factorial_code
        )
        
        def check_explain_code(answer, criteria):
            # Should explain what the function does
            if "add" in answer.lower() and ("return" in answer.lower() or "sum" in answer.lower()):
                return True, False, "Explains function behavior"
            return False, False, "Inadequate explanation"
        
        self.run_test(
            "Explain simple Python function",
            "Coding",
            "Explain this Python function:\n\ndef add(a, b):\n    return a + b",
            "Explains that it adds two numbers",
            check_explain_code
        )
        
        # ========== 5. CODE REASONING ==========
        print("\n" + "=" * 70)
        print("CATEGORY 5: CODE REASONING")
        print("=" * 70)
        
        def check_code_output_10_20(answer, criteria):
            # x=10, y=20, print(x+y) -> 30
            if "30" in answer:
                return True, False, "Correct output"
            return False, True, "Wrong output"
        
        self.run_test(
            "Code output: x=10,y=20,print(x+y)",
            "Code Reasoning",
            "What is the output of:\nx = 10\ny = 20\nprint(x + y)",
            "30",
            check_code_output_10_20
        )
        
        # ========== 6. CONVERSATION CONTEXT ==========
        print("\n" + "=" * 70)
        print("CATEGORY 6: CONVERSATION CONTEXT")
        print("=" * 70)
        
        # First, set up memory using the same chat/user
        context_chat_id = 999
        context_user_id = 777
        msg1 = "My favorite language is Python."
        self.agent.run(msg1, chat_id=context_chat_id, user_id=context_user_id)
        time.sleep(0.5)
        
        def check_fav_lang(answer, criteria):
            if "python" in answer.lower():
                return True, False, "Remembers from context"
            return False, True, "Failed to recall"
        
        self.run_test(
            "Recall favorite language",
            "Conversation Context",
            "What is my favorite language?",
            "Python",
            check_fav_lang
        )
        
        # ========== 7. HALLUCINATION/TRICK QUESTIONS ==========
        print("\n" + "=" * 70)
        print("CATEGORY 7: HALLUCINATION / TRICK QUESTIONS")
        print("=" * 70)
        
        def check_false_premise_country(answer, criteria):
            # "What is the capital of France?" with false premise "in Asia"
            # Should correct the premise, not accept it
            answer_lower = answer.lower()
            if "paris" in answer_lower:
                if "no capital" in answer_lower or "not in asia" in answer_lower or "europe" in answer_lower:
                    return True, False, "Correctly rejects false premise"
                elif "asia" in answer_lower and "paris" in answer_lower:
                    # Model says "capital of France is Paris" but also mentions Asia context - acceptable
                    return True, False, "Correctly identifies Paris, addresses premise"
            return False, True, "Didn't answer correctly or accepted false premise"
        
        self.run_test(
            "False premise: France in Asia",
            "Hallucination/Trick",
            "What is the capital of France in Asia?",
            "Should correct: France is in Europe, capital is Paris",
            check_false_premise_country
        )
        
        def check_false_premise_person(answer, criteria):
            # "Who is the president of Mars?" - should reject
            answer_lower = answer.lower()
            if "mars" in answer_lower and ("no" in answer_lower or "no president" in answer_lower 
                                             or "not a country" in answer_lower or "fictional" in answer_lower):
                return True, False, "Correctly rejects false premise"
            elif "president" in answer_lower and "mars" in answer_lower:
                return False, True, "Hallucinated a president of Mars"
            return False, False, "Unclear response"
        
        self.run_test(
            "False premise: President of Mars",
            "Hallucination/Trick",
            "Who is the president of Mars?",
            "Should reject: Mars has no president",
            check_false_premise_person
        )
        
        def check_false_fact_amazon(answer, criteria):
            # "The Amazon river flows through Africa" - should correct
            answer_lower = answer.lower()
            if "false" in answer_lower:
                if "south america" in answer_lower or "brazil" in answer_lower or "not africa" in answer_lower:
                    return True, False, "Correctly identifies as false with correction"
                # Just "False" is minimally acceptable
                return True, False, "Correctly identifies as false"
            return False, False, "Did not answer True/False clearly"
        
        self.run_test(
            "False fact: Amazon in Africa",
            "Hallucination/Trick",
            "The Amazon river flows through Africa. True or false?",
            "False - Amazon is in South America",
            check_false_fact_amazon
        )
        
        # ========== 8. RAG ==========
        print("\n" + "=" * 70)
        print("CATEGORY 8: RAG (Retrieval Augmented Generation)")
        print("=" * 70)
        
        self.setup_rag()
        
        def check_rag_output_30(answer, criteria):
            # calculator.py: add(10, 20) -> 30
            if "30" in answer:
                return True, False, "Correct grounded answer"
            return False, True, f"Wrong answer: expected 30"
        
        self.run_test(
            "RAG: What is the output?",
            "RAG",
            "What is the output?",
            "30 (from add(10, 20))",
            check_rag_output_30,
            use_rag=True
        )
        
        def check_rag_explain_code(answer, criteria):
            # Should explain the calculator.py code
            answer_lower = answer.lower()
            if "add" in answer_lower and ("return" in answer_lower or "sum" in answer_lower):
                if "10" in answer and "20" in answer:
                    return True, False, "Explains code with specific values"
                return True, False, "Explains code generally"
            return False, False, "Inadequate explanation"
        
        self.run_test(
            "RAG: Explain this code",
            "RAG",
            "Explain this code",
            "Explains add function and print output",
            check_rag_explain_code,
            use_rag=True
        )
        
        self.cleanup_rag()
        
        # ========== SUMMARY ==========
        self.print_summary()
        return self.results
    
    def print_summary(self):
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        accuracy = (passed / total * 100) if total > 0 else 0
        hallucinations = sum(1 for r in self.results if r.hallucination)
        
        rag_tests = [r for r in self.results if r.category == "RAG"]
        rag_passed = sum(1 for r in rag_tests if r.passed)
        rag_accuracy = (rag_passed / len(rag_tests) * 100) if rag_tests else 0
        
        avg_latency = sum(r.latency_ms for r in self.results) / total if total > 0 else 0
        
        print("\n" + "=" * 70)
        print("EVALUATION SUMMARY")
        print("=" * 70)
        print(f"Total tests:        {total}")
        print(f"Passed:             {passed}")
        print(f"Failed:             {failed}")
        print(f"Accuracy:           {accuracy:.1f}%")
        print(f"Hallucinations:     {hallucinations}")
        print(f"RAG tests:          {len(rag_tests)}")
        print(f"RAG accuracy:       {rag_accuracy:.1f}%")
        print(f"Average latency:    {avg_latency:.1f}ms")
        print()
        
        # Category breakdown
        categories = {}
        for r in self.results:
            if r.category not in categories:
                categories[r.category] = {"total": 0, "passed": 0}
            categories[r.category]["total"] += 1
            if r.passed:
                categories[r.category]["passed"] += 1
        
        print("Category breakdown:")
        for cat, stats in categories.items():
            cat_acc = (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            print(f"  {cat}: {stats['passed']}/{stats['total']} ({cat_acc:.1f}%)")
        
        # Save detailed results to JSON
        output_file = "evaluation_results.json"
        with open(output_file, "w") as f:
            json.dump([asdict(r) for r in self.results], f, indent=2)
        print(f"\nDetailed results saved to: {output_file}")


def main():
    suite = EvaluationSuite()
    results = suite.run_all_tests()
    
    # Exit with non-zero if any hallucinations detected
    hallucinations = sum(1 for r in results if r.hallucination)
    if hallucinations > 0:
        print(f"\nWARNING: {hallucinations} hallucination(s) detected!")
        sys.exit(1)
    else:
        print("\nNo hallucinations detected")
        sys.exit(0)


if __name__ == "__main__":
    main()