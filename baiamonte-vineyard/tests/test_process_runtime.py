from app.process_runtime import begin_process, finish_process, mark_process_timed_out, processing_runtime_snapshot


def test_runtime_snapshot_separates_running_and_timed_out() -> None:
    assert begin_process("runtime-test", code="weather", timeout_seconds=1)
    assert not begin_process("runtime-test", code="weather", timeout_seconds=1)
    snapshot = processing_runtime_snapshot()
    assert snapshot["active_count"] == 1
    assert snapshot["timed_out_count"] == 0

    mark_process_timed_out("runtime-test", "expected timeout")
    snapshot = processing_runtime_snapshot()
    assert snapshot["active_count"] == 1
    assert snapshot["timed_out_count"] == 1
    assert snapshot["jobs"][0]["error"] == "expected timeout"
    finish_process("runtime-test")
    assert processing_runtime_snapshot()["active_count"] == 0
