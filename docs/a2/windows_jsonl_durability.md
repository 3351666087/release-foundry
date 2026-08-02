# Windows JSONL durability capability note

A2 currently proves same-directory temporary-file writing and atomic target replacement on the active Windows filesystem. This protects the previous target bytes when replacement fails before completion. It does **not** prove durability across power loss because Python's portable API does not expose a supported directory fsync operation on Windows.

The manifest therefore records `directory_fsync_state: not_exposed`. A future Windows-specific adapter may use supported OS handles and flush primitives, but until that implementation is tested, A2 must not report crash-durable persistence. PostgreSQL transactional persistence remains the preferred production proof when a safe DSN and tooling are available.
