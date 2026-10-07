# Contributing to JMGL

Thanks for helping. JMGL is a safety-relevant project, so the bar is: **honest claims, tests
for every behaviour change, and no regressions on the gating suite.**

## Setup

```bash
git clone https://github.com/inkblotmanagement-cmyk/JacksonMoralGovernanceLayer.git
cd JacksonMoralGovernanceLayer
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
(cd web && npm ci)
```

## Checks (the same ones CI runs)

```bash
ruff check src tests
mypy
python -m pytest -m "not heldout and not heldout2"   # must pass
python -m pytest -m heldout; python -m pytest -m heldout2   # reported, not gating
cd web && npm run lint && npm run typecheck && npm test && npm run build
helm lint deploy/helm/jmgl
(cd deploy/terraform/gcp-cloud-run && terraform fmt -check && terraform init -backend=false && terraform validate)
```

## Rules of the road

* **Engine changes** (`signals.py`, `engine.py`, `ensemble.py`, laws): add or update cases in
  `tests/tests.json`; never tune on `tests/heldout2.json` or `tests/fresh_handwritten.json`.
  Report accuracy changes with `eval/run_accuracy.py`, including benign over-flagging.
* **Laws** (`spec/laws.json`): wording changes need sign-off from the project owner. Changing a
  law changes its hash, which is recorded on every audit entry.
* **API changes:** within `/v1` only add fields; never remove or rename. Update
  `src/jmgl/server/schemas.py`, tests in `tests/server/`, the dashboard types in `web/src/api.ts`,
  and `CHANGELOG.md`.
* **No overclaims** in code, docs or commit messages: no "unbreakable", "guaranteed",
  "superintelligence", or accuracy numbers without a reproducible evaluation.
* **Security:** never commit secrets, real keys, `.env` files, or personal data. Report
  vulnerabilities privately (see [SECURITY.md](SECURITY.md)).

## Pull requests

1. Branch from `main`; keep PRs focused.
2. Describe what changed, why, and the test evidence (paste the pytest summary).
3. Update `CHANGELOG.md` under *Unreleased*.
4. CI must be green. A maintainer reviews and merges.

## Releases

Versions follow SemVer and live in `src/jmgl/_version.py` (Python), `web/package.json`
(dashboard) and `deploy/helm/jmgl/Chart.yaml` (chart + appVersion). Tag releases `vX.Y.Z`.

By contributing you agree your contributions are licensed under the MIT License.
