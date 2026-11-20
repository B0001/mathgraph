"""Name-resolved references between the declarations of one Lean project (mathgraph-ydf).

complete.py's pilot matcher linked a body to every declaration whose last name
component equals one of its identifiers; fxh's 50-body hand check found 39.5%
of those links genuine. Here an identifier is resolved the way Lean's
elaborator resolves it, as far as source text allows:

* comments, docstrings and strings are blanked, and a body ends at the next
  column-0 command instead of at the next scanned declaration;
* scopes are tracked as Lean tracks them (`namespace`, every `section` form,
  `mutual`, `end`), and `theorem Foo.bar` opens `Foo` for its own command;
* locals shadow globals: section `variable`s, signature binders and the
  binders of the body (fun, quantifiers, big operators, have/let/obtain,
  intro/rintro/`with` names, match alternatives, set-builder);
* a global is looked up in the enclosing namespaces innermost first, then as
  written, under every `open` in scope (`open X in`, `open X (a)`, `hiding`,
  `renaming`) and every `export` alias; `protected` names need a qualifier
  and `private` ones stay in their file; failing all, the last component is
  dropped (field notation on a constant), as in ResolveName.resolveGlobalName;
* `x.f` on a local whose binder type is `T ...` looks up `T.f`. When the type
  is not written down, and for a bare `.f`, `f` is linked only if exactly one
  declaration of the project ends in `.f` and no Mathlib declaration does.
  A dotted name whose head resolves to nothing global is such a local, since
  all six projects set autoImplicit false.

Mathlib's names count as existing, so a Mathlib name shadows a project
namesake exactly where Lean's lookup reaches it first.

ponytail: no elaboration (no toolchain here matches the projects' Mathlib
pins), so notation, coercions, instances, unfolding and `simp` sets stay
invisible, and a binder scopes over its whole command.
"""

from __future__ import annotations

import collections
import json
import re

# Lean 4 identifier characters (Lean.isLetterLike, isSubScriptAlnum): ASCII
# letters, `_`, Greek but λ Π Σ, Coptic, polytonic Greek, letterlike symbols
# (ℓ, ℝ) and the script/fraktur/double-struck alphabets (𝔓, 𝓘); after the
# first character also digits, `'`, `!`, `?` and subscripts.
_L = ("A-Za-z_α-κμ-ωΑ-ΟΡΤ-Ωϊ-ϻ"
      "ἀ-῾℀-⅏\U0001d49c-\U0001d59f")
_R = _L + "0-9'!?₀-₉ₐ-ₜᵢ-ᵪⱼ"
ATOM = f"[{_L}][{_R}]*"
TOKEN = re.compile(rf"(?P<nl>\n)|(?P<id>[@.]?{ATOM}(?:\.{ATOM})*)|(?P<num>[0-9]+(?:\.[0-9]+)?)"
                   rf"|(?P<sym>=>|:=|<;>|//|\S)")
_SKIP = re.compile(r'/-|--|"')

MODIFIERS = {"private", "protected", "noncomputable", "partial", "unsafe", "nonrec", "scoped",
             "local", "public", "meta"}
DECLS = {"theorem", "lemma", "def", "abbrev", "instance", "structure", "class", "inductive",
         "coinductive", "opaque", "axiom", "alias", "example", "irreducible_def", "conjecture"}
# Column-0 words that continue the command above instead of starting one.
CONTINUE = {"where", "termination_by", "decreasing_by", "deriving", "with", "then", "else", "in",
            "by", "at", "from", "using", "fun", "do", "calc", "show"}
CLOSE = {"(": ")", "{": "}", "[": "]", "⦃": "⦄", "⟨": "⟩"}
QUANT = {"fun", "λ", "∀", "∃", "Π", "Σ", "∑", "∏", "⋃", "⋂", "⨆", "⨅", "∫", "∮", "⨁", "∐"}
REL = {":", "∈", "∉", "⊆", "⊂", "⊇", "⊃", "<", "≤", ">", "≥", "≠", "in", "|", "//", "=", ":="}
INTRO = {"intro", "intros", "rintro", "rename_i", "ext", "funext", "by_contra", "by_contra!",
         "choose", "next", "case", "with"}
