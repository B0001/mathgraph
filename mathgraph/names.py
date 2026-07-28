"""Mathlib name handling: tokenization, and reconstruction of the
declarations that `@[to_additive]` generates but never writes to source.

Mathlib names are a compressed description of the statement
(`mul_le_mul_of_nonneg_left`), so splitting them into tokens recovers most of
the semantics without any type information. That is the whole reason this
approach works at all.
"""

from __future__ import annotations

import re

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SPLIT = re.compile(r"[._']+")


def split_name(name: str) -> list[str]:
    """`MeasureTheory.integral_add` -> ['measure','theory','integral','add']"""
    out: list[str] = []
    for chunk in _SPLIT.split(name):
        if not chunk:
            continue
        for piece in _CAMEL.split(chunk):
            piece = piece.strip().lower()
            piece = re.sub(r"[^a-z0-9]", "", piece)
            if piece:
                out.append(piece)
    return out


# ---------------------------------------------------------------------------
# to_additive
# ---------------------------------------------------------------------------
# Mathlib's own translation dictionary, abridged to the productive entries.
# Applied to snake_case components and to CamelCase components separately.

_TO_ADDITIVE_SNAKE = {
    "mul": "add", "one": "zero", "inv": "neg", "div": "sub",
    "prod": "sum", "npow": "nsmul", "zpow": "zsmul", "pow": "smul",
    "monoid": "add_monoid", "group": "add_group", "semigroup": "add_semigroup",
    "units": "add_units", "unit": "add_unit", "hom": "hom",
    "smul": "vadd", "action": "vadd_action",
    "multiplicative": "additive", "mul_opposite": "add_opposite",
    "mul_indicator": "indicator", "mul_support": "support",
    "mul_tsupport": "tsupport", "mul_single": "single",
    "finprod": "finsum", "tprod": "tsum", "prodmk": "summk",
    "commute": "add_commute", "semiconj": "add_semiconj",
    "order_of": "add_order_of", "is_of_fin_order": "is_of_fin_add_order",
    "left_cancel": "left_cancel", "right_cancel": "right_cancel",
}

_TO_ADDITIVE_CAMEL = {
    "Mul": "Add", "One": "Zero", "Inv": "Neg", "Div": "Sub",
    "Monoid": "AddMonoid", "Group": "AddGroup", "Semigroup": "AddSemigroup",
    "CommMonoid": "AddCommMonoid", "CommGroup": "AddCommGroup",
    "Units": "AddUnits", "Prod": "Sum", "Pow": "SMul", "SMul": "VAdd",
    "Multiplicative": "Additive", "MulOpposite": "AddOpposite",
    "MonoidHom": "AddMonoidHom", "MulHom": "AddHom",
    "MulEquiv": "AddEquiv", "MonoidWithZero": "AddMonoidWithZero",
    "Submonoid": "AddSubmonoid", "Subgroup": "AddSubgroup",
    "Commute": "AddCommute", "Semiconj": "AddSemiconj",
}

_ATTR_RE = re.compile(r"@\[([^\]]*)\]")
_TO_ADD_RE = re.compile(r"\bto_additive\b\s*(?P<rest>[^,\]]*)")


def _translate_snake(part: str) -> str | None:
    """Translate one dot-component written in snake_case."""
    words = part.split("_")
    out: list[str] = []
    hit = False
    i = 0
    while i < len(words):
        # try two-word keys first (mul_indicator, order_of, ...)
        if i + 1 < len(words):
            pair = f"{words[i]}_{words[i+1]}"
            if pair in _TO_ADDITIVE_SNAKE:
                out.extend(_TO_ADDITIVE_SNAKE[pair].split("_"))
                hit = True
                i += 2
                continue
        w = words[i]
        if w in _TO_ADDITIVE_SNAKE:
            out.extend(_TO_ADDITIVE_SNAKE[w].split("_"))
            hit = True
        else:
            out.append(w)
        i += 1
    return "_".join(out) if hit else None


def _translate_camel(part: str) -> str | None:
    if part in _TO_ADDITIVE_CAMEL:
        return _TO_ADDITIVE_CAMEL[part]
    # compound CamelCase: translate the longest known prefix
    pieces = _CAMEL.split(part)
    out: list[str] = []
    hit = False
    for p in pieces:
        if p in _TO_ADDITIVE_CAMEL:
            out.append(_TO_ADDITIVE_CAMEL[p])
            hit = True
        else:
            out.append(p)
    return "".join(out) if hit else None


def to_additive_name(name: str) -> str | None:
    """Best-effort guess at the additive counterpart of a multiplicative name.

    Returns None when no component is translatable, which means mathlib would
    not have generated an additive version under automatic naming.
    """
    parts = name.split(".")
    out: list[str] = []
    hit = False
    for part in parts:
        if part[:1].isupper():
            t = _translate_camel(part)
        else:
            t = _translate_snake(part)
        if t is not None:
            hit = True
            out.append(t)
        else:
            out.append(part)
    return ".".join(out) if hit else None


def parse_to_additive_attr(attr_line: str) -> tuple[bool, str | None]:
    """Return (has_to_additive, explicit_name_or_None)."""
    for body in _ATTR_RE.findall(attr_line):
        m = _TO_ADD_RE.search(body)
        if not m:
            continue
        rest = m.group("rest").strip()
        rest = re.sub(r'".*?"', "", rest).strip()          # drop docstring arg
        rest = re.sub(r"\(.*?\)", "", rest).strip()        # drop (attr := ...)
        tok = rest.split()[0] if rest.split() else ""
        if tok and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_'.]*", tok) and tok not in {
            "self", "existing", "reorder", "attr", "relabel",
        }:
            return True, tok
        return True, None
    return False, None
