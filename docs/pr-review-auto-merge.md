# PR review + auto-merge flow

## What this setup does
- Runs pytest on every non-closed pull request update.
- Lets you enable auto-merge from the PR body itself.
- Keeps auto-merge disabled unless both checkboxes below are ticked:
  - `Codex review completed`
  - `Enable auto-merge after checks pass`

## Your one-time GitHub setup
1. Open **Settings -> Rules -> Rulesets** or your branch protection rule for `main`.
2. Require pull requests before merging.
3. Require status checks to pass before merging.
4. Add the `PR / Tests` check as a required status check.
5. Keep repository-level **Allow auto-merge** enabled.

## Daily usage
1. Let Codex open or update a PR.
2. Run the prompt from `docs/codex-pr-review-prompt.md` in a fresh Codex review session.
3. Fix anything blocking.
4. Mark these boxes in the PR body:
   - `Codex review completed`
   - `Enable auto-merge after checks pass`
5. Move the PR out of draft.
6. GitHub will auto-merge it after the required checks pass.

## Important note
This setup does not make GitHub run Codex by itself. It gates merge on your explicit Codex review step plus CI.
