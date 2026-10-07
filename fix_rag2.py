"""Fix the indentation damage in rag.py caused by the earlier fix script."""
with open('backend/rag.py', 'r') as f:
    lines = f.readlines()

# Find 'def process_text_file' - it should be at module level (0 indent)
# but it's currently at 4 indent (inside _process_pdf_project)
process_text_file_idx = None
for i, line in enumerate(lines):
    if line.strip() == 'def process_text_file(file_path, user_id, source_filename=None, project_id=None):':
        process_text_file_idx = i
        break

if process_text_file_idx is None:
    print("Could not find process_text_file")
    exit(1)

print(f"Found process_text_file at line {process_text_file_idx + 1}, indent level: {len(lines[process_text_file_idx]) - len(lines[process_text_file_idx].lstrip())}")

# Dedent all lines from process_text_file onwards by 4 spaces
for i in range(process_text_file_idx, len(lines)):
    line = lines[i]
    if line.strip():  # non-blank line
        if line.startswith('    '):
            lines[i] = line[4:]
        # If it doesn't start with 4 spaces, leave it as-is

# Also add a return 0 after the 'if documents:' block in _process_pdf_project
# Find 'return len(documents)' that's inside the 'if documents:' block
# and add '    return 0\n' after it if there's no else clause
return_idx = None
for i in range(process_text_file_idx - 1, process_text_file_idx - 10, -1):
    if 'return len(documents)' in lines[i]:
        return_idx = i
        break

if return_idx is not None:
    # Check if there's already a return 0 or else clause
    # Insert return 0 after the 'if documents:' block
    # The return len(documents) is at 8 spaces (inside if documents:)
    # We need to add '    return 0\n' at 4 spaces (inside _process_pdf_project but outside if documents:)
    # Actually, looking at the structure, process_text_file is at 4 spaces which is inside _process_pdf_project
    # After dedenting, process_text_file will be at 0 spaces
    # So we need to add 'return 0\n' at 4 spaces (inside _process_pdf_project)
    pass

# Write the file
with open('backend/rag.py', 'w') as f:
    f.writelines(lines)

print("Fixed indentation of process_text_file and subsequent functions")

# Verify the functions are now at module level
with open('backend/rag.py', 'r') as f:
    content = f.read()

import re
funcs = re.findall(r'^def (\w+)', content, re.MULTILINE)
print('Functions in rag.py:', funcs)
