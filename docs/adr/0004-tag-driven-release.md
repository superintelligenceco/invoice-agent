# 0004: One tag-driven release path

- Status: accepted
- Date: 2026-09-30

## Context

The project first had a release-please workflow and, later, a Ship workflow that builds
executables and images. Two release paths created tags and releases independently and could race
or disagree.

## Decision

Pushing a `v*` tag is the only way to release. The Ship workflow builds the wheel, sdist,
executables, and image; smoke-tests each on a real invoice; signs, attests, and attaches SBOMs;
publishes to PyPI; and creates the GitHub Release with the CHANGELOG section as notes.
release-please was removed.

## Consequences

- A release is reproducible from one commit and one workflow run.
- The version in `pyproject.toml` and the CHANGELOG are updated by hand before tagging.
- A failed run can be re-run for the same tag; uploads use `--clobber` and PyPI skips existing
  files.
