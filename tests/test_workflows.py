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
    for name in ("update-data.yml", "dashboard.yml"):
        assert "group: data-commits" in (WF / name).read_text()


def test_dashboard_job_commits_every_log_it_writes():
    text = (WF / "dashboard.yml").read_text()
    for log in ("odds_snapshots.csv", "picks_log.csv", "forecasts_log.csv"):
        assert log in text
