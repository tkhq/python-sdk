# Changesets

Declare version bumps and changelog entries for packages.

## Usage

### 1. Create a changeset

```bash
make changeset
```

Runs an interactive wizard to create a new changeset file. Or create manually:

```yaml
type: minor  # patch | minor | major | beta
packages: [ http, sdk-types ]
changelog: |-
  Your changelog message here
```

### 2. Apply version bumps

```bash
make changeset-version
```

Updates `pyproject.toml` versions and moves changesets to `.changeset/applied/`.

### 3. Generate changelogs

```bash
make changeset-changelog
```

Updates `CHANGELOG.md` files and cleans up applied changesets.

### 4. Check status

```bash
make changeset-status
```

## Format Options

**YAML array:**
```yaml
type: minor
packages: [ http, sdk-types ]
changelog: |-
  Message
```

**YAML mapping (different bumps per package):**
```yaml
packages:
  http: minor
  sdk-types: patch
changelog: |-
  Message
```