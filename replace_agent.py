with open('backend/agents/agent.py', 'r') as f:
    content = f.read()

start_marker = '        # 4. Execute Autonomous Tools Based on Intent'
end_marker = '        # 5. Assemble Structured Context Prompt'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1:
    print('ERROR: start marker not found')
    exit(1)
if end_idx == -1:
    print('ERROR: end marker not found')
    exit(1)

new_block = """        # 4. Execute Autonomous Tools Based on Intent
        if action in (ACTION_CODE, ACTION_CODE_EXPLANATION):
            if action == ACTION_CODE:
                tool_results = (
                    "CODE GENERATION\\n"
                    "Tool: code_generation\\n"
                    "Status: success\\n\\n"
                    "Observation:\\n"
                    "Code generation requested. The generated code will be produced by the LLM."
                )
                context = None
            elif action == ACTION_CODE_EXPLANATION:
                if context:
                    tool_results = (
                        "CODE EXPLANATION REQUEST:\\n"
                        "Explain the previously provided code from uploaded documents.\\n"
                        "Requirements:\\n"
                        "- Explain line by line or section by section as requested\\n"
                        "- Reference actual code from the document context\\n"
                        "- Do NOT invent code that isn't in the context\\n"
                        "- If context doesn't contain the answer, say so honestly\\n"
                    )
                else:
                    tool_results = (
                        "CODE EXPLANATION REQUEST:\\n"
                        "Explain code from conversation history.\\n"
                        "Requirements:\\n"
                        "- Reference the actual code from previous messages\\n"
                        "- Explain line by line or section by section as requested\\n"
                        "- Do NOT generate new unrelated code\\n"
                    )
        else:
            outcome = _executor.execute(
                message,
                user_id=user_id,
                chat_id=chat_id,
                project_id=project_id,
            )
            tool_results = outcome.tool_results
            direct_answer = outcome.answer
            action = outcome.final_action or action

            # RAG-specific post-processing
            if action == ACTION_RAG and outcome.steps:
                last_step = outcome.steps[-1]
                if last_step.result and last_step.result.success and last_step.result.output:
                    context = last_step.result.output
                    history = []
                    memories = []
                elif last_step.result and last_step.result.success and not last_step.result.output:
                    context = None
                    action = ACTION_CHAT
                elif not last_step.verified and last_step.error:
                    if tool_results:
                        tool_results += f"\\n\\nVerification: {last_step.error}"

            if outcome.error and not tool_results:
                tool_results = outcome.error

"""

new_content = content[:start_idx] + new_block + content[end_idx:]

with open('backend/agents/agent.py', 'w') as f:
    f.write(new_content)

print('Replacement done')
print(f'Start index: {start_idx}')
print(f'End index: {end_idx}')
print(f'Original block length: {end_idx - start_idx}')
print(f'New block length: {len(new_block)}')