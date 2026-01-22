#!/usr/bin/env python3
"""Changeset management for Python SDK - similar to Kotlin's changesets system."""

import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Dict, Optional
import shutil


@dataclass
class Changeset:
    """Represents a changeset file with modules, type, and summary."""
    file: Path
    modules: List[str]  # e.g., ["api-key-stamper", "http", "sdk-types"]
    type: str  # patch | minor | major | beta
    summary: str


class ChangesetManager:
    """Manages changeset operations."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.changeset_dir = root_dir / ".changeset"
        self.applied_dir = self.changeset_dir / "applied"
        self.packages_dir = root_dir / "packages"

    def load_changesets(self, from_dir: Optional[Path] = None) -> List[Changeset]:
        """Load changeset files from .changeset/ or specified directory."""
        target_dir = from_dir or self.changeset_dir
        if not target_dir.exists():
            return []

        files = sorted(
            f for f in target_dir.iterdir()
            if f.is_file() and f.suffix in {".yml", ".yaml", ".md"}
        )

        changesets = []
        for file in files:
            parsed = self._parse_changeset(file)
            changesets.extend(parsed)

        return changesets

    def _parse_changeset(self, file: Path) -> List[Changeset]:
        """Parse a changeset file (YAML or Markdown front-matter)."""
        text = file.read_text()

        # Try YAML array form first
        # type: minor
        # packages: [ api-key-stamper, http ]
        # changelog: |-
        #   summary...
        type_match = re.search(r'(?mi)^\s*type\s*:\s*"?(major|minor|patch|beta)"?\s*$', text)
        array_match = re.search(r'(?ms)^\s*packages\s*:\s*\[(.*?)\]\s*$', text)

        if array_match:
            packages = [
                p.strip().strip('"\'')
                for p in array_match.group(1).split(',')
                if p.strip()
            ]
            if packages:
                bump_type = type_match.group(1).lower() if type_match else "patch"
                summary = self._extract_changelog(text)
                return [Changeset(file, packages, bump_type, summary)]

        # Try YAML mapping form
        # packages:
        #   api-key-stamper: minor
        #   http: patch
        mapping_match = re.search(r'(?ms)^\s*packages\s*:\s*\n(.*?)(^\S|\Z)', text)
        if mapping_match:
            entries = []
            for line in mapping_match.group(1).splitlines():
                entry_match = re.match(r'^\s+(.+?)\s*:\s*(major|minor|patch|beta)\s*$', line)
                if entry_match:
                    entries.append((entry_match.group(1).strip(), entry_match.group(2).strip()))

            if entries:
                summary = self._extract_changelog(text)
                return [
                    Changeset(file, [mod], bump, summary)
                    for mod, bump in entries
                ]

        # Try Markdown front-matter
        # ---
        # type: minor
        # packages:
        #   - api-key-stamper
        #   - http
        # ---
        # body...
        fm_match = re.match(r'(?s)^---\s*(.*?)\s*---\s*(.*)$', text)
        if fm_match:
            front, body = fm_match.groups()

            type_fm = re.search(r'(?mi)^\s*type\s*:\s*"?(major|minor|patch|beta)"?\s*$', front)
            packages_fm = re.findall(r'(?m)^\s*-\s*(.+)\s*$', front)

            if packages_fm:
                bump_type = type_fm.group(1).lower() if type_fm else "patch"
                return [Changeset(file, packages_fm, bump_type, body.strip())]

        return []

    def _extract_changelog(self, text: str) -> str:
        """Extract changelog content from YAML."""
        match = re.search(r'(?ms)^\s*changelog\s*:\s*\|-\s*\n(.*)$', text)
        if not match:
            return ""
        body = match.group(1)
        return '\n'.join(line.removeprefix("  ") for line in body.splitlines()).strip()

    def bump_version(self, version: str, bump: str) -> str:
        """Bump a semantic version string."""
        match = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z\.-]+))?$', version)
        if not match:
            return version

        major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
        pre = match.group(4) or ""

        bump = bump.lower()
        if bump == "major":
            return f"{major + 1}.0.0"
        elif bump == "minor":
            return f"{major}.{minor + 1}.0"
        elif bump == "patch":
            return f"{major}.{minor}.{patch + 1}"
        elif bump == "beta":
            core = f"{major}.{minor}.{patch}"
            if not pre:
                return f"{core}-beta.1"
            parts = pre.split(".")
            if parts[0].lower() == "beta":
                num = int(parts[-1]) + 1 if parts[-1].isdigit() else 1
                base = ".".join(parts[:-1]) if len(parts) > 1 else "beta"
                return f"{core}-{base}.{num}"
            return f"{core}-beta.1"
        return version

    def read_module_version(self, module_name: str) -> Optional[str]:
        """Read version from module's pyproject.toml."""
        module_dir = self.packages_dir / module_name
        pyproject = module_dir / "pyproject.toml"

        if not pyproject.exists():
            return None

        text = pyproject.read_text()
        match = re.search(r'(?m)^\s*version\s*=\s*["\']([^"\']+)["\']', text)
        return match.group(1) if match else None

    def write_module_version(self, module_name: str, new_version: str) -> bool:
        """Write version to module's pyproject.toml."""
        module_dir = self.packages_dir / module_name
        pyproject = module_dir / "pyproject.toml"

        if not pyproject.exists():
            return False

        text = pyproject.read_text()
        pattern = r'(^\s*version\s*=\s*["\'])([^"\']+)(["\'])'

        if re.search(pattern, text, re.MULTILINE):
            updated = re.sub(pattern, rf'\g<1>{new_version}\g<3>', text, flags=re.MULTILINE)
            pyproject.write_text(updated)
            return True

        return False


