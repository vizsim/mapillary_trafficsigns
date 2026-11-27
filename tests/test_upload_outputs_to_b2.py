"""Tests for scripts/upload_outputs_to_b2.sh, with a fake b2 CLI - no network, no B2."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "upload_outputs_to_b2.sh"
PARQUETS = "b2://vizsim-public-archive/mapillary_trafficsigns/"
CAMPAIGN = "b2://vizsim-public-archive/mapillary_trafficsigns/cycleway-campaign/"

# Records every `b2 sync` by its destination. A destination containing
# $FAKE_B2_FAIL fails its first $FAKE_B2_FAIL_TIMES calls, as B2 did on 28.10.2026.
FAKE_B2 = """#!/usr/bin/env bash
dest="${@: -1}"
echo "$dest" >> "$FAKE_B2_LOG"
if [[ -n "${FAKE_B2_FAIL:-}" && "$dest" == *"$FAKE_B2_FAIL"* ]]; then
  n=$(cat "$FAKE_B2_COUNT" 2>/dev/null || echo 0)
  echo $((n + 1)) > "$FAKE_B2_COUNT"
  if (( n < FAKE_B2_FAIL_TIMES )); then
    echo "503 service_unavailable no tomes available" >&2
    exit 1
  fi
fi
"""


@pytest.fixture
def repo(tmp_path):
    """The script in a repo of its own, with the ts output folders and b2 in ~/.local/bin."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts")
    (root / "output").mkdir()
    (root / "use_cases" / "cycleway_complete_campaign" / "ts_output").mkdir(parents=True)
    # The script puts ~/.local/bin first in PATH, where `uv tool install b2` puts b2.
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    fake = home / ".local" / "bin" / "b2"
    fake.write_text(FAKE_B2)
    fake.chmod(0o755)
    return {"root": root, "home": home, "log": tmp_path / "b2.log", "count": tmp_path / "b2.count"}


def upload(repo, fail="", fail_times=0, credentials=True):
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(repo["home"]),
        "B2_RETRY_WAIT": "0",
        "FAKE_B2_LOG": str(repo["log"]),
        "FAKE_B2_COUNT": str(repo["count"]),
        "FAKE_B2_FAIL": fail,
        "FAKE_B2_FAIL_TIMES": str(fail_times),
    }
    if credentials:
        env |= {"B2_ARCHIVE_KEY_ID": "id", "B2_ARCHIVE_KEY": "key"}
    result = subprocess.run(
        ["bash", str(repo["root"] / "scripts" / "upload_outputs_to_b2.sh"), "mapillary-ts_worker"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    calls = repo["log"].read_text().split() if repo["log"].exists() else []
    return result, calls


def test_a_clean_upload_syncs_each_job_once(repo):
    result, calls = upload(repo)

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == [PARQUETS, CAMPAIGN]
    assert "neuer Versuch" not in result.stdout


def test_a_failed_job_gets_one_more_try_and_only_that_job(repo):
    # The parquets went through; repeating them while B2 is still down could
    # fail a job whose files are already up.
    result, calls = upload(repo, fail="cycleway-campaign", fail_times=1)

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == [PARQUETS, CAMPAIGN, CAMPAIGN]
    assert "neuer Versuch" in result.stdout and "B2-Upload fertig" in result.stdout


def test_a_lasting_outage_fails_the_upload_after_the_second_try(repo):
    result, calls = upload(repo, fail="cycleway-campaign", fail_times=5)

    assert result.returncode == 1
    assert calls == [PARQUETS, CAMPAIGN, CAMPAIGN]
    assert "Mindestens ein B2-Sync ist fehlgeschlagen" in result.stdout


def test_without_credentials_the_upload_is_skipped(repo):
    result, calls = upload(repo, credentials=False)

    assert result.returncode == 3
    assert calls == []
