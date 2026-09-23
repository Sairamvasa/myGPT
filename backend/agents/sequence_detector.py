"""
Deterministic sequence detector for common numeric sequences.
Detects arithmetic, geometric, square, triangular, and other common patterns.
Returns the next value if a clear pattern is detected with high confidence.
"""

from typing import Optional, List, Tuple
import math


def detect_sequence_pattern(numbers: List[int]) -> Optional[Tuple[str, int]]:
    """
    Detect common numeric sequence patterns and return the next value.
    
    Returns (pattern_name, next_value) if a clear pattern is found with high confidence.
    Returns None if no clear pattern is detected.
    """
    if len(numbers) < 3:
        return None
    
    # Try different pattern detectors in order of specificity
    # Geometric progression (each term multiplied by constant)
    geo_result = _check_geometric(numbers)
    if geo_result is not None:
        return ("geometric", geo_result)
    
    # Arithmetic progression (each term added by constant)
    arith_result = _check_arithmetic(numbers)
    if arith_result is not None:
        return ("arithmetic", arith_result)
    
    # Square numbers (n^2)
    square_result = _check_squares(numbers)
    if square_result is not None:
        return ("squares", square_result)
    
    # Triangular numbers (n*(n+1)/2)
    tri_result = _check_triangular(numbers)
    if tri_result is not None:
        return ("triangular", tri_result)
    
    # Quadratic sequences (an^2 + bn + c)
    quad_result = _check_quadratic(numbers)
    if quad_result is not None:
        return ("quadratic", quad_result)
    
    # Powers of 2 (2^n)
    powers2_result = _check_powers_of_two(numbers)
    if powers2_result is not None:
        return ("powers_of_two", powers2_result)
    
    # Fibonacci-like (each term is sum of previous two)
    fib_result = _check_fibonacci_like(numbers)
    if fib_result is not None:
        return ("fibonacci_like", fib_result)
    
    # Factorial-like (n!)
    fact_result = _check_factorial(numbers)
    if fact_result is not None:
        return ("factorial", fact_result)
    
    return None


def _check_arithmetic(numbers: List[int]) -> Optional[int]:
    """Check for arithmetic progression (constant difference)."""
    if len(numbers) < 3:
        return None
    diff = numbers[1] - numbers[0]
    for i in range(2, len(numbers)):
        if numbers[i] - numbers[i-1] != diff:
            return None
    return numbers[-1] + diff


def _check_geometric(numbers: List[int]) -> Optional[int]:
    """Check for geometric progression (constant ratio)."""
    if len(numbers) < 3:
        return None
    if numbers[0] == 0:
        return None
    if numbers[1] % numbers[0] != 0:
        return None
    ratio = numbers[1] // numbers[0]
    if ratio == 0:
        return None
    for i in range(2, len(numbers)):
        if numbers[i-1] == 0 or numbers[i] % numbers[i-1] != 0:
            return None
        if numbers[i] // numbers[i-1] != ratio:
            return None
    return numbers[-1] * ratio


def _check_squares(numbers: List[int]) -> Optional[int]:
    """Check for perfect squares: n^2."""
    if len(numbers) < 3:
        return None
    for i, num in enumerate(numbers, 1):
        root = int(math.isqrt(num))
        if root * root != num or root != i:
            return None
    return (len(numbers) + 1) ** 2


def _check_triangular(numbers: List[int]) -> Optional[int]:
    """Check for triangular numbers: n*(n+1)/2."""
    if len(numbers) < 3:
        return None
    for i, num in enumerate(numbers, 1):
        expected = i * (i + 1) // 2
        if num != expected:
            return None
    n = len(numbers) + 1
    return n * (n + 1) // 2


def _check_quadratic(numbers: List[int]) -> Optional[int]:
    """Check for quadratic sequence: an^2 + bn + c."""
    if len(numbers) < 4:
        return None
    
    # Use first 3 terms to solve for a, b, c
    # n=1: a + b + c = numbers[0]
    # n=2: 4a + 2b + c = numbers[1]
    # n=3: 9a + 3b + c = numbers[2]
    
    n1, n2, n3 = numbers[0], numbers[1], numbers[2]
    
    # Solve system of equations
    # a + b + c = n1
    # 4a + 2b + c = n2
    # 9a + 3b + c = n3
    
    # Subtract: (4a+2b+c) - (a+b+c) = n2 - n1 => 3a + b = n2 - n1
    # Subtract: (9a+3b+c) - (4a+2b+c) = n3 - n2 => 5a + b = n3 - n2
    
    diff1 = n2 - n1
    diff2 = n3 - n2
    
    # (5a+b) - (3a+b) = diff2 - diff1 => 2a = diff2 - diff1
    a2 = diff2 - diff1
    if a2 % 2 != 0:
        return None
    a = a2 // 2
    
    b = diff1 - 3 * a
    c = n1 - a - b
    
    # Verify against remaining terms
    for i in range(3, len(numbers)):
        n = i + 1
        expected = a * n * n + b * n + c
        if numbers[i] != expected:
            return None
    
    # Next term
    n = len(numbers) + 1
    return a * n * n + b * n + c


def _check_powers_of_two(numbers: List[int]) -> Optional[int]:
    """Check for powers of 2: 2^n."""
    if len(numbers) < 3:
        return None
    for i, num in enumerate(numbers, 1):
        if num != (1 << i):
            return None
    return 1 << len(numbers)


def _check_fibonacci_like(numbers: List[int]) -> Optional[int]:
    """Check for Fibonacci-like sequence (each term = sum of previous two)."""
    if len(numbers) < 3:
        return None
    for i in range(2, len(numbers)):
        if numbers[i] != numbers[i-1] + numbers[i-2]:
            return None
    return numbers[-1] + numbers[-2]


def _check_factorial(numbers: List[int]) -> Optional[int]:
    """Check for factorial sequence: n!"""
    if len(numbers) < 3:
        return None
    for i, num in enumerate(numbers, 1):
        expected = math.factorial(i)
        if num != expected:
            return None
    return math.factorial(len(numbers) + 1)


def extract_sequence_from_message(message: str) -> Optional[List[int]]:
    """
    Extract a sequence of integers from a message like "2, 4, 8, 16, ?"
    Returns list of integers if found, None otherwise.
    """
    import re
    
    # Look for patterns like "2, 4, 8, 16, ?" or "2, 4, 8, 16, ?"
    pattern = r'(\d+(?:\s*,\s*\d+)*)\s*,?\s*\?'
    match = re.search(pattern, message)
    if not match:
        return None
    
    seq_str = match.group(1)
    try:
        numbers = [int(x.strip()) for x in seq_str.split(',')]
        if len(numbers) >= 3:
            return numbers
    except ValueError:
        pass
    return None


def get_sequence_answer(message: str) -> Optional[str]:
    """
    Detect sequence in message and return the deterministic answer if pattern found.
    Returns formatted answer string or None if no pattern detected.
    """
    numbers = extract_sequence_from_message(message)
    if not numbers:
        return None
    
    result = detect_sequence_pattern(numbers)
    if not result:
        return None
    
    pattern_name, next_val = result
    return str(next_val)