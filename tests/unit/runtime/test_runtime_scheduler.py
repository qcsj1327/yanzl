from futures_mvp.modules.runtime import RuntimeJob, SchedulerConfig, build_scheduler


class CountingPaperJob:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return "paper-result"


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


def test_disabled_scheduler_does_not_run_injected_paper_job() -> None:
    paper_job = CountingPaperJob()
    scheduler = build_scheduler(
        SchedulerConfig(),
        (RuntimeJob(name="paper_runtime_job", callable=paper_job),),
    )

    scheduler.start()
    result = scheduler.run_once("paper_runtime_job")

    assert result is None
    assert paper_job.calls == 0


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


def test_enabled_scheduler_calls_injected_paper_job_callable() -> None:
    paper_job = CountingPaperJob()
    scheduler = build_scheduler(
        SchedulerConfig(enabled=True, enabled_jobs=("paper_runtime_job",)),
        (RuntimeJob(name="paper_runtime_job", callable=paper_job),),
    )

    scheduler.start()
    result = scheduler.run_once("paper_runtime_job")

    assert result == "paper-result"
    assert paper_job.calls == 1


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
