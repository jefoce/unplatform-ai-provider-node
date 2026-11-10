"""Orphan job directory listing tests."""

from pathlib import Path

from test_exec_support import JOB_ID, SECOND_JOB_ID

from upai_provider.materialize_cleanup import list_job_dirs, orphan_job_ids
from upai_provider.protocol import format_run_id


def _make_dir(root: Path, name: str) -> None:
    (root / name).mkdir(parents=True)


def test_list_job_dirs_maps_run_dir_to_base_id(tmp_path: Path) -> None:
    root = tmp_path / "input"
    run_dir = format_run_id(SECOND_JOB_ID, 2)
    assert not set(run_dir) & set('<>:"|?*')
    _make_dir(root, JOB_ID)
    _make_dir(root, run_dir)

    assert list_job_dirs(root) == (JOB_ID, SECOND_JOB_ID)


def test_list_job_dirs_ignores_invalid_names(tmp_path: Path) -> None:
    root = tmp_path / "input"
    _make_dir(root, "not-a-job")
    (root / "file.txt").write_text("x", encoding="utf-8")

    assert list_job_dirs(root) == ()


def test_list_job_dirs_missing_root_is_empty(tmp_path: Path) -> None:
    assert list_job_dirs(tmp_path / "missing") == ()


def test_orphan_job_ids_lists_missing_dirs(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    result_root = tmp_path / "result"
    _make_dir(input_root, JOB_ID)
    _make_dir(result_root, SECOND_JOB_ID)

    assert orphan_job_ids(input_root, result_root, keep_ids=set()) == (
        JOB_ID,
        SECOND_JOB_ID,
    )


def test_orphan_job_ids_skips_kept_dirs(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    result_root = tmp_path / "result"
    _make_dir(input_root, JOB_ID)
    _make_dir(result_root, SECOND_JOB_ID)

    assert orphan_job_ids(input_root, result_root, keep_ids={JOB_ID}) == (SECOND_JOB_ID,)
