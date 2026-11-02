"""Source-presentation interventions: what the model sees when it reads its own code.

Conditions
  orig       the source exactly as evolved
  fmt        black formatting only
  norm       black + canonical alpha-renaming of function locals (v0, v1, ...)
  neutral    black + neutral renaming: random lowercase names whose length matches
             the originals (token-length control for `norm`)
  nocomment  comments removed, nothing else (separate factor: comments can carry
             learned information, so this is not folded into `norm`)

Safety argument (not a general proof of equivalence)
  Renaming touches only names that are local to a function: bound inside it, not
  parameters, not declared global/nonlocal. Functions using anything that can
  observe or capture names are left untouched and reported as unsupported:
  nested def/lambda/class, global/nonlocal, imports inside the function, match
  statements, walrus inside comprehensions, f-string `{x=}`, and calls to
  locals/vars/eval/exec/globals/dir/compile/__import__/getattr/setattr/delattr/hasattr.
  New names are fresh: they collide with no identifier, attribute, keyword or
  builtin anywhere in the module. String literals, including runtime prompt text,
  are never changed.

Mechanical checks on every transformation
  * the result parses;
  * for renaming: applying the same mapping to the original AST gives exactly the
    AST of the result (so the change is an alpha-renaming and nothing else);
  * for formatting and comment removal: the AST is unchanged.
  The test suite adds differential runs (identical prompts and outputs under a
  deterministic mock). Remaining known gap: exception messages that quote a local
  name (e.g. UnboundLocalError) would change text.

Introspection: agents cannot read files (policy + sandbox). The only way an agent
sees its own source is api.source(), which returns the presented version.
"""

from __future__ import annotations

import ast
import builtins
import hashlib
import io
import keyword
import random
import re
import tokenize
from dataclasses import asdict, dataclass, field

CONDITIONS = ("orig", "fmt", "norm", "neutral", "nocomment")
UNSAFE_CALLS = {"locals", "vars", "eval", "exec", "globals", "dir", "compile", "__import__",
                "getattr", "setattr", "delattr", "hasattr"}
FSTRING_DEBUG = re.compile(r"=\s*(![rsa])?\s*(:[^{}]*)?\}")


@dataclass
class Report:
    condition: str
    verified: bool = True
    error: str | None = None
    total_locals: int = 0
    renamed: int = 0
    unsupported: dict = field(default_factory=dict)   # function name -> reason
    tokens_before: int = 0
    tokens_after: int = 0

    @property
    def coverage(self) -> float:
        return self.renamed / self.total_locals if self.total_locals else 1.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["coverage"] = round(self.coverage, 3)
        return d


# --------------------------------------------------------------------------
# Token proxy (offline). Real runs can swap in a provider's count_tokens.
# --------------------------------------------------------------------------

