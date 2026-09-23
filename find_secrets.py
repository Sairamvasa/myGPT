import os
import re

# Search for hardcoded secrets
patterns = [
    r'GEMINI_API_KEY\s*=\s*["\'][A-Za-z0-9\-_\.]{20,}["\']',
    r'JWT_SECRET_KEY\s*=\s*["\'][A-Za-z0-9\-_\.]{20,}["\']',
    r'OLLAMA_API_KEY\s*=\s*["\'][A-Za-z0-9\-_\.]{20,}["\']',
    r'API_KEY\s*=\s*["\'][A-Za-z0-9\-_\.]{20,}["\']',
    r'API_KEY\s*:\s*["\'][A-Za-z0-9\-_\.]{20,}["\']',
    r'AUTHORIZATION\s*:\s*["\']Bearer\s+[A-Za-z0-9\-_\.]{20,}["\']',
    r'password\s*=\s*["\'][^"\']{8,}["\']',
    r'secret\s*=\s*["\'][A-Za-z0-9\-_\.]{20,}["\']',
]

excluded_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.venv', 'dist', 'build', '.next', '.kilo'}

for root, dirs, files in os.walk("."):
    # Skip excluded directories
    dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.venv', 'dist', 'build', '.next', '.kilo'}]
    
    for file in files:
        if not file.endswith(('.py', '.ts', '.tsx', '.js', '.jsx', '.json', '.env', '.env.example', '.env.local')):
            continue
        
        filepath = os.path.join(root, file)
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
                for pattern in patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    if matches:
                        for match in matches:
                            rel_path = os.path.relpath(filepath, ".")
                            print(f"FOUND: {rel_path}: {match[:100]}")
        except Exception as e:
            print(f"Error reading {filepath}: {e}")