def cmd_new(manager: ChangesetManager):
    """Interactive wizard to create a new changeset file."""
    print("📝 Create a new changeset\n")

    # Get bump type
    print("Bump type:")
    print("  1) patch  - Bug fixes, minor changes")
    print("  2) minor  - New features (backwards-compatible)")
    print("  3) major  - Breaking changes")
    print("  4) beta   - Pre-release")
    choice = input("\nSelect type [1-4]: ").strip()
    
    type_map = {"1": "patch", "2": "minor", "3": "major", "4": "beta"}
    bump_type = type_map.get(choice, "patch")

    # Get packages
    packages_list = [p.name for p in manager.packages_dir.iterdir() if p.is_dir() and not p.name.startswith('.')]
    print(f"\nAvailable packages: {', '.join(packages_list)}")
    packages_input = input("Packages (comma-separated): ").strip()
    packages = [p.strip() for p in packages_input.split(',') if p.strip()]

    if not packages:
        print("Error: At least one package is required")
        sys.exit(1)

    # Get changelog
    print("\nChangelog message (press Ctrl+D or Ctrl+Z when done):")
    lines = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass
    
    changelog = '\n'.join(lines).strip()
    if not changelog:
        changelog = "No description provided"

    # Generate filename
    name = input("\nChangeset filename (without extension): ").strip()
    if not name:
        name = f"change-{date.today().strftime('%Y%m%d')}"
    
    filepath = manager.changeset_dir / f"{name}.yml"
    if filepath.exists():
        print(f"Error: {filepath} already exists")
        sys.exit(1)

    # Write changeset
    manager.changeset_dir.mkdir(exist_ok=True)
    content = f"""type: {bump_type}
packages: [ {', '.join(packages)} ]
changelog: |-
  {changelog}
"""
    filepath.write_text(content)
    print(f"\n✅ Created {filepath.relative_to(manager.root_dir)}")


def cmd_status(manager: ChangesetManager):
    """Show pending changesets."""
    if not manager.changeset_dir.exists():
        print("No .changeset directory found.")
        return

    changesets = manager.load_changesets()
    if not changesets:
        print("No pending changesets.")
        return

    print("Pending changesets:")
    seen = set()
    for cs in changesets:
        if cs.file not in seen:
            print(f"  - {cs.file.name}")
            seen.add(cs.file)