# Fields of Lean core types that hypotheses carry (Eq, Iff, And, Or, Exists,
# LE.le, Prod, Subtype): `h.trans`, `h.mp`, `p.fst`. Mathlib's index lacks core.
CORE_FIELDS = {"trans", "symm", "mp", "mpr", "subst", "left", "right", "elim", "inl", "inr", "imp",
               "resolve_left", "resolve_right", "choose", "choose_spec", "fst", "snd", "out", "val",
               "property", "some", "get", "mk", "le", "lt", "ne", "ge", "gt"}
ASSIGN = {"obtain", "have", "haveI", "let", "letI", "set", "replace", "suffices", "by_cases",
          "generalize"}


def strip(src: str) -> str:
    """Blank comments (nested `/- -/`, docstrings, `--`) and string literals,
    keeping every newline so that line numbers survive."""
    out, i, n = [], 0, len(src)
    while i < n:
        m = _SKIP.search(src, i)
        if not m:
            out.append(src[i:])
            break
        j = m.start()
        out.append(src[i:j])
        if m.group() == "/-":
            k, depth = j + 2, 1
            while depth and k < n:
                a, b = src.find("/-", k), src.find("-/", k)
                if b < 0:
                    k = n
                elif 0 <= a < b:
                    depth, k = depth + 1, a + 2
                else:
                    depth, k = depth - 1, b + 2
        elif m.group() == "--":
            k = src.find("\n", j)
            k = n if k < 0 else k
        else:
            k = j + 1
            while k < n and src[k] != '"':
                k += 2 if src[k] == "\\" else 1
            k += 1
        out.append(re.sub(r"[^\n]", " ", src[j:k]))
        i = k
    return "".join(out)


def tokenize(text: str, line0: int = 0) -> list[tuple[str, str, int]]:
    """[(kind, text, line)] with kind nl/id/num/sym; `@[...]` attributes are dropped."""
    out, line, attr = [], line0, 0
    for m in TOKEN.finditer(text):
        kind, t = m.lastgroup, m.group()
        if kind == "nl":
            line += 1
        if attr:                          # inside `@[...]`; -1: the `[` is next
            if t == "[":
                attr = 1 if attr < 0 else attr + 1
            elif t == "]":
                attr -= 1
            if kind != "nl":
                continue
        elif t == "@" and text.startswith("[", m.end()):
            attr = -1
            continue
        out.append((kind, t, line))
    return out


def is_command(line: str) -> bool:
    m = re.match(r"@\[|#|[A-Za-z_]+", line)
    return bool(m) and m.group() not in CONTINUE


def atomic(t: str) -> bool:
    return "." not in t.lstrip("@")


def _close(toks, i, j):
    """Index of the bracket closing toks[i] (or j when it is not closed before j)."""
    depth = 0
    for k in range(i, j):
        t = toks[k][1]
        if t in CLOSE:
            depth += 1
        elif t in CLOSE.values():
            depth -= 1
            if depth == 0:
                return k
    return j


def _end(toks, i, stops, cap=400):
    """First index from i at bracket depth 0 whose text is in `stops` (a
    closing bracket of an enclosing group also ends the region), else None."""
    depth = 0
    for k in range(i, min(len(toks), i + cap)):
        t = toks[k][1]
        if depth == 0 and t in stops:
            return k
        if t in CLOSE:
            depth += 1
        elif t in CLOSE.values():
            if depth == 0:
                return k
            depth -= 1
    return None


