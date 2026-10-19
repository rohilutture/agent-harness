"""Two kinds of memory, because they solve different problems.

1. Long-term memory: structured notes the agent writes and searches with tools
   (write_note / search_notes). Survives across sessions, so "remember that I
   prefer EUR" in session 1 can change the answer in session 2. Retrieval is
   just-in-time: the agent searches when it needs something, instead of every
   note being stuffed into the prompt.

2. Working-context management for long tasks. When the transcript nears the
   token budget:
     a. observation masking: old tool outputs (usually the bulk of the tokens) are
        replaced by a short stub; recent ones stay verbatim
     b. compaction: if still over budget, older turns are summarized into one
        message and dropped. The cut never separates an assistant tool call from
        its tool result, which providers reject as malformed.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path


class NoteStore:
    def __init__(self, path: Path | None = None):
        self.path = path
        self.notes: dict[str, dict] = {}
        if path and Path(path).exists():
            self.notes = json.loads(Path(path).read_text(encoding="utf-8"))

    def _save(self):
        if self.path:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            Path(self.path).write_text(json.dumps(self.notes, indent=2), encoding="utf-8")

    def write(self, key: str, content: str) -> str:
        key = re.sub(r"[^a-z0-9_\-]+", "_", key.lower()).strip("_")[:60] or "note"
        self.notes[key] = {"content": content[:2000], "updated": time.time()}
        self._save()
        return f"saved note '{key}'"

    def search(self, query: str, k: int = 5) -> str:
        terms = set(re.findall(r"\w+", query.lower()))
        scored = []
        for key, n in self.notes.items():
            words = set(re.findall(r"\w+", (key + " " + n["content"]).lower()))
            s = len(terms & words)
            if s or not terms:
                scored.append((s, key, n["content"]))
        scored.sort(key=lambda x: -x[0])
        return "\n".join(f"- {k}: {c}" for _, k, c in scored[:k]) or "no notes found"


def estimate_tokens(messages: list[dict]) -> int:
    """~4 chars/token. Good enough for a budget trigger; exact counts come from the API."""
    n = 0
    for m in messages:
        n += len(m.get("content") or "") // 4 + 4
        for c in m.get("tool_calls") or []:
            n += len(json.dumps(c.arguments)) // 4 + 8
    return n


class ContextManager:
    def __init__(self, budget_tokens: int = 12_000, keep_recent_tools: int = 3,
                 keep_last_messages: int = 6, summarizer=None):
        self.budget = budget_tokens
        self.keep_tools = keep_recent_tools
        self.keep_last = keep_last_messages
        self.summarizer = summarizer  # callable(list[dict]) -> str, or None for heuristic
        self.maskings = 0
        self.compactions = 0

    def fit(self, messages: list[dict]) -> list[dict]:
        if estimate_tokens(messages) <= self.budget:
            return messages
        messages = self._mask(messages)
        if estimate_tokens(messages) <= self.budget:
            return messages
        return self._compact(messages)

    def _mask(self, messages):
        tool_idx = [i for i, m in enumerate(messages) if m["role"] == "tool"]
        old = tool_idx[:-self.keep_tools] if self.keep_tools else tool_idx
        out = []
        for i, m in enumerate(messages):
            if i in old and not m["content"].startswith("[elided"):
                m = {**m, "content": f"[elided {len(m['content'])} chars of {m['name']} output; "
                                     f"starts: {m['content'][:120]!r}]"}
                self.maskings += 1
            out.append(m)
        return out

    def _safe_cut(self, messages, want: int) -> int:
        """Earliest index >= want that starts a clean turn (assistant or user, never a
        tool result that would be orphaned from its call)."""
        for i in range(want, len(messages)):
            if messages[i]["role"] in {"assistant", "user"}:
                return i
        return len(messages)

    def _compact(self, messages):
        # Always keep: system prompt(s) and the original task (first user message).
        head_end = next(i for i, m in enumerate(messages) if m["role"] == "user") + 1
        cut = self._safe_cut(messages, max(head_end, len(messages) - self.keep_last))
        middle = messages[head_end:cut]
        if not middle:
            return messages
        summary = self.summarizer(middle) if self.summarizer else self._heuristic(middle)
        self.compactions += 1
        note = {"role": "user", "content": "[Context compacted. Summary of earlier steps:]\n" + summary}
        return messages[:head_end] + [note] + messages[cut:]

    @staticmethod
    def _heuristic(middle: list[dict]) -> str:
        lines = []
        for m in middle:
            if m["role"] == "assistant":
                for c in m.get("tool_calls") or []:
                    lines.append(f"- called {c.name}({json.dumps(c.arguments)[:150]})")
                if m.get("content"):
                    lines.append(f"- thought: {m['content'][:200]}")
            elif m["role"] == "tool":
                lines.append(f"  -> {m['content'][:200]}")
            elif m["role"] == "user" and m["content"].startswith("[Context compacted"):
                lines.append(m["content"][:600])
        return "\n".join(lines)


def llm_summarizer(model):
    """Use the agent's own model to write the compaction summary."""
    def summarize(middle):
        transcript = ContextManager._heuristic(middle)
        turn = model([{"role": "system", "content": "Summarize agent progress for yourself. Keep every "
                       "number, name, ID and partial result you will need. Bullet points, <200 words."},
                      {"role": "user", "content": transcript}], [])
        return turn.text or transcript
    return summarize
