"""
Auto-compact — summarizes conversation history when approaching context limits.
Works with both Anthropic API and local Ollama models.
"""

CONTEXT_WINDOWS = {
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "claude-opus-4-6": 200_000,
    # Local models
    "cipher": 8_192,
}
DEFAULT_LOCAL_WINDOW = 32_768  # Most local models support at least this
RESERVE_TOKENS = 4_000  # Reserve for output + buffer


def estimate_tokens(messages: list[dict]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content) // 4
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total += len(str(block.get("text", "") or block.get("content", ""))) // 4
    return total


def should_compact(messages: list[dict], model: str) -> bool:
    window = CONTEXT_WINDOWS.get(model, DEFAULT_LOCAL_WINDOW)
    usable = window - RESERVE_TOKENS
    estimated = estimate_tokens(messages)
    return estimated > usable * 0.80


def compact_messages(client, messages: list[dict], model: str) -> list[dict]:
    """
    Compact conversation history by summarizing older messages.
    Works with both Anthropic and local clients.
    """
    if len(messages) <= 4:
        return messages

    old_messages = messages[:-4]
    tail = messages[-4:]

    # Serialize the old messages for summarization
    serialized = _serialize_messages(old_messages)

    summary_prompt = (
        "Summarize this conversation history concisely for a coding agent. Include: "
        "what was done, files modified, current task/goal, important decisions. "
        "Be thorough but brief. Output only the summary.\n\n"
        f"Conversation:\n{serialized}"
    )

    try:
        # Try Anthropic-style API first
        import anthropic
        if isinstance(client, anthropic.Anthropic):
            from anthropic.types import TextBlock
            response = client.messages.create(
                model=model,
                max_tokens=2048,
                messages=[{"role": "user", "content": summary_prompt}],
            )
            summary = "(no summary)"
            for b in response.content:
                if isinstance(b, TextBlock):
                    summary = b.text
                    break
        else:
            # Local model — use the client's stream interface
            summary = _compact_local(client, summary_prompt, model)
    except Exception:
        # Last resort: just truncate
        summary = _simple_summary(old_messages)

    compact_msg = {
        "role": "user",
        "content": f"[CONTEXT SUMMARY — conversation was compacted to save memory]\n\n{summary}",
    }
    return [compact_msg] + tail


def _compact_local(client, prompt: str, model: str) -> str:
    """Compact using the local model."""
    try:
        from openai import OpenAI
        from config import cfg
        oai = OpenAI(base_url=cfg.ollama_url, api_key="ollama")
        response = oai.chat.completions.create(
            model=cfg.cipher_model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes conversations concisely."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2048,
            temperature=0.1,
        )
        return response.choices[0].message.content or _simple_summary_from_prompt(prompt)
    except Exception:
        return _simple_summary_from_prompt(prompt)


def _simple_summary(messages: list[dict]) -> str:
    """Fallback: extract key info without an LLM call."""
    files_mentioned = set()
    actions = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use":
                        name = block.get("name", "")
                        inp = block.get("input", {})
                        path = inp.get("path", inp.get("file_path", ""))
                        if path:
                            files_mentioned.add(path)
                        cmd = inp.get("command", "")
                        if cmd:
                            actions.append(f"ran: {cmd[:60]}")
                        elif name in ("write", "edit") and path:
                            actions.append(f"{name}: {path}")

    parts = ["Previous conversation summary:"]
    if files_mentioned:
        parts.append(f"Files touched: {', '.join(sorted(files_mentioned)[:10])}")
    if actions:
        parts.append("Actions taken:")
        for a in actions[-10:]:
            parts.append(f"  - {a}")
    return "\n".join(parts)


def _simple_summary_from_prompt(prompt: str) -> str:
    """Extract what we can from the raw prompt."""
    lines = prompt.split("\n")
    summary_lines = []
    for line in lines:
        if any(kw in line.upper() for kw in ["USER:", "ASSISTANT:", "[TOOL:"]):
            summary_lines.append(line[:120])
    return "\n".join(summary_lines[-20:]) if summary_lines else "Previous conversation context (summarization failed)."


def _serialize_messages(messages: list[dict]) -> str:
    parts = []
    for msg in messages:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        text_parts.append(f"[tool: {block.get('name')}]")
                    elif block.get("type") == "tool_result":
                        text_parts.append(f"[result: {str(block.get('content', ''))[:200]}]")
            content = " ".join(text_parts)
        parts.append(f"{role.upper()}: {content[:500]}")
    return "\n\n".join(parts)