def _binders(toks, i, j, out, types):
    """Names bound in toks[i:j]. A bracketed group binds the names before its
    colon (an untyped `{x}` all of them, a `[C x]` none; types[name] = the
    first token after the colon when it is a name); a ⟨..⟩ pattern binds every
    name; the top level binds names until its first relation, after which
    everything is type or term."""
    pending = []
    while i < j:
        kind, t, _ = toks[i]
        if t in CLOSE:
            k = _close(toks, i, j)
            inner = toks[i + 1:k]
            if t == "⟨":
                out.update(x.lstrip("@") for kk, x, _ in inner if kk == "id" and atomic(x))
            else:
                c = _end(inner, 0, {":"})
                head = inner[:len(inner) if c is None else c]
                names = [x.lstrip("@") for kk, x, _ in head if kk == "id" and atomic(x)]
                if c is None and t == "[":
                    names = []
                out.update(names)
                if c is not None and c + 1 < len(inner) and inner[c + 1][0] == "id":
                    types.update((n, inner[c + 1][1].lstrip("@")) for n in names)
            i = k + 1
            continue
        if kind == "id" and atomic(t):
            out.add(t.lstrip("@"))
            pending.append(t.lstrip("@"))
        elif t in REL:
            if t == ":" and i + 1 < j and toks[i + 1][0] == "id":
                types.update((n, toks[i + 1][1].lstrip("@")) for n in pending)
            return
        i += 1


def binders(toks, start=0):
    """(locals, {local: type head}) bound anywhere in toks[start:]."""
    out, types = set(), {}
    for k in range(start, len(toks)):
        kind, t, _ = toks[k]
        if t in QUANT:
            e = _end(toks, k + 1, {",", "=>", "↦"})
            if e is not None:
                _binders(toks, k + 1, e, out, types)
        elif t in INTRO:
            e = _end(toks, k + 1, {"\n", ";", "<;>", "using", "=>", ":=", ":", "at", "|"} - (
                {"|"} if t in ("rintro", "with") else set()))
            e = len(toks) if e is None else e
            out.update(x.lstrip("@") for kk, x, _ in toks[k + 1:e] if kk == "id" and atomic(x))
        elif t in ASSIGN:
            e = _end(toks, k + 1, {":=", ":", "\n", "from", "by", "|"} - ({"|"} if t == "obtain" else set()))
            if e is not None and toks[e][1] == ":" and e + 1 < len(toks) and toks[e + 1][0] == "id":
                for kk, x, _ in toks[k + 1:e]:
                    if kk == "id" and atomic(x):
                        types[x.lstrip("@")] = toks[e + 1][1].lstrip("@")
            for kk, x, _ in toks[k + 1:len(toks) if e is None else e]:
                if kk == "id" and atomic(x):
                    out.add(x.lstrip("@"))
        elif t == "|" and (k == 0 or toks[k - 1][0] == "nl" or toks[k - 1][1] == "fun"):
            e = _end(toks, k + 1, {"=>", "\n"})
            if e is not None and toks[e][1] == "=>":
                out.update(x.lstrip("@") for kk, x, _ in toks[k + 1:e] if kk == "id" and atomic(x))
        elif t == "{":            # set-builder and subtype: {x | p}, {x ∈ s | p}, {x : T // p}
            e = k + 1
            while e < len(toks) and toks[e][0] == "id" and atomic(toks[e][1]):
                e += 1
            if e > k + 1 and e < len(toks) and toks[e][1] in ("|", "∈", "//", ":"):
                out.update(x for _, x, _ in toks[k + 1:e])
    return out, types


class Mathlib:
    """What of Mathlib name resolution needs: its names, protected names,
    namespaces and last components (private declarations are invisible)."""

    def __init__(self, path: str):
        self.names, self.protected = set(), set()
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                d = json.loads(line)
                head = d.get("head", "")
                if head.startswith("private"):
                    continue
                self.names.add(d["name"])
                if head.startswith("protected"):
                    self.protected.add(d["name"])
        self.namespaces = {n.rsplit(".", 1)[0] for n in self.names if "." in n}
        self.namespaces |= {p for ns in list(self.namespaces) for p in _prefixes(ns)}
        self.shorts = {n.rsplit(".", 1)[-1] for n in self.names}


def _prefixes(name: str):
    parts = name.split(".")
    return [".".join(parts[:k]) for k in range(1, len(parts))]


