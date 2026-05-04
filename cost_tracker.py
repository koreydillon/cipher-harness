from compact import CONTEXT_WINDOWS, estimate_tokens

PRICING = {
    "claude-sonnet-4-6":        {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80,  "output": 4.00},
    "claude-opus-4-6":           {"input": 15.00, "output": 75.00},
}


class CostTracker:
    def __init__(self, model: str):
        self.model = model
        self.input_tokens = 0
        self.output_tokens = 0

    def add_usage(self, input_tokens: int, output_tokens: int):
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    def session_cost(self) -> float:
        pricing = PRICING.get(self.model, {"input": 3.00, "output": 15.00})
        return (
            self.input_tokens / 1_000_000 * pricing["input"]
            + self.output_tokens / 1_000_000 * pricing["output"]
        )

    def format_status(self) -> str:
        cost = self.session_cost()
        total_tok = self.input_tokens + self.output_tokens
        if total_tok >= 1000:
            tok_str = f"{total_tok / 1000:.1f}k"
        else:
            tok_str = str(total_tok)
        return f"${cost:.3f} | {tok_str} tok"

    def context_pct(self, messages: list[dict], model: str) -> float:
        window = CONTEXT_WINDOWS.get(model, 200_000)
        estimated = estimate_tokens(messages)
        return min(estimated / window, 1.0)
