#!/usr/bin/env python3
"""


Scenario: a  job exports customer records -- a compliance event that is
not a single gated tool call, so we log it.

Run:
    source ~/path/to-env/nenv/bin/activate
    export MACAW_HOME=~/path/to/macaw-client
    python audited_export.py

Datadog:  service:macaw-mcp @event:export_complete
"""
from macaw_client import MACAWClient

client = MACAWClient(app_name="data-export-job")
client.register()


def run_export(dataset, destination):
    target = f"dataset:{dataset}"                      
    meta = {"destination": destination}             

    client.log_event(event_type="export_start", action="start",
                     target=target, signed=True, metadata=meta)
    try:
        rows = _do_export(dataset, destination)
        client.log_event(event_type="export_complete", action="complete",
                         target=target, outcome="success", signed=True,
                         metadata={**meta, "rows_exported": rows})
        print(f"exported {rows} rows")
    except Exception as e:
        client.log_event(event_type="export_error", action="error",
                         target=target, outcome="error", signed=True,
                         metadata={**meta, "error": str(e)})
        raise


def _do_export(dataset, destination):
    return 1284


run_export("customers", "s3://acme-exports/nightly")
client.unregister()
