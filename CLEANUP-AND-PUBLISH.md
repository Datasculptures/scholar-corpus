# Cleanup → GitHub → PyPI checklist

Specific, ordered actions to take `scholar-corpus` from its current folder to a
published package. Commands assume Windows; run the shell ones in **PowerShell**
from the project root unless noted. `RELEASE.md` has the deeper detail for the
PyPI steps — this list is the end-to-end path.

Current state: v0.4.0, gate green (97 tests, 96.7% coverage, ruff + mypy strict
clean), distributions build and `twine check` clean, wheel smoke-tested.

---

## A. Clean up the working copy

- [ ] **A1. Delete the broken `.git` folder.** A half-initialised `.git` (with a
      stuck `config.lock`) is present and must be removed before a fresh init:
      ```powershell
      Remove-Item -Recurse -Force ".git"
      ```
      If that fails on the lock file, close any editor/Git tool touching the
      folder and retry, or delete `.git` via File Explorer (enable "show hidden").

- [ ] **A2. Move the project out of OneDrive.** The sync layer caused file-read
      races during development, and reproducible corpus artifacts should never
      live in a sync folder. Copy the repo to a non-synced path and work there:
      ```powershell
      robocopy "$env:OneDrive\Sean\AI\scholar-corpus" "C:\dev\scholar-corpus" /E /XD .git __pycache__ .ruff_cache .mypy_cache .pytest_cache *.egg-info dist build
      cd C:\dev\scholar-corpus
      ```
      (Skip if you deliberately want it under OneDrive — but then expect sync
      churn.)

- [ ] **A3. Remove local caches / build leftovers** (all gitignored, but start
      clean):
      ```powershell
      Remove-Item -Recurse -Force .ruff_cache,.mypy_cache,.pytest_cache,dist,build -ErrorAction SilentlyContinue
      Get-ChildItem -Recurse -Directory -Filter *.egg-info | Remove-Item -Recurse -Force
      ```

- [ ] **A4. Decide the release version.** Currently `0.4.0` (feature-complete
      across build phases 1–4). If you want to signal a stable first release,
      bump to `1.0.0`: edit `version` in `pyproject.toml`, and add a matching
      section to `CHANGELOG.md` (move `Unreleased` down). Otherwise ship `0.4.0`.

- [ ] **A5. Fix project URLs and author metadata in `pyproject.toml`.** They
      currently point at `github.com/datasculptures/scholar-corpus`. Set them to
      the account you will actually publish under, and add issue/changelog URLs:
      ```toml
      authors = [{ name = "Sean ...", email = "pfn.sean@gmail.com" }]

      [project.urls]
      Homepage = "https://github.com/<OWNER>/scholar-corpus"
      Source = "https://github.com/<OWNER>/scholar-corpus"
      Issues = "https://github.com/<OWNER>/scholar-corpus/issues"
      Changelog = "https://github.com/<OWNER>/scholar-corpus/blob/main/CHANGELOG.md"
      ```
      `<OWNER>` must match the GitHub repo you create in step B2.

---

## B. Local environment + green gate (native)

- [ ] **B1. Use Python 3.11+.** The package requires `>=3.11`. Confirm and create
      a virtualenv:
      ```powershell
      py -3.11 --version        # install 3.11+ if this fails
      py -3.11 -m venv .venv
      .\.venv\Scripts\Activate.ps1
      python -m pip install -U pip
      pip install -e ".[dev]"
      ```

- [ ] **B2. Run the full gate natively and confirm green on your Python:**
      ```powershell
      ruff check .
      mypy
      pytest
      ```
      All three must pass (pytest enforces the 85% line/branch floor). This is the
      first time the suite runs on 3.11 rather than the 3.10 sandbox, so treat a
      green result here as the real sign-off.

---

## C. GitHub

- [ ] **C1. Initialise git on the `main` branch and make the first commit:**
      ```powershell
      git init -b main
      git config user.name  "Your Name"
      git config user.email "pfn.sean@gmail.com"
      git add -A
      git status                      # sanity-check: no .db/.parquet/.log/dist/ staged
      git commit -m "scholar-corpus v0.4.0: arXiv catalogue, OpenAlex join, citation graph, resumable builds"
      ```

