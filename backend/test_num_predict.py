"""Tests for refined smart num_predict selection."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from llm import get_num_predict, NVIDIA_NUM_PREDICT, NUM_PREDICT_SHORT, NUM_PREDICT_NORMAL, NUM_PREDICT_RAG, NUM_PREDICT_LONG

passed = 0
failed = 0

def check(name, actual, expected):
    global passed, failed
    if actual == expected:
        passed += 1
        print("  PASS: " + name + " -> " + str(actual))
    else:
        failed += 1
        print("  FAIL: " + name + " -> got " + str(actual) + ", expected " + str(expected))

def run_tests():
    global passed, failed
    passed = 0
    failed = 0

    print("=" * 60)
    print("TEST: Refined smart num_predict selection")
    print("=" * 60)

    # 1. RAG simple factual/output/value questions -> NUM_PREDICT_NORMAL
    check("RAG factual: 'What is the output?'", get_num_predict("rag", "What is the output?"), NUM_PREDICT_NORMAL)
    check("RAG factual: 'What is the result?'", get_num_predict("rag", "What is the result?"), NUM_PREDICT_NORMAL)
    check("RAG factual: 'What does this print?'", get_num_predict("rag", "What does this print?"), NUM_PREDICT_NORMAL)
    check("RAG factual: 'What is the value?'", get_num_predict("rag", "What is the value?"), NUM_PREDICT_NORMAL)
    check("RAG factual: 'What is the return value?'", get_num_predict("rag", "What is the return value?"), NUM_PREDICT_NORMAL)
    check("RAG factual: \"What's the output?\"", get_num_predict("rag", "What's the output?"), NUM_PREDICT_NORMAL)
    check("RAG factual: 'output of this code'", get_num_predict("rag", "output of this code"), NUM_PREDICT_NORMAL)
    check("RAG factual: 'result of this function'", get_num_predict("rag", "result of this function"), NUM_PREDICT_NORMAL)

    # 2. RAG code explanation/review/bug analysis -> NUM_PREDICT_RAG
    check("RAG explain: 'Explain this code'", get_num_predict("rag", "Explain this code"), NUM_PREDICT_RAG)
    check("RAG explain: 'Review this code'", get_num_predict("rag", "Review this code"), NUM_PREDICT_RAG)
    check("RAG explain: 'Analyze this code'", get_num_predict("rag", "Analyze this code"), NUM_PREDICT_RAG)
    check("RAG explain: 'What does this code do?'", get_num_predict("rag", "What does this code do?"), NUM_PREDICT_RAG)
    check("RAG explain: 'How does this code work?'", get_num_predict("rag", "How does this code work?"), NUM_PREDICT_RAG)
    check("RAG explain: 'Find any problems in this code'", get_num_predict("rag", "Find any problems in this code"), NUM_PREDICT_RAG)
    check("RAG explain: 'Bug in this code'", get_num_predict("rag", "Bug in this code"), NUM_PREDICT_RAG)
    check("RAG explain: 'Error in this code'", get_num_predict("rag", "Error in this code"), NUM_PREDICT_RAG)
    check("RAG explain: 'Code review'", get_num_predict("rag", "Code review"), NUM_PREDICT_RAG)

    # 3. RAG deep/long analysis -> NUM_PREDICT_LONG
    check("RAG long: 'explain in detail this code'", get_num_predict("rag", "explain in detail this code"), NUM_PREDICT_LONG)
    check("RAG long: 'analyze thoroughly this code'", get_num_predict("rag", "analyze thoroughly this code"), NUM_PREDICT_LONG)
    check("RAG long: 'step by step this code'", get_num_predict("rag", "step by step this code"), NUM_PREDICT_LONG)

    # 4. Normal short/simple questions -> NUM_PREDICT_SHORT
    check("normal short: 'What is 2+2?'", get_num_predict("chat", "What is 2+2?"), NUM_PREDICT_SHORT)
    check("normal short: 'calculate 15*15'", get_num_predict("chat", "calculate 15*15"), NUM_PREDICT_SHORT)

    # 5. Normal chat -> NUM_PREDICT_NORMAL
    check("normal chat: 'What is Python?'", get_num_predict("chat", "What is Python?"), NUM_PREDICT_NORMAL)
    check("normal chat: 'Tell me a joke'", get_num_predict("chat", "Tell me a joke"), NUM_PREDICT_NORMAL)

    # 6. Tool actions -> NUM_PREDICT_SHORT
    check("tool: time action", get_num_predict("time", "What time is it?"), NUM_PREDICT_SHORT)
    check("tool: python action", get_num_predict("python", "calculate 2+2"), NUM_PREDICT_SHORT)

    # 7. Environment override still works
    print("\n" + "=" * 60)
    print("TEST: Environment override caps results")
    print("=" * 60)
    import llm
    original = llm.NVIDIA_NUM_PREDICT
    try:
        llm.NVIDIA_NUM_PREDICT = 100
        check("env cap: RAG factual capped to 100", get_num_predict("rag", "What is the output?"), 100)  # 2048 > 100, capped to 100
        check("env cap: RAG explain capped to 100", get_num_predict("rag", "Explain this code"), 100)  # 2048 > 100, capped to 100
        check("env cap: short math capped to 100", get_num_predict("chat", "What is 2+2?"), 100)  # 256 > 100, capped to 100
    finally:
        llm.NVIDIA_NUM_PREDICT = original

    # 8. Default values
    print("\n" + "=" * 60)
    print("TEST: Default constants")
    print("=" * 60)
    check("NUM_PREDICT_SHORT = 256", NUM_PREDICT_SHORT, 256)
    check("NUM_PREDICT_NORMAL = 2048", NUM_PREDICT_NORMAL, 2048)
    check("NUM_PREDICT_RAG = 2048", NUM_PREDICT_RAG, 2048)
    check("NUM_PREDICT_LONG = 4096", NUM_PREDICT_LONG, 4096)
    check("NVIDIA_NUM_PREDICT default = 4096", NVIDIA_NUM_PREDICT, 4096)

    print("\n" + "=" * 60)
    print("RESULTS: " + str(passed) + " passed, " + str(failed) + " failed")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_tests())
