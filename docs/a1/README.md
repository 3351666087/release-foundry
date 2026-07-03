# A1 Local SDK/Runner

Local-only SDK/Runner/Adapter/Trace loop. It wraps external agents, runs 30-80 case batches, records observations and VM stream metadata, and emits JSON fixtures for A2/A3 without Ashr API calls or real keys.

Fresh setup:

```powershell
python -B -m pytest tests/a1 -q -p no:cacheprovider
python -m services.runner.cli --input docs/a1/evidence/local_agent_cases_30.json --output docs/a1/evidence/local_run_30.json --agent examples.agents.mock_agent:RespondingMockAgent --dataset-id a2-local-scenarios --runner-id a1-local-runner --max-workers 4 --timeout 5 --fail-on-case-failure
python examples/agents/mock_agent.py --write-fixtures examples/agents/fixtures
```
