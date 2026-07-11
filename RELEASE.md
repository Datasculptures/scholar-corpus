# Release process

This project publishes to PyPI from a clean, green tree. Uploads require your own
PyPI / TestPyPI API tokens; the steps below are the exact commands to run — no
step here uploads anything on your behalf.

## Pre-release checklist

- [ ] Working tree clean, on `main`, pulled up to date.
- [ ] Gate is green: `ruff check . && mypy && pytest` (85% line/branch floor).
- [ ] `pyproject.toml` `version` bumped and `CHANGELOG.md` updated with the new
      version and date; the `Unreleased` section moved down.
- [ ] Name still available (first publish only): the upload will be rejected if
      `scholar-corpus` is taken, so no separate check is strictly required, but
      you can confirm at <https://pypi.org/project/scholar-corpus/>.
- [ ] Tag prepared: `git tag -a v$(VERSION) -m "v$(VERSION)"` (push after PyPI).

## 1. Build the distributions

```bash
python -m pip install --upgrade build twine
rm -rf dist
python -m build            # writes dist/*.whl and dist/*.tar.gz
python -m twine check dist/*
```

`twine check` must report `PASSED` for both artifacts (this validates the
long-description rendering that PyPI will use).

## 2. Verify the built artifacts

Confirm bundled package data is present in the built wheel (never assume it):

```bash
python - <<'PY'
import glob, zipfile
names = zipfile.ZipFile(sorted(glob.glob("dist/*.whl"))[-1]).namelist()
assert any(n.endswith("scholar_corpus/py.typed") for n in names), "py.typed missing from wheel"
print("wheel OK:", len(names), "entries")
PY
```

Smoke-test the wheel in a throwaway virtualenv, using the console script (not the
source tree), so you exercise exactly what a user installs:

```bash
python -m venv /tmp/sc-smoke
/tmp/sc-smoke/bin/pip install "dist/scholar_corpus-$(VERSION)-py3-none-any.whl[parquet]"
/tmp/sc-smoke/bin/scholar-corpus --version
/tmp/sc-smoke/bin/scholar-corpus build --snapshot <small.json> --categories cs.LG \
  --enrichment openalex --enrichment-snapshot <small-oa.json> --coverage-gate 0.5 \
  --output /tmp/sc-smoke-out
/tmp/sc-smoke/bin/scholar-corpus verify /tmp/sc-smoke-out    # must exit 0
```

## 3. TestPyPI dry run

Upload to TestPyPI first and install from there into a clean environment:

```bash
python -m twine upload --repository testpypi dist/*
# then, in a fresh venv:
python -m venv /tmp/sc-testpypi
/tmp/sc-testpypi/bin/pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  "scholar-corpus[parquet]"
/tmp/sc-testpypi/bin/scholar-corpus --version
/tmp/sc-testpypi/bin/scholar-corpus verify <a-corpus-you-built>   # must exit 0
```

The `--extra-index-url` lets `pyarrow` resolve from real PyPI while
`scholar-corpus` comes from TestPyPI. Confirm the project page renders the README
and metadata correctly at <https://test.pypi.org/project/scholar-corpus/>.

## 4. Publish to PyPI

Only after the TestPyPI install and `verify` succeed:

```bash
python -m twine upload dist/*
git push origin main
git push origin v$(VERSION)
```

## 5. Post-release

- [ ] Confirm <https://pypi.org/project/scholar-corpus/> renders correctly.
- [ ] `pip install scholar-corpus` in a clean venv; run `scholar-corpus info`.
- [ ] Open a GitHub release from the tag, pasting the CHANGELOG section.

## Authentication

Store tokens in `~/.pypirc` or pass them via `TWINE_USERNAME=__token__` and
`TWINE_PASSWORD=<token>`. Never commit tokens.
