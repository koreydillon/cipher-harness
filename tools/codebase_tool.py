"""
Codebase intelligence tool for Cipher — builds an in-memory index of the project
and answers questions about file relationships, imports, and architecture.
No external dependencies needed (uses grep/glob under the hood).
"""
import os
import sys
import json
import subprocess
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tool import Tool, ToolResult


# File extensions to index
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".rb", ".php", ".c", ".cpp", ".h", ".hpp", ".cs", ".swift",
    ".sh", ".bash", ".sql", ".yaml", ".yml", ".toml", ".json",
    ".md", ".txt", ".env", ".cfg", ".ini",
}

# Dirs to skip
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", ".next",
    "dist", "build", ".cache", ".cipher", "target", ".tox",
    "egg-info", ".eggs", ".mypy_cache", ".pytest_cache",
}

MAX_FILE_SIZE = 100_000  # 100KB


class CodebaseTool(Tool):
    is_read_only = True
    is_concurrency_safe = True
    is_destructive = False

    def __init__(self):
        super().__init__()
        self._index = None
        self._cwd = None

    @property
    def name(self): return "codebase"

    @property
    def description(self):
        return (
            "Analyze the codebase structure and relationships. Actions: "
            "'map' — returns a tree of all code files with sizes and purposes. "
            "'imports' — shows import graph (what imports what). "
            "'find_related' — finds files related to a given file (imports, imported-by, similar names). "
            "'summarize' — gives a high-level summary of the project architecture. "
            "'search_semantic' — searches code by concept, not just text (e.g., 'error handling', 'database queries')."
        )

    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["map", "imports", "find_related", "summarize", "search_semantic"],
                    "description": "Action to perform",
                },
                "path": {"type": "string", "description": "File path (for find_related)"},
                "query": {"type": "string", "description": "Search query (for search_semantic)"},
            },
            "required": ["action"],
        }

    def _build_index(self, cwd: str):
        """Build a lightweight index of the codebase."""
        if self._index and self._cwd == cwd:
            return

        self._cwd = cwd
        self._index = {
            "files": {},        # path -> {size, lines, language, imports, exports}
            "imports": defaultdict(set),    # file -> set of imports
            "imported_by": defaultdict(set), # module -> set of files that import it
        }

        for root, dirs, files in os.walk(cwd):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for fname in files:
                fpath = os.path.join(root, fname)
                ext = Path(fname).suffix.lower()

                if ext not in CODE_EXTENSIONS:
                    continue

                rel_path = os.path.relpath(fpath, cwd)
                try:
                    size = os.path.getsize(fpath)
                    if size > MAX_FILE_SIZE:
                        continue

                    with open(fpath, "r", errors="replace") as f:
                        content = f.read()

                    lines = content.count("\n") + 1
                    imports = self._extract_imports(content, ext)
                    exports = self._extract_exports(content, ext)

                    self._index["files"][rel_path] = {
                        "size": size,
                        "lines": lines,
                        "ext": ext,
                        "imports": imports,
                        "exports": exports,
                    }

                    for imp in imports:
                        self._index["imports"][rel_path].add(imp)
                        self._index["imported_by"][imp].add(rel_path)

                except (OSError, UnicodeDecodeError):
                    continue

    def _extract_imports(self, content: str, ext: str) -> list[str]:
        imports = []
        if ext == ".py":
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("import "):
                    mod = line.split()[1].split(".")[0]
                    imports.append(mod)
                elif line.startswith("from "):
                    parts = line.split()
                    if len(parts) >= 2:
                        mod = parts[1].split(".")[0]
                        imports.append(mod)
        elif ext in (".js", ".ts", ".tsx", ".jsx"):
            import re
            for m in re.finditer(r'(?:import|require)\s*\(?["\']([^"\']+)["\']', content):
                imports.append(m.group(1))
        elif ext == ".go":
            import re
            for m in re.finditer(r'"([^"]+)"', content[:2000]):
                imports.append(m.group(1).split("/")[-1])
        return imports

    def _extract_exports(self, content: str, ext: str) -> list[str]:
        exports = []
        if ext == ".py":
            import re
            for m in re.finditer(r'^(?:def|class)\s+(\w+)', content, re.MULTILINE):
                exports.append(m.group(1))
        elif ext in (".js", ".ts", ".tsx", ".jsx"):
            import re
            for m in re.finditer(r'export\s+(?:default\s+)?(?:function|class|const|let|var)\s+(\w+)', content):
                exports.append(m.group(1))
        return exports

    def call(self, input: dict) -> ToolResult:
        action = input["action"]
        cwd = os.getcwd()
        self._build_index(cwd)

        if action == "map":
            return self._do_map()
        elif action == "imports":
            return self._do_imports()
        elif action == "find_related":
            path = input.get("path", "")
            if not path:
                return ToolResult(output="'path' is required for find_related", error=True)
            return self._do_find_related(path)
        elif action == "summarize":
            return self._do_summarize()
        elif action == "search_semantic":
            query = input.get("query", "")
            if not query:
                return ToolResult(output="'query' is required for search_semantic", error=True)
            return self._do_search_semantic(query)
        else:
            return ToolResult(output=f"Unknown action: {action}", error=True)

    def _do_map(self) -> ToolResult:
        if not self._index["files"]:
            return ToolResult(output="No code files found in this directory.")

        lines = ["Codebase Map:", ""]
        by_dir = defaultdict(list)
        for fpath, info in sorted(self._index["files"].items()):
            dir_name = os.path.dirname(fpath) or "."
            by_dir[dir_name].append((fpath, info))

        for dir_name in sorted(by_dir):
            lines.append(f"  {dir_name}/")
            for fpath, info in by_dir[dir_name]:
                fname = os.path.basename(fpath)
                exports_str = ""
                if info["exports"]:
                    top = info["exports"][:5]
                    exports_str = f" — {', '.join(top)}"
                    if len(info["exports"]) > 5:
                        exports_str += f" (+{len(info['exports'])-5} more)"
                lines.append(f"    {fname:30s} {info['lines']:>5} lines{exports_str}")
            lines.append("")

        total_files = len(self._index["files"])
        total_lines = sum(f["lines"] for f in self._index["files"].values())
        lines.append(f"Total: {total_files} files, {total_lines:,} lines")
        return ToolResult(output="\n".join(lines))

    def _do_imports(self) -> ToolResult:
        lines = ["Import Graph:", ""]
        for fpath in sorted(self._index["imports"]):
            imports = sorted(self._index["imports"][fpath])
            if imports:
                lines.append(f"  {fpath}")
                for imp in imports:
                    # Check if it's a local import
                    is_local = any(
                        imp in f or imp.replace("_", "") in f.replace("_", "")
                        for f in self._index["files"]
                    )
                    marker = "→" if is_local else "⇢"
                    lines.append(f"    {marker} {imp}")
                lines.append("")

        return ToolResult(output="\n".join(lines))

    def _do_find_related(self, path: str) -> ToolResult:
        rel = path
        if rel not in self._index["files"]:
            # Try to find a match
            matches = [f for f in self._index["files"] if path in f or os.path.basename(path) in f]
            if matches:
                rel = matches[0]
            else:
                return ToolResult(output=f"File not found in index: {path}")

        info = self._index["files"][rel]
        lines = [f"Related files for: {rel}", ""]

        # What this file imports
        imports = self._index["imports"].get(rel, set())
        if imports:
            lines.append("  Imports:")
            for imp in sorted(imports):
                lines.append(f"    → {imp}")
            lines.append("")

        # What imports this file
        module_name = Path(rel).stem
        imported_by = self._index["imported_by"].get(module_name, set())
        if imported_by:
            lines.append("  Imported by:")
            for f in sorted(imported_by):
                if f != rel:
                    lines.append(f"    ← {f}")
            lines.append("")

        # Files with similar names
        base = Path(rel).stem.lower()
        similar = [
            f for f in self._index["files"]
            if f != rel and (base in f.lower() or f.lower().split("/")[-1].startswith(base[:4]))
        ]
        if similar:
            lines.append("  Similar files:")
            for f in sorted(similar)[:5]:
                lines.append(f"    ~ {f}")

        return ToolResult(output="\n".join(lines))

    def _do_summarize(self) -> ToolResult:
        files = self._index["files"]
        if not files:
            return ToolResult(output="No code files found.")

        # Count by language
        lang_count = defaultdict(int)
        lang_lines = defaultdict(int)
        for info in files.values():
            lang_count[info["ext"]] += 1
            lang_lines[info["ext"]] += info["lines"]

        # Find entry points
        entry_points = []
        for fpath in files:
            fname = os.path.basename(fpath).lower()
            if fname in ("main.py", "app.py", "index.js", "index.ts", "server.py", "manage.py", "cli.py"):
                entry_points.append(fpath)

        # Find config files
        config_files = [
            f for f in files
            if any(c in f.lower() for c in ["config", "settings", ".env", "setup", "package.json", "pyproject", "cargo.toml"])
        ]

        # Find test files
        test_files = [f for f in files if "test" in f.lower() or "spec" in f.lower()]

        # Most imported modules
        top_imported = sorted(
            self._index["imported_by"].items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )[:5]

        lines = ["Project Summary:", ""]

        lines.append("  Languages:")
        for ext in sorted(lang_count, key=lambda e: lang_lines[e], reverse=True):
            lines.append(f"    {ext:8s} {lang_count[ext]:3d} files  {lang_lines[ext]:>6,} lines")

        if entry_points:
            lines.append(f"\n  Entry points: {', '.join(entry_points)}")

        if config_files:
            lines.append(f"  Config files: {', '.join(config_files[:5])}")

        if test_files:
            lines.append(f"  Test files: {len(test_files)}")

        if top_imported:
            lines.append("\n  Most used modules:")
            for mod, users in top_imported:
                lines.append(f"    {mod:20s} imported by {len(users)} files")

        total = len(files)
        total_lines = sum(f["lines"] for f in files.values())
        lines.append(f"\n  Total: {total} files, {total_lines:,} lines")

        return ToolResult(output="\n".join(lines))

    def _do_search_semantic(self, query: str) -> ToolResult:
        """Search code by concept — maps query keywords to code patterns."""
        # Map common concepts to grep patterns
        CONCEPT_MAP = {
            "error handling": [r"try:", r"except\s", r"catch\s*\(", r"\.catch\(", r"raise\s", r"throw\s"],
            "database": [r"SELECT\s", r"INSERT\s", r"UPDATE\s", r"DELETE\s", r"CREATE TABLE", r"\.query\(", r"\.execute\(", r"cursor", r"Session\("],
            "authentication": [r"login", r"logout", r"auth", r"token", r"jwt", r"password", r"session", r"cookie"],
            "api": [r"@app\.(get|post|put|delete|patch)", r"router\.", r"endpoint", r"@route", r"fetch\(", r"requests\.(get|post)"],
            "testing": [r"def test_", r"assert\s", r"expect\(", r"describe\(", r"it\(", r"pytest", r"unittest"],
            "logging": [r"logger\.", r"logging\.", r"console\.log", r"print\(", r"log\.(info|debug|warn|error)"],
            "config": [r"os\.environ", r"getenv", r"\.env", r"config\[", r"settings\.", r"process\.env"],
            "validation": [r"validate", r"validator", r"schema", r"pydantic", r"zod", r"joi"],
            "async": [r"async\s+def", r"await\s", r"asyncio", r"Promise", r"\.then\("],
            "file io": [r"open\(", r"read\(", r"write\(", r"readFile", r"writeFile", r"os\.path"],
            "security": [r"hash", r"encrypt", r"decrypt", r"sanitize", r"escape", r"cors", r"csrf", r"xss"],
        }

        query_lower = query.lower()
        patterns = []

        # Check if query matches a known concept
        for concept, pats in CONCEPT_MAP.items():
            if any(word in query_lower for word in concept.split()):
                patterns.extend(pats)

        # Also use the raw query words as patterns
        for word in query.split():
            if len(word) >= 3:
                patterns.append(re.escape(word) if not any(c in word for c in r".*+?[](){}|\\") else word)

        if not patterns:
            return ToolResult(output=f"Could not map query to search patterns: {query}")

        import re
        results = defaultdict(list)

        for fpath, info in self._index["files"].items():
            full_path = os.path.join(self._cwd, fpath)
            try:
                with open(full_path, "r", errors="replace") as f:
                    content = f.read()

                for i, line in enumerate(content.split("\n"), 1):
                    for pattern in patterns:
                        try:
                            if re.search(pattern, line, re.IGNORECASE):
                                results[fpath].append((i, line.strip()[:100]))
                                break  # one match per line is enough
                        except re.error:
                            continue
            except (OSError, UnicodeDecodeError):
                continue

        if not results:
            return ToolResult(output=f"No results found for: {query}")

        # Sort by number of matches
        sorted_results = sorted(results.items(), key=lambda x: len(x[1]), reverse=True)

        lines = [f"Semantic search: {query}", ""]
        for fpath, matches in sorted_results[:10]:
            lines.append(f"  {fpath} ({len(matches)} matches)")
            for line_no, text in matches[:3]:
                lines.append(f"    L{line_no}: {text}")
            if len(matches) > 3:
                lines.append(f"    ... +{len(matches)-3} more")
            lines.append("")

        total = sum(len(m) for m in results.values())
        lines.append(f"Total: {total} matches in {len(results)} files")
        return ToolResult(output="\n".join(lines))


# Need this for search_semantic
import re
