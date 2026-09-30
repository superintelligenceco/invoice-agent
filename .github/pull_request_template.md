## Summary

<!-- What does this change and why? Link the issue it fixes, for example "Fixes #12". -->

## Checklist

- [ ] `ruff check .`, `ruff format --check .`, `mypy`, and `pytest` pass locally.
- [ ] `invoice-agent eval` still reports 100% decision accuracy, or the PR explains the change.
- [ ] New matching rules or extractor changes have tests that run offline.
- [ ] If the generator changed, `invoice-agent generate-dataset dataset` was rerun and the diff is committed.
- [ ] `README.md` and `CHANGELOG.md` are updated if behavior changed.
- [ ] The PR title follows [Conventional Commits](https://www.conventionalcommits.org/).
