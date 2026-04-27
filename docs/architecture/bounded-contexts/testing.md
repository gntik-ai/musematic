# Testing

Testing owns platform regression APIs, E2E harness surfaces, synthetic journey validation, and test-result streams.

Primary entities include test suites, run state, generated reports, and CI artifacts. REST APIs expose selected test controls for admins and E2E runs. Events are emitted on testing-related topics and the WebSocket `testing` channel.

Testing is operationally separate from production execution but reuses the same observability and evidence model.