class Scope:
    __slots__ = ("kind", "ns", "opens", "vars", "types")

    def __init__(self, kind, ns=()):
        self.kind, self.ns, self.opens, self.vars, self.types = kind, tuple(ns), [], set(), {}


class OpenSpec:
    """One `open` command, resolved after the whole project is scanned (its
    namespaces may be declared in files scanned later)."""
    __slots__ = ("toks", "ns", "prior", "decls")

    def __init__(self, toks, ns, prior):
        self.toks, self.ns, self.prior, self.decls = toks, ns, prior, []


class Decl:
    __slots__ = ("name", "module", "line", "end", "kind", "private", "protected", "ns", "opens",
                 "locals", "types", "toks", "name_at")


class Project:
    """Every command of one project's Lean files, with the scope it sits in.

    `files` maps module names to paths. `refs(rows)` resolves each indexed
    declaration's command (rows matched by module and line) and returns
    {row name: row names it references}."""

    def __init__(self, files: dict[str, str], mathlib: Mathlib):
        self.ml = mathlib
        self.decls: list[Decl] = []
        self.public: dict[str, list[Decl]] = collections.defaultdict(list)
        self.private: dict[tuple[str, str], list[Decl]] = collections.defaultdict(list)
        self.extra: set[str] = set()      # fields, constructors, unindexed mutual members
        self.alias: dict[str, list[str]] = collections.defaultdict(list)
        self.protected: set[str] = set()
        self.specs: list[OpenSpec] = []
        self.exports = []                 # (tokens, namespace, opens in scope), resolved after the scan
        self.text: dict[str, list[str]] = {}
        for module, path in sorted(files.items()):
            with open(path, encoding="utf-8", errors="replace") as fh:
                raw = fh.read()
            self.text[module] = raw.splitlines()
            self._scan(module, strip(raw).split("\n"))
        names = set(self.public) | {n for n, _ in self.private}
        self.namespaces = {p for n in names | self.extra for p in _prefixes(n)} | self.ml.namespaces
        for o in self.specs:               # creation order: every prior spec is resolved first
            o.decls = self._open(o.toks, o.ns, _flat(o.prior))
        for toks, ns, prior in self.exports:
            self._export(toks, ns, _flat(prior))

    # ---- scanning ---------------------------------------------------------

    def _scan(self, module: str, lines: list[str]) -> None:
        stack, pend_opens, pend_vars, pend_types = [Scope("file")], [], set(), {}
        starts = [i for i, ln in enumerate(lines) if is_command(ln)] + [len(lines)]
        for s, e in zip(starts, starts[1:]):
            while e > s + 1 and not lines[e - 1].strip():
                e -= 1
            toks = tokenize("\n".join(lines[s:e]), s)
            k, mods = _words(toks, 0)
            if k >= len(toks):
                continue                  # attributes only: transparent
            word = toks[k][1]
            in_ = toks[-1][1] == "in"
            ns = tuple(p for sc in stack for p in sc.ns)
            if word == "namespace" and k + 1 < len(toks):
                stack.append(Scope("namespace", toks[k + 1][1].split(".")))
            elif word in ("section", "mutual"):
                stack.append(Scope(word))
                if word == "mutual":
                    self._mutual(module, toks, ns)
            elif word == "end":
                if len(stack) > 1:
                    stack.pop()
            elif word == "open":
                o = OpenSpec(toks[k + 1:len(toks) - in_], ns, [o for sc in stack for o in sc.opens])
                self.specs.append(o)
                (pend_opens if in_ else stack[-1].opens).append(o)
                continue
            elif word == "export" and k + 1 < len(toks):
                self.exports.append((toks[k + 1:], ns, [o for sc in stack for o in sc.opens]))
            elif word in ("variable", "universe"):
                vs, ts = set(), {}
                if word == "universe":
                    vs = {x for kk, x, _ in toks[k + 1:] if kk == "id"}
                else:
                    _binders(toks, k + 1, len(toks) - in_, vs, ts)
                if in_:
                    pend_vars |= vs
                    pend_types.update(ts)
                else:
                    stack[-1].vars |= vs
                    stack[-1].types.update(ts)
                continue
            elif word in ("set_option", "omit", "include") and in_:
                continue                  # `... in` prefixes stay transparent
            elif word in DECLS:
                self._decl(module, toks, k, mods, ns, stack, pend_opens, pend_vars, pend_types, e)
            pend_opens, pend_vars, pend_types = [], set(), {}

    def _decl(self, module, toks, k, mods, ns, stack, pend_opens, pend_vars, pend_types, end):
        word, i, name = toks[k][1], k + 1, None
        if word == "instance" and i < len(toks) and toks[i][1] == "(" and i + 1 < len(toks) \
                and toks[i + 1][1] == "priority":
            i = _close(toks, i, len(toks)) + 1
        if word == "alias" and i < len(toks) and toks[i][1] == "⟨":
            j = _close(toks, i, len(toks))
            for kk, x, _ in toks[i + 1:j]:
                if kk == "id":
                    self.extra.add(".".join(ns + (x,)))
            return
        if word != "example" and i < len(toks) and toks[i][0] == "id" and not toks[i][1].startswith((".", "@")):
            name, i = toks[i][1], i + 1
        d = Decl()
        d.module, d.line, d.end, d.kind = module, toks[k][2] + 1, end, word   # 1-based, end inclusive
        d.private, d.protected = "private" in mods, "protected" in mods
        if name is None:
            d.name, d.ns = None, ns
        elif name.startswith("_root_."):
            d.name, d.ns = name[7:], ns
        else:
            d.name = ".".join(ns + (name,))
            d.ns = tuple(d.name.split(".")[:-1])
        d.opens = [o for sc in stack for o in sc.opens] + pend_opens
        locals_, types = binders(toks, i)
        sig = _end(toks, i, {":", ":=", "|", "where"})
        _binders(toks, i, len(toks) if sig is None else sig, locals_, types)
        d.locals = locals_ | pend_vars | {v for sc in stack for v in sc.vars}
        d.types = {**{a: b for sc in stack for a, b in sc.types.items()}, **pend_types, **types}
        d.toks, d.name_at = toks, (i - 1 if name else None)
        self.decls.append(d)
        if d.name:
            (self.private[(d.name, module)] if d.private else self.public[d.name]).append(d)
            if d.protected:
                self.protected.add(d.name)
            if word in ("structure", "class", "inductive"):
                self._members(d.name, toks, i, word)

    def _members(self, full, toks, i, word):
        """Constructors and fields: `| c` of an inductive, `c ::` and the
        line-leading names after `where` of a structure (plus `mk`)."""
        if word == "inductive" or (i < len(toks) and toks[i][1] == "inductive"):
            self.extra.update(f"{full}.{toks[k + 1][1]}" for k in range(i, len(toks) - 1)
                              if toks[k][1] == "|" and toks[k + 1][0] == "id")
            return
        self.extra.add(f"{full}.mk")
        w = next((k for k in range(i, len(toks)) if toks[k][1] == "where"), None)
        if w is None:
            return
        for k in range(w + 1, len(toks) - 1):
            if toks[k][0] == "nl" and toks[k + 1][0] == "id" and atomic(toks[k + 1][1]):
                j = k + 1
                while j < len(toks) and toks[j][0] == "id" and atomic(toks[j][1]):
                    self.extra.add(f"{full}.{toks[j][1]}")
                    j += 1

    def _mutual(self, module, toks, ns):
        for k, (kind, t, _) in enumerate(toks[:-1]):
            if t in DECLS and toks[k + 1][0] == "id":
                self.extra.add(".".join(ns + (toks[k + 1][1],)))

    def _namespaces(self, name, ns, opens):
        """resolveNamespace: the innermost `ns ++ name` that is a namespace, plus
        `o ++ name` for every simple open o; `name` itself when none is."""
        out = []
        for k in range(len(ns), -1, -1):
            c = ".".join(ns[:k] + (name,))
            if c in self.namespaces:
                out.append(c)
                break
        out += [f"{o[1]}.{name}" for o in opens if o[0] == "all" and f"{o[1]}.{name}" in self.namespaces]
        return out or [name]

    def _open(self, toks, ns, opens):
        if not toks or toks[0][1] in ("scoped", "private"):
            return []
        ids, k = [], 0
        while k < len(toks) and toks[k][0] in ("id", "nl") and toks[k][1] not in ("hiding", "renaming"):
            if toks[k][0] == "id":
                ids.append(toks[k][1])
            k += 1
        rest = [x for kk, x, _ in toks[k:] if kk == "id"]
        out = []
        if k < len(toks) and toks[k][1] == "(" and ids:
            for c in self._namespaces(ids[-1], ns, opens):
                out += [("one", x, f"{c}.{x}") for x in rest]
            ids = ids[:-1]
        elif k < len(toks) and toks[k][1] == "renaming" and ids:
            for c in self._namespaces(ids[-1], ns, opens):
                out += [("one", b, f"{c}.{a}") for a, b in zip(rest[::2], rest[1::2])]
            return out
        hide = frozenset(rest) if k < len(toks) and toks[k][1] == "hiding" else frozenset()
        for x in ids:
            out += [("all", c, hide) for c in self._namespaces(x, ns, opens + out)]
        return out

    def _export(self, toks, ns, opens):
        if len(toks) > 1 and toks[0][0] == "id" and toks[1][1] == "(":
            cands = self._namespaces(toks[0][1], ns, opens)
            for kk, x, _ in toks[2:]:
                if kk == "id":
                    self.alias[".".join(ns + (x,))] += [f"{c}.{x}" for c in cands]

    # ---- resolution -------------------------------------------------------

    def exists(self, name: str, module: str) -> bool:
        return (name in self.public or (name, module) in self.private or name in self.extra
                or name in self.alias or name in self.ml.names)

    def _protected(self, name: str) -> bool:
        return name in self.protected or name in self.ml.protected

    def resolve(self, ident: str, ns: tuple, opens: list, module: str) -> tuple[list[str], int]:
        """(names `ident` can denote, how many of its components they cover),
        after ResolveName.resolveGlobalName without macro scopes: the innermost
        enclosing namespace that has it; else the name as written, under each
        open and as an export alias; else the same for `ident` minus its last
        component, which then is field notation on the result."""
        parts = ident.split(".")
        if parts[0] == "_root_":
            parts, ns = parts[1:], ()
        while parts:
            ident, one = ".".join(parts), len(parts) == 1
            for k in range(len(ns), 0, -1):
                c = ".".join(ns[:k]) + "." + ident
                if self.exists(c, module) and not (one and self._protected(c)):
                    return self._unalias(c), len(parts)
            hits = [ident] if self.exists(ident, module) else []
            for o in opens:
                if o[0] == "all" and ident not in o[2]:
                    c = f"{o[1]}.{ident}"
                    if self.exists(c, module) and not (one and self._protected(c)):
                        hits.append(c)
                elif o[0] == "one" and o[1] == ident:
                    hits.append(o[2])
            if hits:
                return [x for h in dict.fromkeys(hits) for x in self._unalias(h)], len(parts)
            parts = parts[:-1]
        return [], 0

    def _unalias(self, name: str) -> list[str]:
        return self.alias.get(name, [name]) if name not in self.public else [name]

    def _own(self, name: str, module: str) -> bool:
        return (name in self.public or (name, module) in self.private or name in self.extra
                or name in self.alias)

    def _is_namespace(self, head: str, ns: tuple, opens: list) -> bool:
        return any(".".join(ns[:k] + (head,)) in self.namespaces for k in range(len(ns) + 1)) or any(
            o[0] == "all" and f"{o[1]}.{head}" in self.namespaces for o in opens)

    def targets(self, d: Decl) -> set[str]:
        """True names (this project's and Mathlib's) that d's command mentions."""
        out, toks, opens = set(), d.toks, _flat(d.opens)
        seen = {".".join(d.ns[:k]) for k in range(1, len(d.ns) + 1)}   # namespaces it mentions
        fields = []                       # fields on receivers whose type is not written down
        for k, (kind, t, _) in enumerate(toks):
            if kind != "id" or k == d.name_at or (k + 1 < len(toks) and toks[k + 1][1] == ":="):
                continue
            t = t.lstrip("@")
            if t.startswith("."):
                fields += t[1:].split(".")
                continue
            parts = t.split(".")
            if parts[0] in d.locals:
                if len(parts) > 1:
                    hit = self._typed_field(d, opens, parts[0], parts[1])
                    fields += parts[1:] if hit is None else parts[2:]
                    out |= hit or set()
                continue
            comps = parts[1:] if parts[0] == "_root_" else parts
            hits, used = self.resolve(t, d.ns, opens, d.module)
            if not hits:
                if self._is_namespace(comps[0], d.ns, opens):
                    continue              # a global we do not know (Lean core, Batteries)
                used = 1                  # an unbound head is a local: autoImplicit is off
            out.update(hits)
            seen.update(hits)
            fields += comps[used:]
        for v, head in d.types.items():
            if head.split(".")[0] not in d.locals:
                seen.update(self.resolve(head, d.ns, opens, d.module)[0])
        for f in fields:
            out |= self._field(f, seen, d.module)
        out.discard(d.name)
        return out

    def _typed_field(self, d, opens, var, field):
        """`x.f` for a local x whose binder type `T ...` is written down: the
        names `T.f` denotes, or None when T is unknown or has no `f`."""
        head = d.types.get(var)
        if not head or head.split(".")[0] in d.locals:
            return None
        found = [f"{c}.{field}" for c in self.resolve(head, d.ns, opens, d.module)[0] or [head]]
        found = [y for x in found if self.exists(x, d.module) for y in self._unalias(x)]
        return set(found) or None

    def _field(self, f: str, seen: set, module: str) -> set[str]:
        """`e.f` with e's type not written down: `T.f` for the namespaces T the
        command mentions, if all of those are this project's; with none,
        the project's only `*.f` when Mathlib has no `*.f`. Core fields
        (`h.trans`, `h.mp`, `p.1`) never link."""
        if f in CORE_FIELDS:
            return set()
        cands = {f"{t}.{f}" for t in seen if self.exists(f"{t}.{f}", module)}
        if cands:
            if not all(self._own(c, module) for c in cands):
                return set()
            return {y for c in cands for y in self._unalias(c)}
        if f in self.ml.shorts:
            return set()
        own = self._by_short().get(f, ())
        return set(own) if len(own) == 1 else set()

    def _by_short(self):
        if not hasattr(self, "_shorts"):
            self._shorts = collections.defaultdict(set)
            for d in self.decls:
                if d.name:
                    self._shorts[d.name.rsplit(".", 1)[-1]].add(d.name)
        return self._shorts

    # ---- index rows -------------------------------------------------------

    def refs(self, rows: list[dict]) -> dict[str, set[str]]:
        """{row name: row names its command references}, rows matched to
        commands by (module, line); a row with no command here cites nothing."""
        at = {(d.module, d.line): d for d in self.decls}
        row_of = {}                       # true name -> row name
        found = {}
        for r in rows:
            d = at.get((r["module"], r["line"]))
            found[r["name"]] = d
            if d is not None and d.name:
                row_of.setdefault(d.name, r["name"])
        return {n: ({row_of[t] for t in self.targets(d) if t in row_of} - {n}) if d else set()
                for n, d in found.items()}


def _flat(specs):
    return [t for o in specs for t in o.decls]


def _words(toks, i):
    """Skip modifiers from i: (index of the command word, the modifiers)."""
    mods = set()
    while i < len(toks) and toks[i][1] in MODIFIERS:
        mods.add(toks[i][1])
        i += 1
    return i, mods
