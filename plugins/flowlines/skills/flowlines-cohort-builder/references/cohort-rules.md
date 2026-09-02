# Flowlines cohort rule vocabulary

A cohort definition is `aggregateId`, `name`, an optional `description`, and a `rules` array. All rules must match (logical AND). Each rule is one of the kinds below; the shapes are the API's request schema for `POST /namespaces/{namespaceId}/cohorts` and `POST /namespaces/{namespaceId}/cohorts/preview`.

## Rule kinds

### `numeric`

Compare one per-user metric with a number.

```json
{ "kind": "numeric", "field": "successRate", "op": "lt", "value": 0.5 }
```

- `field`: `csat`, `powerScore`, `sessionCount`, `successRate`, `cleanSessionRate`, `firstSeenDaysAgo`, `avgCostUsd`, `totalCostUsd`, `avgLatencyMs`, `cadence`, `signalCount`, `highSignalCount`, `mediumSignalCount`.
- `op`: `eq`, `neq`, `lt`, `lte`, `gt`, `gte`.
- Rates are fractions between 0 and 1, not percentages.

### `recency`

Filter by when the user was last active.

```json
{ "kind": "recency", "op": "inLastDays", "value": 30 }
```

- `op`: `inLastDays` or `beforeDays`.
- `value`: whole days, 1 to 3650.

### `signalType`

Users affected by given signal types.

```json
{ "kind": "signalType", "op": "includes", "value": ["mcp_tool_loop"], "windowDays": 14 }
```

- `op`: `includes` or `excludes`.
- `value`: 1 to 100 signal type ids, as shown by `list_signals`.
- `windowDays`: optional, 1 to 3650.

### `intentFamily`

Users whose sessions carry given intent families.

```json
{ "kind": "intentFamily", "op": "isOneOf", "value": ["refund"] }
```

- `op`: `isOneOf` or `isNotOneOf`.
- `value`: 1 to 100 intent family names, as returned by `aggregate_sessions` grouped by `intent`.

### `facetSentiment`

Users with sessions carrying a given sentiment facet.

```json
{ "kind": "facetSentiment", "op": "includes", "value": ["frustrated"], "windowDays": 14 }
```

- `op`: `includes` or `excludes`.
- `value`: any of `positive`, `neutral`, `frustrated`, `confused`.
- `windowDays`: optional, 1 to 3650.

### `behavioralFlag`

Users with sessions carrying a given behavioural flag from analysis.

```json
{ "kind": "behavioralFlag", "op": "includes", "value": ["repeated_question"], "windowDays": 30 }
```

- `op`: `includes` or `excludes`.
- `value`: 1 to 100 flag ids, as they appear in session analysis findings.
- `windowDays`: optional, 1 to 3650.

## Related endpoints

All of these require a signed-in user session (bearer JWT); namespace API keys do not authenticate them.

| Endpoint | Purpose |
|---|---|
| `POST /namespaces/{id}/cohorts/preview?sampleLimit=n` | Size a definition before saving: `matchedCount`, `totalCount`, and a sample. |
| `GET /namespaces/{id}/cohorts/rule-suggestions?aggregateId=` | Suggested rules with a rationale for the aggregate. |
| `POST /namespaces/{id}/cohorts` | Create. Optional `category`, `isPinned`, `automationsConfig` (`hubspotListId`, `webhookUrl`). |
| `POST /namespaces/{id}/cohorts/from-selection` | Create from a list of `sessionIds` instead of rules. |
| `POST /namespaces/{id}/cohorts/compare` | Same comparison the MCP `compare_cohorts` tool returns. |

The MCP tools `list_cohorts`, `get_cohort`, and `compare_cohorts` cover reading and comparing without a browser session.
