# Synthetic fixtures

These are the fixture sets T1–T8 and T10 of DEVELOPMENT_TEST_PLAN §7 (FN-OPS-06, TSK-OPS-06-C). Every file is synthetic, so the sets contain no patient data (SEC-17).

Generate them with `just fixtures`; check them with `just fixtures-check`. The generator is [`tools/fixtures`](../../tools/fixtures/src/jude_fixtures).

## Layout

| Path | Content |
|---|---|
| `manifest.json` | Every fixture: set, parameters, seed, analytic JSON path and its SHA-256, and every file with its size and SHA-256 |
| `<set>/<name>.json` | Analytic ground truth. Always committed. |
| `<set>/<name>/<file>` | Mesh and defect files. Files over 1.1 MB are pinned by hash only: they are listed in `.gitignore` and written locally by `just fixtures`. |

## Rules

- **Coordinates and frame.** Coordinates are in mm. The phantom frame is right-handed: x = A-P (+x anterior), y = M-L (+y patient-left), z = superior.
- **Analytic values belong to the smooth surface.** The sections, CI, HC, diagonals, CVA and CVAI follow FN-KMS-03/04/05 and the 30° and 40° presets of DEC-027. Mesh results differ by chord error; the verification tasks judge that difference with the DEC-025 tolerances.
- **Test parameters are not clinical values.** The ellipsoid semi-axes, magnitudes and offsets are inputs for tests only.
- **The bytes are identical on every host.** Mesh coordinates use only correctly rounded IEEE operations. Trigonometric values are snapped to a 2⁻⁴⁰ grid. Analytic numbers are rounded to 1e-9. Random choices use PCG64 with a fixed seed.
- **Changing a fixture.** Change the generator, run `just fixtures`, and review the diff of `manifest.json`. A changed hash means a changed fixture, so the PR states why.
- **T9** (reference designs, golden hashes) belongs to TSK-OPS-04-C, and **T13–T15** to XC-SHR-03.
