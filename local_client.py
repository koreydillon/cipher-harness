"""
Local model client for Cipher — wraps Ollama's OpenAI-compatible API
to match Anthropic SDK's interface used in agent.py.

Set LOCAL_MODEL=true and CIPHER_MODEL=cipher to use your fine-tuned model.
"""
import json
import re
import uuid
from dataclasses import dataclass, field

from config import cfg

OLLAMA_BASE_URL = cfg.ollama_url
DEFAULT_LOCAL_MODEL = cfg.cipher_model


@dataclass
class LocalUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class LocalMessage:
    content: list
    usage: LocalUsage = field(default_factory=LocalUsage)
    stop_reason: str = "end_turn"


class LocalStreamContext:
    """Mimics Anthropic's streaming context manager interface with real streaming."""

    def __init__(self, client: "LocalClient", model: str, max_tokens: int,
                 system: str, tools: list, messages: list):
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._system = system
        self._tools = tools
        self._messages = messages
        self._events = []
        self._final_message = None
        self._tool_names = set()

    def __enter__(self):
        # Precompute valid tool names for JSON parsing
        for t in self._tools:
            self._tool_names.add(t.get("name", ""))
        self._generate()
        return self

    def __exit__(self, *args):
        pass

    def __iter__(self):
        return iter(self._events)

    def get_final_message(self) -> LocalMessage:
        return self._final_message

    def _build_openai_messages(self) -> list:
        oai_messages = [{"role": "system", "content": self._system}]
        for msg in self._messages:
            role = msg["role"]
            content = msg["content"]

            if isinstance(content, str):
                oai_messages.append({"role": role, "content": content})
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "text":
                        oai_messages.append({"role": role, "content": block["text"]})
                    elif btype == "tool_use":
                        oai_messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": block["id"],
                                "type": "function",
                                "function": {
                                    "name": block["name"],
                                    "arguments": json.dumps(block["input"]),
                                },
                            }],
                        })
                    elif btype == "tool_result":
                        oai_messages.append({
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": str(block.get("content", "")),
                        })
        return oai_messages

    def _build_openai_tools(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in self._tools
        ]

    def _generate(self):
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package required for local model: pip install openai")

        client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")

        oai_messages = self._build_openai_messages()
        oai_tools = self._build_openai_tools()

        # Try streaming first for real-time output
        try:
            self._generate_streaming(client, oai_messages, oai_tools)
        except Exception:
            # Fall back to non-streaming if streaming fails
            self._generate_sync(client, oai_messages, oai_tools)

    def _generate_streaming(self, client, oai_messages: list, oai_tools: list):
        """Stream response token by token for real-time display."""
        stream = client.chat.completions.create(
            model=self._model,
            messages=oai_messages,
            tools=oai_tools if oai_tools else None,
            max_tokens=self._max_tokens,
            temperature=0.2,
            stream=True,
        )

        full_text = ""
        tool_calls_data = {}  # index -> {id, name, arguments}
        events = []
        content_blocks = []
        text_started = False

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            # Text streaming
            if delta.content:
                if not text_started:
                    events.append(_TextStartEvent())
                    text_started = True
                events.append(_TextDeltaEvent(delta.content))
                full_text += delta.content

            # Tool call streaming
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_data:
                        tool_calls_data[idx] = {
                            "id": tc.id or f"call_{uuid.uuid4().hex[:8]}",
                            "name": tc.function.name if tc.function and tc.function.name else "",
                            "arguments": "",
                        }
                    if tc.function and tc.function.arguments:
                        tool_calls_data[idx]["arguments"] += tc.function.arguments

        # Finalize text
        if text_started:
            events.append(_BlockStopEvent())

        # Get usage from the last chunk if available
        input_tokens = 0
        output_tokens = 0

        # Parse tool calls from text if none came structured
        tool_calls_found = []
        clean_text = full_text

        if tool_calls_data:
            for idx in sorted(tool_calls_data):
                tc = tool_calls_data[idx]
                if tc["name"]:
                    try:
                        args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls_found.append((tc["id"], tc["name"], args, tc["arguments"]))
        elif full_text:
            # Try to extract tool calls from text
            tool_calls_found, clean_text = self._extract_tool_calls_from_text(full_text)

        # Rebuild events if we cleaned the text
        if clean_text != full_text and tool_calls_found:
            events = []
            if clean_text.strip():
                events.append(_TextStartEvent())
                events.append(_TextDeltaEvent(clean_text.strip()))
                events.append(_BlockStopEvent())
                content_blocks.append({"type": "text", "text": clean_text.strip()})
            elif full_text.strip() and not tool_calls_found:
                content_blocks.append({"type": "text", "text": full_text})
        elif full_text:
            content_blocks.append({"type": "text", "text": clean_text if tool_calls_found else full_text})

        # Emit tool call events
        for call_id, name, args, raw_args in tool_calls_found:
            content_blocks.append({
                "type": "tool_use",
                "id": call_id,
                "name": name,
                "input": args,
            })
            events.append(_ToolUseStartEvent(call_id, name))
            events.append(_InputJsonDeltaEvent(raw_args or json.dumps(args)))
            events.append(_BlockStopEvent())

        self._events = events
        self._final_message = LocalMessage(
            content=content_blocks,
            usage=LocalUsage(input_tokens=input_tokens, output_tokens=output_tokens),
            stop_reason="tool_use" if tool_calls_found else "end_turn",
        )

    def _generate_sync(self, client, oai_messages: list, oai_tools: list):
        """Fallback: non-streaming generation."""
        response = client.chat.completions.create(
            model=self._model,
            messages=oai_messages,
            tools=oai_tools if oai_tools else None,
            max_tokens=self._max_tokens,
            temperature=0.2,
            stream=False,
        )

        choice = response.choices[0]
        msg = choice.message

        input_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(response.usage, "completion_tokens", 0) or 0
        usage = LocalUsage(input_tokens=input_tokens, output_tokens=output_tokens)

        content_blocks = []
        events = []

        # Structured tool calls
        tool_calls_found = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls_found.append((tc.id, tc.function.name, args, tc.function.arguments))

        # Parse from text if needed
        text_content = msg.content or ""
        clean_text = text_content

        if not tool_calls_found and text_content:
            tool_calls_found, clean_text = self._extract_tool_calls_from_text(text_content)

        # Text
        if clean_text.strip():
            content_blocks.append({"type": "text", "text": clean_text.strip()})
            events.append(_TextStartEvent())
            events.append(_TextDeltaEvent(clean_text.strip()))
            events.append(_BlockStopEvent())

        # Tool calls
        for call_id, name, args, raw_args in tool_calls_found:
            content_blocks.append({
                "type": "tool_use",
                "id": call_id,
                "name": name,
                "input": args,
            })
            events.append(_ToolUseStartEvent(call_id, name))
            events.append(_InputJsonDeltaEvent(raw_args or json.dumps(args)))
            events.append(_BlockStopEvent())

        self._events = events
        self._final_message = LocalMessage(
            content=content_blocks,
            usage=usage,
            stop_reason="tool_use" if tool_calls_found else "end_turn",
        )

    def _extract_tool_calls_from_text(self, text: str) -> tuple[list, str]:
        """Extract tool calls embedded in text content. Returns (tool_calls, clean_text)."""
        tool_calls = []
        clean_text = text

        patterns = [
            (r'<tool_call>\s*(\{.*?\})\s*</tool_call>', re.DOTALL),
            (r'```(?:json)?\s*(\{"(?:name|function)".*?\})\s*```', re.DOTALL),
            (r'✿FUNCTION✿\s*(\{.*?\})\s*(?:✿|$)', re.DOTALL),
            (r'(\{"name"\s*:\s*"[^"]+"\s*,\s*"(?:arguments|parameters)"\s*:\s*\{.*?\}\s*\})', re.DOTALL),
        ]

        for pattern, flags in patterns:
            matches = re.findall(pattern, text, flags)
            for raw in matches:
                try:
                    parsed = json.loads(raw)
                    name = parsed.get("name") or parsed.get("function", {}).get("name", "")
                    args = parsed.get("arguments") or parsed.get("parameters") or parsed.get("input") or {}
                    if isinstance(args, str):
                        args = json.loads(args)
                    if name and name in self._tool_names:
                        call_id = f"call_{uuid.uuid4().hex[:8]}"
                        tool_calls.append((call_id, name, args, json.dumps(args)))
                except (json.JSONDecodeError, AttributeError, KeyError):
                    continue

        # Strip tool call JSON from text
        if tool_calls:
            for pattern, flags in patterns:
                clean_text = re.sub(pattern, '', clean_text, flags=flags)
            clean_text = clean_text.strip()

        return tool_calls, clean_text


