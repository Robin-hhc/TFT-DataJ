# TFT-DataJ development rules

## Bug fixes and accumulated regression protection

Before fixing a reported bug, read `docs/testing/regression-accumulation.md`
and locate its entry in `docs/testing/regressions.json`. Preserve unrelated
working-tree changes and the original evidence.

1. Reproduce the user-visible failure at the affected seam: source query,
   entity identity, asynchronous state, Qt display, clipboard or capture.
   Write a regression that fails for that defect before changing production code.
   A passing mock or a test named after the bug is not proof of reproduction.
2. Independently check the expected answer. Preserve captured requests,
   responses and screenshot originals. Never generate accepted answers from
   failing observations or the current implementation. Unreviewed captures
   stay pending; they do not count as passed.
3. Register the exact test method IDs and public/private scope in the history
   registry. Append approved screenshot hashes to the private review baseline
   using the documented registration command. Keep private screenshots local.
4. Run the affected tests, then the unified validation entrypoint. Include
   private replay when changing recognition, capture or original-frame paths.
   Run data fault injection when changing ranking/query/display behavior.
   Verify that a relevant faulty implementation is rejected by the new test.
5. Report the test command, revision, actual outcomes and remaining limits.
   A source test does not prove the packaged EXE, a physical side button,
   MuMu compositing or real game FPS. Record those checks separately.

Never recover a green run by deleting/skipping a registered test, dropping an
approved original/oracle, weakening an assertion, or regenerating expected
answers from the modified code. Retain historical registry IDs. A justified
test replacement or coverage change needs a new `coverage_change_note` with
independent evidence; old immutable fixtures stay available under their paths.

Completion requires no unaccounted failures or skips, explicit private/hardware
limits, and the new protection included in the unified report. Reversible
cosmetic changes do not need tests that merely mirror implementation details.

## Validation entrypoints

Use Python 3.12 with `packaging/requirements-runtime.txt`; the local development
runtime is `work/p0-runtime/Scripts/python.exe` when present.

```powershell
python -X utf8 tools/validate_data.py --release-gate
python -X utf8 tools/validate_data.py --include-private --release-gate --report work/data-validation/with-private.json
python -X utf8 tools/check_data_mutations.py
```

Public CI must be reproducible from a clean clone. Real clipboard tests restore
the previous MIME contents. Test-only work does not require starting a match.
See `docs/testing/README.md` for package and performance checks.