- [ ] **C2. Create the GitHub repo and push.** With the GitHub CLI:
      ```powershell
      gh repo create <OWNER>/scholar-corpus --public --source=. --remote=origin --push
      ```
      Or via the web UI (create an empty repo, no README), then:
      ```powershell
      git remote add origin https://github.com/<OWNER>/scholar-corpus.git
      git push -u origin main
      ```
      The `<OWNER>/scholar-corpus` path must match the URLs from step A5.

- [ ] **C3. (Recommended) Add CI** so the gate runs on every push. Create
      `.github/workflows/ci.yml` running `ruff check .`, `mypy`, and `pytest` on
      Python 3.11 and 3.12 (`pip install -e ".[dev]"`). Commit and push; confirm
      the badge is green before publishing.

- [ ] **C4. (Optional) Protect `main`** in repo Settings → Branches: require the
      CI check to pass before merge.

---

## D. PyPI (see `RELEASE.md` for full detail)

- [ ] **D1. Create accounts + tokens.** Register on <https://pypi.org> and
      <https://test.pypi.org>, enable 2FA, and create an API token for each. Store
      them (do **not** commit): create `%USERPROFILE%\.pypirc`, or set
      `TWINE_USERNAME=__token__` and `TWINE_PASSWORD=<token>` per upload.
      *Recommended alternative:* configure **PyPI Trusted Publishing** (OIDC) from
      a GitHub Actions release workflow, which avoids long-lived tokens entirely.

- [ ] **D2. Build and check the distributions:**
      ```powershell
      pip install -U build twine
      Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
      python -m build
      python -m twine check dist/*      # both must say PASSED
      ```

- [ ] **D3. Confirm the wheel bundles `py.typed`** and smoke-test it in a clean
      venv using the console script (not the source tree) — commands are in
      `RELEASE.md` §2. `scholar-corpus verify <corpus>` must exit 0.

- [ ] **D4. TestPyPI dry run.** Upload to TestPyPI, then install from there into a
      fresh venv (with `--extra-index-url https://pypi.org/simple/` so `pyarrow`
      resolves) and re-run `--version` + `verify`. Confirm the project page
      renders the README at <https://test.pypi.org/project/scholar-corpus/>.
      (`RELEASE.md` §3.)

- [ ] **D5. Publish to PyPI** — only after D4 succeeds:
      ```powershell
      python -m twine upload dist/*
      ```
      The upload is the authoritative name check; it will fail if `scholar-corpus`
      is taken.

- [ ] **D6. Tag the release and push it:**
      ```powershell
      git tag -a v0.4.0 -m "v0.4.0"
      git push origin v0.4.0
      ```
      Then open a GitHub Release from the tag and paste the CHANGELOG section.

- [ ] **D7. Post-publish verification:**
      ```powershell
      py -3.11 -m venv C:\tmp\sc-verify
      C:\tmp\sc-verify\Scripts\pip install scholar-corpus
      C:\tmp\sc-verify\Scripts\scholar-corpus info
      ```
      Confirm <https://pypi.org/project/scholar-corpus/> renders correctly.

---

## E. Real-data acceptance benchmark (separate from publishing)

- [ ] **E1.** Run the reference scope on the real Kaggle arXiv + OpenAlex
      snapshots and reconcile the recovered figures (~313k papers, ~4.7M edges,
      ~93.9% coverage) against the reference, explaining any delta from snapshot
      drift. Full procedure in `docs/acceptance-benchmark.md`. This validates
      scale; the test suite already validates correctness.

---

### Blockers vs. nice-to-haves

**Must do before publishing:** A1, A4, A5, B1, B2, C1, C2, D1–D6.
**Recommended:** A2, A3, C3, D7, trusted publishing (D1 alternative).
**Optional:** C4, E1 (do when you have the real snapshots).