# ── Fake event classes to match Anthropic stream event interface ───────────────

class _TextStartEvent:
    type = "content_block_start"
    class content_block:
        type = "text"

class _TextDeltaEvent:
    type = "content_block_delta"
    def __init__(self, text):
        self.delta = type("d", (), {"type": "text_delta", "text": text})()

class _ToolUseStartEvent:
    type = "content_block_start"
    def __init__(self, id, name):
        self.content_block = type("cb", (), {"type": "tool_use", "id": id, "name": name})()

class _InputJsonDeltaEvent:
    type = "content_block_delta"
    def __init__(self, partial_json):
        self.delta = type("d", (), {"type": "input_json_delta", "partial_json": partial_json})()

class _BlockStopEvent:
    type = "content_block_stop"


class LocalClient:
    """Drop-in replacement for anthropic.Anthropic() when using local model."""

    def __init__(self, model: str = DEFAULT_LOCAL_MODEL):
        self._model = model
        self.messages = self

    def stream(self, model: str, max_tokens: int, system: str,
               tools: list, messages: list) -> LocalStreamContext:
        return LocalStreamContext(
            client=self,
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )


def get_client(api_key: str | None = None):
    """
    Return the right client based on environment:
      LOCAL_MODEL=true  → LocalClient (Ollama)
      default           → anthropic.Anthropic
    """
    if cfg.local_model:
        model = cfg.cipher_model
        print(f"\033[90m[cipher] using local model: {model} @ {cfg.ollama_url}\033[0m")
        return LocalClient(model=model)

    import anthropic
    return anthropic.Anthropic(api_key=api_key or cfg.anthropic_api_key)
