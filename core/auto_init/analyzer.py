"""
Project scanner — detects languages, frameworks, and complexity
to inform automatic palace layout generation.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

# Extension → language mapping
_LANG_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".java": "java",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
}

# Marker files → framework
_FRAMEWORK_MARKERS: dict[str, str] = {
    "requirements.txt": "python-pip",
    "pyproject.toml": "python-project",
    "setup.py": "python-setuptools",
    "package.json": "node",
    "tsconfig.json": "typescript",
    "next.config.ts": "nextjs",
    "next.config.js": "nextjs",
    "next.config.mjs": "nextjs",
    "Cargo.toml": "rust-cargo",
    "go.mod": "go-modules",
    "pom.xml": "java-maven",
    "build.gradle": "java-gradle",
    "Gemfile": "ruby-bundler",
    "composer.json": "php-composer",
    "Dockerfile": "docker",
    "docker-compose.yml": "docker-compose",
    "docker-compose.yaml": "docker-compose",
    ".env": "dotenv",
}

_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "env", ".tox", "dist", "build", ".mypy_cache", ".pytest_cache",
    ".next", "target", "bin", "obj",
}


@dataclass
class ProjectProfile:
    """Result of scanning a project directory."""
    root: str
    languages: dict[str, int] = field(default_factory=dict)  # lang → file count
    frameworks: list[str] = field(default_factory=list)
    total_files: int = 0
    complexity: str = "small"  # small | medium | large
    top_level_dirs: list[str] = field(default_factory=list)  # directories at project root


def _detect_top_level_dirs(root: Path) -> list[str]:
    """Return sorted list of top-level directory names (excluding skip dirs)."""
    dirs: list[str] = []
    try:
        for entry in root.iterdir():
            if entry.is_dir() and entry.name not in _SKIP_DIRS and not entry.name.startswith("."):
                dirs.append(entry.name)
    except OSError:
        pass
    return sorted(dirs)


def analyze_project(path: str) -> ProjectProfile:
    """
    Walk *path*, count files per language, detect frameworks,
    and classify project complexity.
    """
    root = Path(path).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")

    profile = ProjectProfile(root=str(root))
    languages: dict[str, int] = {}

    profile.top_level_dirs = _detect_top_level_dirs(root)

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories in-place
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

        for fname in filenames:
            profile.total_files += 1

            # Detect frameworks from marker files
            if fname in _FRAMEWORK_MARKERS:
                fw = _FRAMEWORK_MARKERS[fname]
                if fw not in profile.frameworks:
                    profile.frameworks.append(fw)

            # Count languages
            ext = Path(fname).suffix.lower()
            lang = _LANG_MAP.get(ext)
            if lang:
                languages[lang] = languages.get(lang, 0) + 1

    profile.languages = dict(sorted(languages.items(), key=lambda kv: kv[1], reverse=True))

    # Classify complexity
    code_files = sum(languages.values())
    if code_files > 500:
        profile.complexity = "large"
    elif code_files > 100:
        profile.complexity = "medium"
    else:
        profile.complexity = "small"

    return profile
