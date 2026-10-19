# Automatic CTFtime profile updates

Put these files in your public `Team-Visored/Team-Visored` repository, preserving the paths:

- `README.md`
- `.github/workflows/update-profile.yml`
- `scripts/update_profile.py`
- `tests/test_update_profile.py`

The workflow runs on the repository's default branch after uploading the files, on a schedule every 15 minutes, and when you select **Actions → Update CTFtime profile → Run workflow**. No personal access token or Python packages are required. The workflow uses the repository's built-in GitHub token with permission to update its README.

The updater refreshes Nepal rank, worldwide rank, season, best finish, total finishes, official season rating, planned-event count, and the five strongest placements with event links, scores, and rating points. It ranks finishes by lowest placement, then highest score, and removes duplicate events.

The live website endpoint is tried first, followed by its saved snapshot. If both fail or return invalid data, the job fails without changing the saved README. The rest of the README, including the Spydomain credit, stays outside the generated section.

The source date is shown without a time so identical stats do not generate a new commit every 15 minutes. A new snapshot date can still produce one daily update. The displayed results describe the current season, matching the website feed; a new season with no ranked results displays an empty-season message.

## Run locally

```bash
python3 scripts/update_profile.py
python3 -m unittest discover -s tests -p 'test_update_profile.py' -v
```

Edit the design and introduction outside `<!-- CTFTIME:START -->` and `<!-- CTFTIME:END -->`. The updater replaces only the content between those markers.

## GitHub setup

Keep GitHub Actions enabled for the repository. If repository settings restrict token permissions, go to **Settings → Actions → General → Workflow permissions** and allow **Read and write permissions**. A branch rule that blocks automated direct commits must allow this workflow to update the default branch.

GitHub schedules can be delayed and only run from the default branch. Public repositories can have scheduled workflows disabled after 60 days without repository activity. Re-enable a disabled workflow from the Actions tab. See [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
