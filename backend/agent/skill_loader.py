"""Skill Loader — reads SKILL.md files and prepares context for the agent.

Skills follow the Agent Skills specification (agentskills.io):
  skills/{skill-name}/SKILL.md

Each SKILL.md contains:
  - YAML frontmatter (name, description)
  - Markdown body with domain knowledge and instructions

The loader reads the assigned skills and returns their combined content,
which is appended to the agent's system prompt before the ReAct loop starts.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("mastro.skill_loader")


def load_skills(skill_names: list[str], skills_dir: Path) -> str:
    """Load and concatenate skill contents for the given skill names.

    Returns a formatted string ready to be injected into the system prompt.
    Empty string if no skills are found.
    """
    if not skill_names:
        return ""

    sections = []
    for name in skill_names:
        skill_path = skills_dir / name / "SKILL.md"
        if not skill_path.exists():
            logger.warning("Skill '%s' not found at %s", name, skill_path)
            continue
        try:
            content = skill_path.read_text(encoding="utf-8")
            # Strip YAML frontmatter if present (between --- delimiters)
            body = _strip_frontmatter(content)
            if body.strip():
                sections.append(f"## Skill: {name}\n\n{body.strip()}")
        except Exception as exc:
            logger.warning("Failed to read skill '%s': %s", name, exc)

    if not sections:
        return ""

    header = (
        "---\n"
        "The following domain knowledge and instructions are provided as SKILLS. "
        "Use them to guide your reasoning and actions.\n"
        "---\n\n"
    )
    return header + "\n\n---\n\n".join(sections)


def list_skills(skills_dir: Path) -> list[dict]:
    """Return metadata for all available skills."""
    result = []
    if not skills_dir.exists():
        return result
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        meta = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        result.append({
            "name": skill_dir.name,
            "description": meta.get("description", ""),
            "has_content": True,
        })
    return result


def get_skill_content(skill_name: str, skills_dir: Path) -> str | None:
    """Return raw SKILL.md content for a named skill, or None if missing."""
    path = skills_dir / skill_name / "SKILL.md"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def save_skill(skill_name: str, content: str, skills_dir: Path) -> None:
    """Write or overwrite a skill's SKILL.md."""
    skill_dir = skills_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def delete_skill(skill_name: str, skills_dir: Path) -> bool:
    """Delete a skill directory. Returns False if not found."""
    import shutil
    skill_dir = skills_dir / skill_name
    if not skill_dir.exists():
        return False
    shutil.rmtree(skill_dir)
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter (--- ... ---) from markdown text."""
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return text
    lines = stripped.split("\n")
    end = -1
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end = i
            break
    if end == -1:
        return text
    return "\n".join(lines[end + 1:])


def _parse_frontmatter(text: str) -> dict:
    """Extract simple key: value pairs from YAML frontmatter."""
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return {}
    lines = stripped.split("\n")
    end = -1
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end = i
            break
    if end == -1:
        return {}
    meta: dict = {}
    for line in lines[1:end]:
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta
