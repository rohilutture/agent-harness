"""Deterministic checkers. No LLM judge: every task has a verifiable answer."""
from __future__ import annotations

import re
import sqlite3

from agent.memory import NoteStore

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]
_NUM = re.compile(r"-?\$?\d[\d,]*\.?\d*\s?[kKmM]?\b")


def numbers(text: str) -> list[float]:
    out = []
    for m in _NUM.finditer(text):
        tok = m.group(0).replace("$", "").replace(",", "").replace(" ", "")
        mult = 1.0
        if tok[-1] in "kK":
            mult, tok = 1e3, tok[:-1]
        elif tok[-1] in "mM":
            mult, tok = 1e6, tok[:-1]
        try:
            out.append(float(tok.rstrip(".")) * mult)
        except ValueError:
            pass
    return out


def sql_value(db: str, sql: str):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute(sql).fetchone()[0]
    finally:
        con.close()


def check(c: dict, final: str, notes: NoteStore, db: str) -> tuple[bool, str]:
    t = c["type"]
    if t == "numeric":
        exp = c["value"] if "value" in c else sql_value(db, c["sql"])
        tol = c.get("tol", 0.0)
        if "rel_tol" in c:
            tol = max(tol, abs(exp) * c["rel_tol"])
        # K-formatted answers are rounded (e.g. $1,234.5K), so allow the rounding.
        nums = numbers(final)
        ok = any(abs(n - exp) <= max(tol, 1e-9) for n in nums)
        return ok, f"expected {exp} (±{tol}); found {nums[:8]}"
    if t == "contains_sql":
        exp = str(sql_value(db, c["sql"]))
        return exp.lower() in final.lower(), f"expected mention of {exp!r}"
    if t == "month_sql":
        m = MONTHS[int(sql_value(db, c["sql"])) - 1]
        return m in final.lower() or m[:3] in final.lower().split(), f"expected month {m}"
    if t == "regex":
        return bool(re.search(c["pattern"], final, re.I)), f"pattern {c['pattern']!r}"
    if t == "not_contains":
        return c["text"].lower() not in final.lower(), f"must not mention {c['text']!r}"
    if t == "note_absent":
        return c["key"] not in notes.notes, f"note {c['key']!r} must not exist"
    raise ValueError(f"unknown check type {t}")
