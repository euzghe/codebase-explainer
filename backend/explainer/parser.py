"""Tree-sitter-based source parser for Python and JS/TS.

Extracts:
    - functions, classes, methods (Symbol nodes)
    - import edges between Files
    - call edges between Symbols (best-effort, name-based)

This is intentionally a *lightweight* parser. For an MVP we don't try to
resolve every call site to a fully qualified target — we record local calls
by name and let the Q&A layer query Neo4j for candidates. Good enough to
answer "where is X defined / called from" for the vast majority of cases.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from tree_sitter_language_pack import get_parser


@dataclass
class Symbol:
    name: str
    qname: str          # qualified within file, e.g. "ClassName.method" or "func"
    kind: str           # "function" | "class" | "method"
    file_path: str
    line_start: int
    line_end: int
    snippet: str        # first ~20 lines of the body
    calls: list[str] = field(default_factory=list)


@dataclass
class FileParse:
    path: str
    language: str
    bytes_: int
    symbols: list[Symbol]
    imports: list[str]  # raw import targets (modules, paths, packages)


_LANG_BY_EXT = {
    "py": "python",
    "ts": "typescript",
    "tsx": "tsx",
    "js": "javascript",
    "jsx": "javascript",
    "mjs": "javascript",
}


def language_for(path: Path) -> str | None:
    return _LANG_BY_EXT.get(path.suffix.lstrip(".").lower())


def _text(node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _snippet(src: bytes, node, max_lines: int = 20) -> str:
    text = _text(node, src)
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... ({len(text.splitlines()) - max_lines} more lines)"]
    return "\n".join(lines)


def _collect_calls(node, src: bytes, lang: str) -> list[str]:
    """Walk the subtree, collect call target identifiers."""
    out: list[str] = []
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type == "call" or n.type == "call_expression":
            # First child is usually the callee (identifier or attribute/member access)
            callee = n.child_by_field_name("function") or n.child_by_field_name("callee")
            if callee is not None:
                name = _text(callee, src).split(".")[-1].strip()
                if name and name.isidentifier():
                    out.append(name)
        for c in n.children:
            stack.append(c)
    # Dedupe while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for n in out:
        if n in seen:
            continue
        seen.add(n)
        uniq.append(n)
    return uniq[:50]


def _walk_python(tree, src: bytes, rel_path: str) -> tuple[list[Symbol], list[str]]:
    symbols: list[Symbol] = []
    imports: list[str] = []

    def visit(node, class_ctx: str | None) -> None:
        for child in node.children:
            t = child.type
            if t == "import_statement" or t == "import_from_statement":
                # Collect imported module path
                module = child.child_by_field_name("module_name")
                if module is not None:
                    imports.append(_text(module, src).strip())
                else:
                    # Fallback: whole text after the keyword
                    text = _text(child, src)
                    for tok in text.replace(",", " ").split():
                        if tok not in {"import", "from", "as"}:
                            imports.append(tok)
                            break
            elif t == "class_definition":
                name_node = child.child_by_field_name("name")
                if name_node is None:
                    continue
                name = _text(name_node, src)
                symbols.append(
                    Symbol(
                        name=name,
                        qname=name,
                        kind="class",
                        file_path=rel_path,
                        line_start=child.start_point[0] + 1,
                        line_end=child.end_point[0] + 1,
                        snippet=_snippet(src, child),
                        calls=_collect_calls(child, src, "python"),
                    )
                )
                body = child.child_by_field_name("body")
                if body is not None:
                    visit(body, class_ctx=name)
            elif t == "function_definition":
                name_node = child.child_by_field_name("name")
                if name_node is None:
                    continue
                name = _text(name_node, src)
                qname = f"{class_ctx}.{name}" if class_ctx else name
                kind = "method" if class_ctx else "function"
                symbols.append(
                    Symbol(
                        name=name,
                        qname=qname,
                        kind=kind,
                        file_path=rel_path,
                        line_start=child.start_point[0] + 1,
                        line_end=child.end_point[0] + 1,
                        snippet=_snippet(src, child),
                        calls=_collect_calls(child, src, "python"),
                    )
                )
            else:
                visit(child, class_ctx=class_ctx)

    visit(tree.root_node, class_ctx=None)
    return symbols, imports


def _walk_js_like(tree, src: bytes, rel_path: str) -> tuple[list[Symbol], list[str]]:
    symbols: list[Symbol] = []
    imports: list[str] = []

    def visit(node, class_ctx: str | None) -> None:
        for child in node.children:
            t = child.type
            if t in ("import_statement", "import_declaration"):
                source = child.child_by_field_name("source")
                if source is not None:
                    raw = _text(source, src).strip().strip('"').strip("'")
                    imports.append(raw)
                else:
                    # Fallback: scan for string children
                    for c in child.children:
                        if c.type == "string":
                            imports.append(_text(c, src).strip().strip('"').strip("'"))
                            break
            elif t == "class_declaration":
                name_node = child.child_by_field_name("name")
                if name_node is None:
                    continue
                name = _text(name_node, src)
                symbols.append(
                    Symbol(
                        name=name,
                        qname=name,
                        kind="class",
                        file_path=rel_path,
                        line_start=child.start_point[0] + 1,
                        line_end=child.end_point[0] + 1,
                        snippet=_snippet(src, child),
                        calls=_collect_calls(child, src, "js"),
                    )
                )
                body = child.child_by_field_name("body")
                if body is not None:
                    visit(body, class_ctx=name)
            elif t in ("function_declaration", "method_definition"):
                name_node = child.child_by_field_name("name")
                if name_node is None:
                    continue
                name = _text(name_node, src)
                qname = f"{class_ctx}.{name}" if class_ctx else name
                kind = "method" if t == "method_definition" else "function"
                symbols.append(
                    Symbol(
                        name=name,
                        qname=qname,
                        kind=kind,
                        file_path=rel_path,
                        line_start=child.start_point[0] + 1,
                        line_end=child.end_point[0] + 1,
                        snippet=_snippet(src, child),
                        calls=_collect_calls(child, src, "js"),
                    )
                )
            elif t == "lexical_declaration":
                # const foo = () => {...} / const foo = function () {...}
                for declarator in child.children:
                    if declarator.type != "variable_declarator":
                        continue
                    name_node = declarator.child_by_field_name("name")
                    value = declarator.child_by_field_name("value")
                    if name_node is None or value is None:
                        continue
                    if value.type in ("arrow_function", "function_expression", "function"):
                        name = _text(name_node, src)
                        symbols.append(
                            Symbol(
                                name=name,
                                qname=name,
                                kind="function",
                                file_path=rel_path,
                                line_start=child.start_point[0] + 1,
                                line_end=child.end_point[0] + 1,
                                snippet=_snippet(src, child),
                                calls=_collect_calls(value, src, "js"),
                            )
                        )
                visit(child, class_ctx=class_ctx)
            else:
                visit(child, class_ctx=class_ctx)

    visit(tree.root_node, class_ctx=None)
    return symbols, imports


def parse_file(path: Path, repo_root: Path) -> FileParse | None:
    lang = language_for(path)
    if lang is None:
        return None
    try:
        src = path.read_bytes()
    except OSError:
        return None
    rel = str(path.relative_to(repo_root))

    parser = get_parser(lang)
    tree = parser.parse(src)

    if lang == "python":
        symbols, imports = _walk_python(tree, src, rel)
    else:
        symbols, imports = _walk_js_like(tree, src, rel)

    return FileParse(
        path=rel,
        language=lang,
        bytes_=len(src),
        symbols=symbols,
        imports=imports,
    )


def parse_repo(root: Path, files: Iterable[Path]) -> list[FileParse]:
    out: list[FileParse] = []
    for f in files:
        parsed = parse_file(f, root)
        if parsed is not None:
            out.append(parsed)
    return out
