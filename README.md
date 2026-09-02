# ToBid MCP — Taiwan Government Tenders

MCP server for searching and analyzing **Taiwan government procurement (tenders)**: 14M+ notices since 1999, updated daily from Taiwan's official e-procurement platform.

Beyond search, it exposes the analysis engine of [ToBid](https://tobid.tw):

- **Vendor intelligence** — win rate, known award totals, top clients, head-to-head rivalry records, recent losses (and who won instead)
- **Agency intelligence** — spending patterns, supplier concentration, competition metrics (average bidders / sole-bid rate / failure rate), peak tendering months, and **recurring annual tenders with next-tender predictions**
- **Price analysis** — suggested bids (conservative / typical / aggressive) from historical award-to-budget ratios, benchmarked against similar cases
- **Failed-tender opportunities** — repeatedly failed tenders where competition is low and agencies are eager to award

**Free, no API key, no registration.**

## Quick start

This is a remote MCP server (streamable HTTP). No installation needed:

```
https://api.tobid.tw/mcp
```

**Claude Code**

```bash
claude mcp add --transport http tobid https://api.tobid.tw/mcp
```

**Claude Desktop / claude.ai** — Settings → Connectors → Add custom connector, paste the URL above.

Also listed in the official MCP registry as `tw.tobid/tenders`.

## Tools

| Tool | Description |
|---|---|
| `search_tenders` | Full-text tender search with filters (region, year, budget range, agency, vendor) |
| `get_tender` | Single tender timeline: notices, amounts, winners, competition status |
| `price_analysis` | Suggested bid range from historical award/budget ratios |
| `vendor_report` | Vendor intelligence: win rate, totals, top clients, rivals, recent losses |
| `unit_report` | Agency intelligence: spending, competition metrics, recurring tenders + next-tender predictions |
| `compare_vendors` | Head-to-head record between two vendors |
| `hot_opportunities` | Repeatedly failed tenders (low competition entry points) |
| `find_entity` | Fuzzy name → official vendor/agency names and IDs |

## Example prompts

- "What smart streetlight tenders are open in Taichung?"
- "Analyze Chunghwa Telecom's recent government contract wins"
- "Is the Legislative Yuan a good agency to bid for? When will it tender again?"
- "How much should I bid for this tender?"

(Works in Chinese too — the underlying data is in Traditional Chinese.)

## Data

Source: public data from Taiwan's Government e-Procurement System (政府電子採購網), operated by the Public Construction Commission, Executive Yuan. ~14 million notices from 1999 to present, refreshed daily. This is a third-party service; verify critical figures against official notices.

## Running your own

`mcp_server.py` is a thin FastMCP wrapper over the ToBid API. Point `TOBID_API` at the public API if you want to self-host the wrapper:

```bash
pip install "mcp<2" requests
TOBID_API=https://api.tobid.tw MCP_HOST=127.0.0.1 MCP_PORT=8890 python mcp_server.py
```

## License

MIT
