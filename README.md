# ToBid MCP — Taiwan Government Tenders

MCP server for searching and analyzing **Taiwan government procurement (tenders)**: 14M+ notices since 1999, updated daily from Taiwan's official e-procurement platform.

Beyond search, it exposes the analysis engine of [ToBid](https://tobid.tw):

- **Vendor intelligence** — win rate, known award totals, top clients, head-to-head rivalry records, recent losses (and who won instead)
- **Agency intelligence** — spending patterns, supplier concentration, competition metrics (average bidders / sole-bid rate / failure rate), peak tendering months, and **recurring annual tenders with next-tender predictions**
- **Price analysis** — suggested bids (conservative / typical / aggressive) from historical award-to-budget ratios, benchmarked against similar cases
- **Failed-tender opportunities** — repeatedly failed tenders where competition is low and agencies are eager to award
- **Pre-tender signals** — procurement forecasts (1–3 months ahead of the notice) and draft documents open for public review
- **Compliance** — debarment list, revocations and Article 101 suspension cases, straight from the official site
- **Evaluation committees** — published committee members per tender, member records, agency committee concentration, and which members a vendor most often meets
- **Asset sales and rentals** — government auctions of vehicles, equipment, land and venues

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
| `procurement_forecast` | Procurement forecasts: tenders agencies plan to issue in the coming months (planned month, budget, method) |
| `public_reading` | Draft tender documents open for public review, with opinion deadlines |
| `vendor_compliance` | Debarment (拒絕往來) status, revocations and Article 101 suspension cases for a vendor |
| `evaluation_committee` | Published evaluation-committee members for a tender (name, position, background) |
| `committee_member` | A committee member's record: cases, agencies, categories, co-members, winning vendors, award/budget ratio |
| `search_committee_members` | Find committee members by name, position or agency |
| `unit_committee` | An agency's most frequently appointed committee members and top-5 concentration |
| `vendor_committee` | Committee members a vendor most often meets, with met/won counts and the vendor's overall win rate |
| `asset_sales` | Government asset sales (財物變賣) and rentals (財物出租): floor price, bid opening, location |

## Example prompts

- "What smart streetlight tenders are open in Taichung?"
- "Analyze Chunghwa Telecom's recent government contract wins"
- "Is the Legislative Yuan a good agency to bid for? When will it tender again?"
- "How much should I bid for this tender?"

(Works in Chinese too — the underlying data is in Traditional Chinese.)

## Data

Besides the 14M+ tender notices, the server carries data scraped daily from the official procurement site query pages: procurement forecasts, public-review drafts, the debarment list, Article 101 cases, published evaluation committees (from 2018) and asset sales/rentals (from 2020). Committee data is presented as factual aggregation of official publications; evaluations are collegial decisions confirmed by the agency, and the tools say so in their output.

Source: public data from Taiwan's Government e-Procurement System (政府電子採購網), operated by the Public Construction Commission, Executive Yuan. ~14 million notices from 1999 to present, refreshed daily. This is a third-party service; verify critical figures against official notices.

## Running your own

`mcp_server.py` is a thin FastMCP wrapper over the ToBid API. It speaks stdio by default (set `MCP_TRANSPORT=streamable-http` to serve HTTP instead):

```bash
pip install "mcp<2" requests
TOBID_API=https://api.tobid.tw python mcp_server.py
```

Or with Docker:

```bash
docker build -t tobid-mcp .
docker run -i tobid-mcp
```

## License

MIT
