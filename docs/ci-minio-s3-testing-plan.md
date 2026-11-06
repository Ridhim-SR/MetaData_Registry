# CI plan: exercise S3 behavior with MinIO

**Status:** Complete — steps 1–5 implemented 2026-11-06. Verified locally against MinIO; not yet pushed or run in GitHub Actions.
**Planning date:** 2026-11-05
**Implementation target:** 2026-11-06
**Scope:** `data_services` CI tests and their documentation

## Goal

Run the S3-dependent `data_services` tests against an ephemeral, local MinIO
service in GitHub Actions. This supplements Moto unit tests with checks against
a real S3-compatible HTTP server, especially the conditional writes used by
cross-process storage locks and the concurrent lookup update that has flaked
under Moto.

This work is test infrastructure only. It must not connect to Wasabi, read
developer `.env` files, publish to OpenMetadata, or change production storage
behavior.

## Current state

- `.github/workflows/ci.yml` runs `data_services` pytest on `ubuntu-latest`.
- The workflow currently says two MinIO-dependent tests are accepted as skips.
- `data_services/tests/test_batch.py` has two tests marked to skip unless
  `localhost:9000` accepts a connection. With MinIO available, these tests run
  the batch CLI using a unique `tests/<uuid>` prefix and storage-only settings.
- `data_services/tests/test_s3_storage.py` tests basic S3 operations and
  concurrency using Moto. In particular,
  `test_concurrent_registrations_from_two_machines_lose_no_rows` exercises
  concurrent read-modify-write updates to `_lookups/departments.csv`, but Moto's
  in-memory S3 has previously produced a closed-file flake.
- `infrastructure/minio/docker-compose.yml` and the local MinIO README describe
  the developer stack. The compose image currently uses a mutable `latest` tag;
  CI must not silently inherit that moving dependency.
- The CI workflow must continue to work without repository or environment
  secrets. No real `.env` file is needed.

## Proposed implementation

### 1. Add an ephemeral MinIO service to the data-services CI job

- Run MinIO as a GitHub Actions service container for the `data-services` job,
  publishing its S3 API on runner `localhost:9000`, which matches the existing
  test default.
- Before implementation, verify an available maintained image and its
  supported startup/health-check behavior. Pin a specific release (preferably
  an immutable digest); do not use `latest`.
- Use test-only credentials in the workflow. They are disposable local service
  credentials, not repository secrets.
- Add a readiness check that waits for the S3 API to be responsive and fails
  with useful logs if MinIO does not become ready. Do not start pytest before
  readiness is confirmed.
- Create only the bucket(s) needed by the tests. Prefer the existing
  `infrastructure/minio/init_buckets.py` with explicit test environment
  variables or a small focused initialization step. Verify precisely which
  buckets it creates before wiring it in.
- Keep all test object keys under unique test prefixes and clean them up as
  appropriate. Since the service is ephemeral, deleting the service container
  also disposes of its data.

### 2. Run the existing MinIO-dependent batch tests in CI

- Ensure the service is available at `http://localhost:9000` when pytest runs.
- Confirm both MinIO-dependent tests in `test_batch.py` run and pass rather
  than skip. Preserve the existing skip behavior for local developers who
  intentionally run without MinIO.
- Keep the tests' current isolation: a per-run throwaway prefix, no
  OpenMetadata token, and no use of developer storage.

### 3. Add a real-MinIO storage concurrency integration test

- Add a separate integration test (or a clear opt-in mode in
  `test_s3_storage.py`) that runs only when CI explicitly enables it and
  passes MinIO connection settings.
- Reuse the production `S3ObjectStorage` and `lookups.register_department`
  code path. Do not replace the Moto unit test; both test types have value.
- Run concurrent registrations from multiple storage instances against one
  shared lookup CSV. Assert that every unique department row survives and
  that no lock objects remain after successful completion.
- Use a unique prefix per test invocation, and clean it up in a `finally`
  path so failures do not contaminate later tests.
- Keep the normal local suite useful: if MinIO integration is not explicitly
  enabled, do not introduce a new unexplained skip. Report the reason clearly
  or leave this check to a dedicated CI command.
- Use a bounded workload in the normal CI run. If repeated stress iterations
  are needed to reproduce intermittent races, add a separate repeatable stress
  command or workflow-dispatch option rather than making every PR run
  unbounded.

### 4. Keep CI safe and diagnosable

- No step may read or materialize `data_services/.env` or use credentials for
  Wasabi or OpenMetadata.
- Set the test endpoint, bucket, region, credentials, and environment
  explicitly in the job. Verify the app's branch/environment routing cannot
  override these values and that the batch tests remain storage-only.
- Add a preflight step that identifies the endpoint and bucket (without
  printing secrets) and confirms bucket access.
- Preserve `pytest -rs` reporting. Once MinIO is ready, the two existing
  MinIO-dependent tests must be reported as passed, not skipped.
- Update the workflow comments to describe the service and its isolation,
  replacing the note that the skips are accepted as a follow-up.

