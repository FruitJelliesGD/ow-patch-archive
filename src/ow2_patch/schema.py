"""Version of the JSON artifacts consumed by external clients (local tools, sites).

Bump INDEX_SCHEMA_VERSION only for backwards-incompatible shape changes of the
`data/*_index.json` / `official_edits.json` artifacts; additive fields do not
need a bump. Consumers must tolerate missing keys (treat as v1) and warn when
they see a higher version.
"""

INDEX_SCHEMA_VERSION = 1