def token_count(src: str) -> int:
    n = 0
    for piece in re.findall(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", src):
        n += max(1, -(-len(piece) // 4)) if piece[0].isalnum() or piece[0] == "_" else 1
    return n


# --------------------------------------------------------------------------
# Scope analysis
# --------------------------------------------------------------------------

def _functions(tree: ast.Module) -> list[ast.FunctionDef]:
    """Top-level functions and methods of top-level classes."""
    out = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out.append(node)
        elif isinstance(node, ast.ClassDef):
            out += [n for n in node.body if isinstance(n, ast.FunctionDef)]
    return out


def _bound_names(fn: ast.FunctionDef) -> list[str]:
    """Names bound in fn's body, in order of first appearance."""
    seen: dict[str, None] = {}

    def add(name):
        seen.setdefault(name, None)

    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            add(node.name)
    params = {a.arg for a in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs}
    for a in (fn.args.vararg, fn.args.kwarg):
        if a:
            params.add(a.arg)
    return [n for n in seen if n not in params]


def unsupported_reason(fn: ast.FunctionDef, src: str) -> str | None:
    for node in ast.walk(fn):
        if node is not fn and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            return "nested function/lambda/class"
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            return "global/nonlocal"
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return "import inside function"
        if isinstance(node, ast.Match):
            return "match statement"
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            if any(isinstance(n, ast.NamedExpr) for n in ast.walk(node)):
                return "walrus inside comprehension"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in UNSAFE_CALLS:
            return f"call to {node.func.id}()"
        if isinstance(node, ast.JoinedStr):
            seg = ast.get_source_segment(src, node) or ""
            if FSTRING_DEBUG.search(seg.replace("}}", "")):
                return "f-string self-documenting expression"
    if getattr(fn, "type_params", None):
        return "type parameters"
    return None


def all_identifiers(tree: ast.Module) -> set[str]:
    names = set(dir(builtins)) | set(keyword.kwlist) | set(keyword.softkwlist)
    for node in ast.walk(tree):
        for attr in ("id", "attr", "arg", "name", "asname", "module"):
            v = getattr(node, attr, None)
            if isinstance(v, str):
                names.update(v.split("."))
    return names


# --------------------------------------------------------------------------
# Renaming
# --------------------------------------------------------------------------

class _Renamer(ast.NodeTransformer):
    def __init__(self, maps: dict[tuple, dict[str, str]]):
        self.maps, self.current = maps, None

    def visit_FunctionDef(self, node):
        prev = self.current
        self.current = self.maps.get(_key(node), prev if prev else None)
        self.generic_visit(node)
        self.current = prev
        return node

    def visit_Name(self, node):
        if self.current and node.id in self.current:
            node.id = self.current[node.id]
        return node

    def visit_ExceptHandler(self, node):
        if self.current and node.name in self.current:
            node.name = self.current[node.name]
        self.generic_visit(node)
        return node


def _key(fn) -> tuple:
    return (fn.lineno, fn.col_offset, fn.name)


def _dump(tree) -> str:
    return ast.dump(tree, include_attributes=False)


def rename(src: str, plan: dict[str, dict[str, str]] | callable, condition: str = "rename"):
    """Alpha-rename function locals.

    ``plan`` maps function qualname -> {old: new}, or is a callable
    (qualname, locals, taken) -> {old: new}. Unsupported functions are skipped
    and reported. Returns (new_src, Report). On any verification failure the
    original source is returned with verified=False.
    """
    rep = Report(condition, tokens_before=token_count(src))
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        rep.verified, rep.error = False, f"syntax error: {e.msg}"
        rep.tokens_after = rep.tokens_before
        return src, rep
    taken = all_identifiers(tree)
    lines = src.splitlines(keepends=True)
    edits: list[tuple[int, int, int, str]] = []   # (line, start_byte, end_byte, new)
    maps: dict[tuple, dict[str, str]] = {}
    for fn in _functions(tree):
        names = _bound_names(fn)
        rep.total_locals += len(names)
        reason = unsupported_reason(fn, src)
        if reason:
            rep.unsupported[fn.name] = reason
            continue
        mapping = plan(fn.name, names, taken) if callable(plan) else dict(plan.get(fn.name, {}))
        mapping = {o: n for o, n in mapping.items() if o in names and o != n}
        if not mapping:
            continue
        new_names = list(mapping.values())
        if len(set(new_names)) != len(new_names) or any(n in taken for n in new_names) \
                or any(not n.isidentifier() or keyword.iskeyword(n) for n in new_names):
            rep.unsupported[fn.name] = "name collision in plan"
            continue
        # No need to reserve new names module-wide: locals of different functions
        # live in separate scopes, and none collides with an existing identifier.
        maps[_key(fn)] = mapping
        rep.renamed += len(mapping)
        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and node.id in mapping:
                edits.append((node.lineno, node.col_offset, node.end_col_offset, mapping[node.id]))
            elif isinstance(node, ast.ExceptHandler) and node.name in mapping:
                line = lines[node.lineno - 1].encode()
                m = re.compile(rb"\bas\s+(" + re.escape(node.name.encode()) + rb")\b").search(line, node.col_offset)
                if not m:
                    rep.verified, rep.error = False, "could not locate except-as name"
                    return src, rep
                edits.append((node.lineno, m.start(1), m.end(1), mapping[node.name]))
    by_line: dict[int, list] = {}
    for ln, a, b, new in edits:
        by_line.setdefault(ln, []).append((a, b, new))
    for ln, items in by_line.items():
        raw = lines[ln - 1].encode()
        for a, b, new in sorted(set(items), reverse=True):
            raw = raw[:a] + new.encode() + raw[b:]
        lines[ln - 1] = raw.decode()
    out = "".join(lines)
    # Verify: AST(out) == rename(AST(src)).
    try:
        expected = _Renamer(maps).visit(ast.parse(src))
        ok = _dump(ast.parse(out)) == _dump(expected)
    except SyntaxError:
        ok = False
    if not ok:
        rep.verified, rep.error = False, "renamed AST does not match expected alpha-renaming"
        rep.renamed = 0
        out = src
    rep.tokens_after = token_count(out)
    return out, rep


def canonical_plan(qualname, names, taken):
    mapping, i = {}, 0
    for n in names:
        while f"v{i}" in taken:
            i += 1
        mapping[n] = f"v{i}"
        i += 1
    return mapping


SYLLABLES = ["ka", "zo", "ri", "mu", "te", "lo", "vi", "na", "pe", "su", "do", "ga", "fi", "ru", "xe", "bo"]


def neutral_plan_factory(seed: str):
    def plan(qualname, names, taken):
        rng = random.Random(f"{seed}:{qualname}")
        mapping, used = {}, set(taken)
        for n in names:
            for _ in range(200):
                target = max(2, len(n))
                word = ""
                while len(word) < target:
                    word += rng.choice(SYLLABLES)
                word = word[:target]
                if word not in used and word.isidentifier() and not keyword.iskeyword(word):
                    break
            mapping[n] = word
            used.add(word)
        return mapping
    return plan


# --------------------------------------------------------------------------
# Formatting and comments
# --------------------------------------------------------------------------

def black_format(src: str) -> tuple[str, Report]:
    rep = Report("fmt", tokens_before=token_count(src))
    try:
        import black
        out = black.format_str(src, mode=black.Mode(line_length=88))
        if _dump(ast.parse(out)) != _dump(ast.parse(src)):
            raise ValueError("AST changed")
    except Exception as e:  # noqa: BLE001
        rep.verified, rep.error, out = False, f"format failed: {type(e).__name__}: {e}"[:200], src
    rep.tokens_after = token_count(out)
    return out, rep


def strip_comments(src: str) -> tuple[str, Report]:
    rep = Report("nocomment", tokens_before=token_count(src))
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
        lines = src.splitlines(keepends=True)
        for tok in reversed([t for t in toks if t.type == tokenize.COMMENT]):
            (ln, col), (_, end) = tok.start, tok.end
            line = lines[ln - 1]
            before = line[:col].rstrip()
            lines[ln - 1] = (before + line[end:]).rstrip() + "\n" if before else ""
        out = "".join(lines)
        if _dump(ast.parse(out)) != _dump(ast.parse(src)):
            raise ValueError("AST changed")
    except Exception as e:  # noqa: BLE001
        rep.verified, rep.error, out = False, f"comment removal failed: {e}"[:200], src
    rep.tokens_after = token_count(out)
    return out, rep


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def present(src: str, condition: str) -> tuple[str, Report]:
    if condition == "orig":
        n = token_count(src)
        return src, Report("orig", tokens_before=n, tokens_after=n)
    if condition == "nocomment":
        return strip_comments(src)
    formatted, frep = black_format(src)
    if condition == "fmt" or not frep.verified:
        if condition != "fmt":
            frep.condition = condition
        return formatted, frep
    seed = hashlib.sha256(src.encode()).hexdigest()[:12]
    plan = canonical_plan if condition == "norm" else neutral_plan_factory(seed)
    out, rep = rename(formatted, plan, condition)
    rep.tokens_before = token_count(src)
    return out, rep


# --------------------------------------------------------------------------
# Style metrics (used by the analysis and by the mock models)
# --------------------------------------------------------------------------

def style_of(name: str) -> str:
    if re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)+", name):
        return "snake"
    if re.fullmatch(r"[a-z][a-z0-9]*([A-Z][a-z0-9]*)+", name):
        return "camel"
    return "neutral"


def local_names(src: str) -> list[str]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    return [n for fn in _functions(tree) for n in _bound_names(fn)]


def style_mix(src: str) -> dict[str, float]:
    names = local_names(src)
    if not names:
        return {"snake": 0.0, "camel": 0.0, "neutral": 1.0, "n": 0}
    counts = {"snake": 0, "camel": 0, "neutral": 0}
    for n in names:
        counts[style_of(n)] += 1
    return {k: v / len(names) for k, v in counts.items()} | {"n": len(names)}