### 5. Document local and CI behavior

- Update `data_services/README.md` with:
  - which tests use Moto and which exercise MinIO;
  - how to run the MinIO integration test locally using the existing local
    MinIO stack;
  - the explicit opt-in/configuration required for the new integration test;
  - how to run a bounded stress repetition when investigating a race.
- Keep secrets out of command examples. Use the existing disposable local
  MinIO credentials only where appropriate.

## Suggested execution order for 2026-11-06

1. Recheck `git status`, current `main`, and the workflow/test files before
   editing; preserve unrelated worktree changes.
2. Verify the chosen MinIO image, version/digest, startup command, and health
   check. Decide whether to use the Actions service-container feature or a
   Docker Compose step; prefer the simpler option that exposes the service to
   `ubuntu-latest` runner processes on `localhost`.
3. Add the CI service, explicit test configuration, readiness check, and
   bucket initialization. Run the existing two tests locally against the
   developer MinIO stack first.
4. Add and run the real-MinIO concurrent lookup integration test. Exercise
   it locally more than once, confirming row preservation and lock cleanup.
5. Run the focused tests:

   ```bash
   python -m pytest tests/test_s3_storage.py tests/test_batch.py -q -rs
   ```

6. Run the full `data_services` suite with MinIO available:

   ```bash
   python -m pytest -q --no-header -rs
   ```

7. Review pytest output for unexpected skips, confirm no service writes outside
   the unique test prefix, then push a branch and inspect the actual GitHub
   Actions run.
8. Update the README and workflow comments, review the final diff, and report
   the passed/skipped counts and any limitations.

## Acceptance criteria

- The data-services CI job starts a pinned MinIO image, waits for readiness,
  creates the required test bucket, and tears down the service at job end.
- Both existing MinIO-dependent batch CLI tests pass in CI and are not skipped.
- A real-MinIO concurrency test uses production S3 storage/locking code and
  proves all expected rows are present after competing registrations.
- The concurrency test also verifies lock cleanup, and test objects are
  isolated under a disposable prefix.
- Moto-based unit tests remain in place and pass.
- The full data-services test job passes with no MinIO-related skips.
- CI uses no Wasabi/OpenMetadata credentials, repository secrets, or developer
  `.env` files, and the rest of the CI workflow remains unchanged.
- Documentation explains both local and CI execution, including the
  distinction between Moto unit tests and MinIO integration tests.

## Implementation record (2026-11-06)

- `.github/workflows/ci.yml`: pinned MinIO service container (tag + digest),
  readiness poll, bucket creation via `init_buckets.py`, a preflight that
  prints the endpoint/bucket and confirms access, and explicit `SDA_MINIO_*`
  settings on the test step.
- `tests/test_s3_minio_integration.py`: opt-in conditional-write/lock test and
  concurrent-registration test; unique prefix per invocation, `finally`
  cleanup, optional bounded `SDA_MINIO_STRESS_ROUNDS`.
- `tests/test_batch.py`: derives the allowed `ENVIRONMENT` from the branch and
  points every environment prefix at the test MinIO.
- `infrastructure/minio/docker-compose.yml` and its README: the local image is
  pinned to the same tag + digest as CI. Recreating the container preserved the
  named `minio-data` volume and every object; the full suite passed afterwards.
- `data_services/README.md`: Moto vs MinIO, local opt-in, stress command.

Local verification: **669 passed, 0 skipped** with `SDA_MINIO_INTEGRATION=1`;
**9 passed, 2 explained skips** without it; a 50-round stress run passed and
left 0 integration objects behind. On Windows, `localhost` added ~21 s per new
S3 connection, so the examples and CI use `127.0.0.1`.

## Out of scope

- Replacing Moto or converting every S3 unit test into an integration test.
- Changing `S3ObjectStorage` lock semantics unless the MinIO test exposes a
  reproducible product bug. Any such fix should be separately reasoned about
  and covered by both Moto and MinIO tests.
- Running against a real Wasabi bucket in CI.
- Changing the registry's normal local/development/production routing.
- Making download API changes or adding MinIO to the `apps/api` job.

## Risks and decisions to resolve during implementation

- **MinIO image availability:** choose a pinned image that can be pulled
  reliably by GitHub-hosted runners; do not assume the local legacy image's
  mutable tag is appropriate for CI.
- **S3 conditional-write compatibility:** the lock implementation relies on
  `If-None-Match` and `If-Match` behavior. The integration test should fail
  clearly if the chosen MinIO release does not honor these conditions.
- **Concurrency flakiness:** keep a deterministic bounded integration case in
  PR CI, and use a repeatable stress mode for investigation. Do not infer safety
  from a single pass or respond to a flaky test by weakening its assertions.
- **Resource readiness:** container start does not imply S3 readiness; use a
  health/readiness loop with a finite timeout and actionable failure output.
- **Existing local compose image:** resolved 2026-11-06 — the developer
  compose pins the same tag and digest as CI. Recreating the container kept
  the `minio-data` volume and all objects.
