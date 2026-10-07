"""Fix _process_pdf_project in rag.py - line-based approach"""
with open('backend/rag.py', 'r') as f:
    lines = f.readlines()

# Find _process_pdf_project
func_start_idx = None
for i, line in enumerate(lines):
    if 'def _process_pdf_project' in line:
        func_start_idx = i
        break

if func_start_idx is None:
    print("Could not find _process_pdf_project")
    exit(1)

print(f"Found _process_pdf_project at line {func_start_idx + 1}")

# Find 'if not documents:' within this function
not_documents_idx = None
for i in range(func_start_idx, len(lines)):
    if 'if not documents:' in lines[i]:
        not_documents_idx = i
        break

if not_documents_idx is None:
    print("Could not find 'if not documents:' in _process_pdf_project")
    exit(1)

print(f"Found 'if not documents:' at line {not_documents_idx + 1}")

# Find the end of the raise ValueError block (the closing ')')
raise_end_idx = None
for i in range(not_documents_idx, len(lines)):
    if lines[i].strip() == ')':
        raise_end_idx = i
        break

print(f"Found raise ValueError end at line {raise_end_idx + 1}")
print(f"Line content: {repr(lines[raise_end_idx])}")

# Find the line 'if key not in project_vector_stores:'
key_idx = None
for i in range(raise_end_idx + 1, len(lines)):
    if 'if key not in project_vector_stores:' in lines[i]:
        key_idx = i
        break

print(f"Found 'if key not in project_vector_stores:' at line {key_idx + 1}")

# Now replace lines from not_documents_idx to the line before key_idx
# with '    if documents:\n' and indent the FAISS block by 4 more spaces
new_lines = ['    if documents:\n']

# The lines from key_idx onwards need to be indented by 4 more spaces
# (they're currently at 4 spaces inside the function, need to be at 8 inside the if block)
# Actually, the existing lines after key_idx are at 4-space indent (function body level)
# We need them at 8-space indent (inside the if documents: block)
for i in range(key_idx, len(lines)):
    line = lines[i]
    if line.strip():  # non-blank line
        lines[i] = '    ' + line
    # blank lines stay as-is

# Replace the block from not_documents_idx to key_idx-1 with '    if documents:\n'
lines[not_documents_idx:key_idx] = ['    if documents:\n']

with open('backend/rag.py', 'w') as f:
    f.writelines(lines)

print("Fixed _process_pdf_project")
