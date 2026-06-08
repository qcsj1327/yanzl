from futures_mvp.modules.runtime import RuntimeJob, SchedulerConfig, build_scheduler


def test_disabled_scheduler_is_noop() -> None:
    calls: list[str] = []
    scheduler = build_scheduler(
        SchedulerConfig(),
        (RuntimeJob(name="job", callable=lambda: calls.append("called")),),
    )

    scheduler.start()
    result = scheduler.run_once("job")

    assert result is None
    assert scheduler.is_running is False
    assert calls == []


def test_enabled_scheduler_calls_application_callable() -> None:
    calls: list[str] = []
    scheduler = build_scheduler(
        SchedulerConfig(enabled=True, enabled_jobs=("job",)),
        (RuntimeJob(name="job", callable=lambda: calls.append("called")),),
    )

    scheduler.start()
    scheduler.run_once("job")
    scheduler.stop()

    assert calls == ["called"]
    assert scheduler.is_running is False


def test_enabled_scheduler_rejects_unwired_job() -> None:
    scheduler = build_scheduler(
        SchedulerConfig(enabled=True, enabled_jobs=("missing",)),
        (),
    )

    try:
        scheduler.start()
    except RuntimeError as exc:
        assert "missing" in str(exc)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("scheduler did not reject missing job")