def cmd_version(manager: ChangesetManager):
    """Apply version bumps from pending changesets."""
    changesets = manager.load_changesets()
    if not changesets:
        print("No pending changesets to apply.")
        return

    # Determine strongest bump per module
    rank = {"patch": 0, "minor": 1, "major": 2, "beta": 3}
    target: Dict[str, str] = {}

    for cs in changesets:
        for module in cs.modules:
            old_bump = target.get(module)
            if old_bump is None or rank[cs.type] > rank[old_bump]:
                target[module] = cs.type

    print("\nApplying version bumps:")
    bumped_modules = []

    for module, bump in target.items():
        current = manager.read_module_version(module)
        if current is None:
            print(f"  - {module}: NO version found (skipped)")
            continue

        next_version = manager.bump_version(current, bump)
        success = manager.write_module_version(module, next_version)

        if success:
            print(f"  - {module}: {current} → {next_version} ({bump})")
            bumped_modules.append(module)

            # Update version.py for http module
            if module == "http":
                version_file = manager.packages_dir / "http" / "src" / "turnkey_http" / "version.py"
                version_file.write_text(
                    f'"""Auto-generated version file. Do not edit manually."""\n\n'
                    f'VERSION = "turnkey/python-sdk@{next_version}"\n'
                )
        else:
            print(f"  - {module}: failed to write version")

    # Move applied changesets to .changeset/applied/
    manager.applied_dir.mkdir(parents=True, exist_ok=True)
    seen = set()
    for cs in changesets:
        if cs.file in seen:
            continue
        seen.add(cs.file)
        dest = manager.applied_dir / cs.file.name
        shutil.move(str(cs.file), str(dest))

    print(f"\nMoved {len(seen)} file(s) to .changeset/applied/")

    # Write bumped modules list
    bumped_list_file = manager.changeset_dir / ".last_bumped_modules"
    bumped_list_file.write_text("\n".join(target.keys()) + "\n")
    print(f"Wrote bumped module list to {bumped_list_file}")


def cmd_changelog(manager: ChangesetManager):
    """Generate CHANGELOG.md entries from applied changesets."""
    if not manager.applied_dir.exists():
        print("No .changeset/applied directory; nothing to write.")
        return

    applied = manager.load_changesets(from_dir=manager.applied_dir)
    if not applied:
        print("No applied changesets found; nothing to write.")
        return

    today = date.today().isoformat()

    # Group by module
    by_module: Dict[str, List[tuple[str, str]]] = {}
    for cs in applied:
        for module in cs.modules:
            if module not in by_module:
                by_module[module] = []
            by_module[module].append((cs.type, cs.summary))

    for module, entries in by_module.items():
        new_version = manager.read_module_version(module) or "UNSPECIFIED"
        changelog = manager.packages_dir / module / "CHANGELOG.md"

        # Build new section
        section_lines = [f"## {new_version} — {today}", ""]

        # Group by bump type
        by_type: Dict[str, List[str]] = {}
        for bump_type, summary in entries:
            if bump_type not in by_type:
                by_type[bump_type] = []
            by_type[bump_type].append(summary)

        for bump_type in ["major", "minor", "patch", "beta"]:
            if bump_type in by_type:
                section_lines.append(f"### {bump_type.capitalize()} Changes")
                for msg in by_type[bump_type]:
                    section_lines.append(f"- {msg}")
                section_lines.append("")

        section = "\n".join(section_lines)

        # Read existing changelog
        if changelog.exists():
            existing = changelog.read_text()
        else:
            existing = "# Changelog\n\n"

        # Insert new section after header
        if existing.startswith("# Changelog"):
            split_idx = existing.find("\n\n")
            if split_idx >= 0:
                header = existing[:split_idx].rstrip()
                rest = existing[split_idx + 2:]
            else:
                header = existing.rstrip()
                rest = ""
        else:
            header = "# Changelog"
            rest = "\n\n" + existing

        updated = f"{header}\n\n{section}\n{rest}"
        changelog.write_text(updated)

        relative = changelog.relative_to(manager.root_dir)
        print(f"Updated {relative}")

    # Clean up applied changesets
    for cs in applied:
        cs.file.unlink(missing_ok=True)

    if not any(manager.applied_dir.iterdir()):
        manager.applied_dir.rmdir()

    print("Cleared applied changesets.")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: manage.py <new|status|version|changelog>")
        sys.exit(1)

    command = sys.argv[1]
    root_dir = Path(__file__).parent.parent
    manager = ChangesetManager(root_dir)

    if command == "new":
        cmd_new(manager)
    elif command == "status":
        cmd_status(manager)
    elif command == "version":
        cmd_version(manager)
    elif command == "changelog":
        cmd_changelog(manager)
    else:
        print(f"Unknown command: {command}")
        print("Usage: manage.py <new|status|version|changelog>")
        sys.exit(1)


if __name__ == "__main__":
    main()
