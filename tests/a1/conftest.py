def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "docker: opt-in integration test that creates disposable Docker resources",
    )
