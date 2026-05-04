import os
import subprocess


def scan_project(cwd: str) -> str:
    lines = ["## Project Context"]

    project_type, type_detail = _detect_type(cwd)
    if project_type:
        lines.append(f"- Type: {project_type} ({type_detail})")

    git_info = _detect_git(cwd)
    if git_info:
        lines.append(f"- Git: yes (branch: {git_info})")
    else:
        lines.append("- Git: no")

    stack = _detect_stack(cwd, project_type)
    if stack:
        lines.append(f"- Stack: {stack}")

    return "\n".join(lines)


def _detect_type(cwd: str) -> tuple[str, str]:
    if os.path.exists(os.path.join(cwd, "pyproject.toml")):
        name = _read_pyproject_name(cwd)
        detail = f"pyproject.toml{f' — {name}' if name else ''}"
        return "Python project", detail
    if os.path.exists(os.path.join(cwd, "setup.py")):
        return "Python project", "setup.py"
    if os.path.exists(os.path.join(cwd, "requirements.txt")):
        return "Python project", "requirements.txt"
    if os.path.exists(os.path.join(cwd, "package.json")):
        info = _read_package_json(cwd)
        return "Node project", info
    if os.path.exists(os.path.join(cwd, "Cargo.toml")):
        return "Rust project", "Cargo.toml"
    if os.path.exists(os.path.join(cwd, "go.mod")):
        return "Go project", "go.mod"
    return "", ""


def _detect_git(cwd: str) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def _detect_stack(cwd: str, project_type: str) -> str:
    if "Python" in project_type:
        deps = _read_requirements(cwd)
        if deps:
            return ", ".join(deps[:5]) + " (from requirements.txt)"
    if "Node" in project_type:
        deps = _read_node_deps(cwd)
        if deps:
            return ", ".join(deps[:5]) + " (from package.json)"
    extras = []
    if os.path.exists(os.path.join(cwd, "Dockerfile")):
        extras.append("Docker")
    return ", ".join(extras) if extras else ""


def _read_requirements(cwd: str) -> list[str]:
    path = os.path.join(cwd, "requirements.txt")
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            lines = f.readlines()
        deps = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                name = line.split(">=")[0].split("==")[0].split("[")[0].strip()
                if name:
                    deps.append(name)
        return deps
    except Exception:
        return []


def _read_pyproject_name(cwd: str) -> str:
    path = os.path.join(cwd, "pyproject.toml")
    try:
        with open(path) as f:
            for line in f:
                if line.strip().startswith("name"):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def _read_package_json(cwd: str) -> str:
    path = os.path.join(cwd, "package.json")
    try:
        import json
        with open(path) as f:
            data = json.load(f)
        name = data.get("name", "")
        desc = data.get("description", "")
        if name and desc:
            return f"{name} — {desc[:60]}"
        return name or "package.json"
    except Exception:
        return "package.json"


def _read_node_deps(cwd: str) -> list[str]:
    path = os.path.join(cwd, "package.json")
    try:
        import json
        with open(path) as f:
            data = json.load(f)
        deps = list(data.get("dependencies", {}).keys())
        deps += list(data.get("devDependencies", {}).keys())
        return deps
    except Exception:
        return []
