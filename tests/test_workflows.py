"""The schedules the user relies on: player data every Tuesday, the card
four times a day, and the two jobs never pushing at the same time."""
import re
from pathlib import Path

WF = Path(__file__).parent.parent / ".github" / "workflows"


def _cron(name):
    return re.findall(r'cron:\s*"([^"]+)"', (WF / name).read_text())


def test_player_data_and_model_update_every_tuesday():
    crons = _cron("update-data.yml")
    assert len(crons) == 1
    minute, hour, dom, month, dow = crons[0].split()
    assert dow == "2" and dom == "*" and month == "*"      # Tuesday, every week
    assert minute != "0"                                    # off the busy full hour
    text = (WF / "update-data.yml").read_text()
    assert "scripts/update_player_data.py" in text
    assert "update_data.py --skip-player-data" in text


def test_dashboard_runs_four_times_a_day():
    assert _cron("dashboard.yml") == ["17 3,9,15,21 * * *"]


def test_both_jobs_share_one_concurrency_group():
    for name in ("update-data.yml", "dashboard.yml", "pm-traders.yml"):
        assert "group: data-commits" in (WF / name).read_text()


def test_dashboard_job_commits_every_log_it_writes():
    text = (WF / "dashboard.yml").read_text()
    for log in ("odds_snapshots.csv", "picks_log.csv", "forecasts_log.csv"):
        assert log in text


def test_queued_runs_start_from_the_branch_tip():
    """A run waiting in the concurrency queue keeps the SHA it was triggered
    on; checking that out made the dashboard run of 2026-10-24 rebuild on a
    stale commit and fail its push."""
    for name in ("update-data.yml", "dashboard.yml", "pm-traders.yml"):
        text = (WF / name).read_text()
        assert "ref: ${{ github.ref_name }}" in text
        assert "pull --rebase -X theirs" in text
        assert "git rebase --abort" in text


def test_append_only_logs_merge_by_union():
    attrs = (WF.parent.parent / ".gitattributes").read_text()
    for log in ("odds_snapshots.csv", "picks_log.csv", "forecasts_log.csv", "ta_elo_history.csv"):
        assert f"data/processed/{log} merge=union" in attrs


def test_weekly_refresh_script_touches_only_data_and_main():
    """The Tuesday command run from the Claude Code chat: a separate checkout
    of main, the player-data refresh with surface speed, a commit of
    data/processed only, pushed to main."""
    script = (WF.parent.parent / "scripts" / "weekly_ta_refresh.sh").read_text()
    assert "worktree add" in script and "origin/main" in script
    assert "update_player_data.py --surface-speed" in script
    assert "git add data/processed" in script
    assert "git push -q origin HEAD:main" in script
    assert "-X theirs" in script


def test_rankings_refresh_daily_and_rebuild_the_live_page():
    assert _cron("pm-traders.yml") == ["23 4 * * *"]
    daily = (WF / "pm-traders.yml").read_text()
    assert "update_pm_traders.py --days 30" in daily               # tennis
    assert "--sport soccer" in daily and "--sport basketball" in daily
    assert "scripts/build_pros_live.py" in daily
    assert "update_pm_traders" not in (WF / "update-data.yml").read_text()
