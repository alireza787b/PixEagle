# PixEagle API Modernization Blueprint

PixEagle's current API surface is mixed across `/status`, `/stats`,
`/commands/*`, `/telemetry/*`, `/api/*`, `/api/yolo/*`, `/video_feed`, and
`/ws/*`. Phase 0 freezes that current surface with route inventory tests before
the `/api/v1` migration begins.

## Standards

- New public business routes use `/api/v1/...`.
- Routes use nouns and subresources instead of ad hoc verb collections.
- Multi-step mutations return a tracked command or action resource.
- Mutations that can be retried accept an idempotency key.
- Dangerous actions expose dry-run or preview where practical and require
  explicit confirmation.
- All JSON routes use typed Pydantic request and response models.
- Errors use a structured envelope with machine-readable code, detail,
  timestamp, path, and request ID.
- OpenAPI includes tags, operation IDs, deprecation flags, and safety metadata.
- Compatibility aliases are temporary and tracked in route inventory tests.

## Initial Canonical Families

```text
/api/v1/system/*
/api/v1/runtime/*
/api/v1/telemetry/*
/api/v1/tracking/*
/api/v1/following/*
/api/v1/flight/*
/api/v1/safety/*
/api/v1/streams/*
/api/v1/models/*
/api/v1/config/*
/api/v1/recordings/*
/api/v1/logs/*
/api/v1/actions/*
/api/v1/commands/*
/ws/v1/*
```

## Route Inventory

Route inventory tests must:

- collect current route registrations without starting Uvicorn, video, MAVLink,
  or PX4 subsystems
- assert the frozen method/path inventory
- assert there are no duplicate method/path pairs
- explicitly track deprecated aliases until removal

During migration, old routes remain only as compatibility aliases with
deprecation metadata and a planned removal checkpoint.
