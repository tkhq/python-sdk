# Changelog

## 0.1.1 — 2026-10-20

### Patch Changes
- Require Python 3.10 or newer. The generated client already needed it: `import turnkey_http` failed on Python 3.9 with a TypeError, while the package metadata still claimed 3.8. pip now refuses to install on older interpreters instead of installing a package that cannot be imported.

## 0.1.0 — 2026-03-09

### Minor Changes
- Initial release

