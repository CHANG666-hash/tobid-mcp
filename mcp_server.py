# -*- coding: utf-8 -*-
"""
ToBid MCP Server — 台灣政府標案搜尋與情報分析

把 ToBid（tobid.tw）的搜尋與分析引擎包成 MCP 工具，讓 Claude 等 AI 助手
直接查標案、看廠商／機關情報、要出價建議。

設計原則：
  * 工具呼叫本機既有 API（127.0.0.1:8899），複用查詢快取，與主服務隔離。
  * 回傳「瘦身」：AI 的 context 有限，只留判斷需要的欄位、限制筆數——
    完整資料引導 AI 附上 tobid.tw 連結讓使用者自己看。
  * User-Agent 標 ToBid-MCP，查詢紀錄裡可與網頁流量區分。

部署：systemd pcc-mcp.service → streamable-http 於 127.0.0.1:8890/mcp，
Caddy 將 api.tobid.tw/mcp 反代過來。
"""
import os

import requests
from mcp.server.fastmcp import FastMCP

API = os.environ.get("TOBID_API", "http://127.0.0.1:8899")
UA = {"User-Agent": "ToBid-MCP/1.0"}
SITE = "https://tobid.tw"

mcp = FastMCP(
    "tobid",
    host=os.environ.get("MCP_HOST", "127.0.0.1"),
    port=int(os.environ.get("MCP_PORT", "8890")),
    instructions=(
        "台灣政府標案（政府電子採購網）搜尋與情報分析。收錄 1999 年至今約 1,400 萬筆"
        "招標決標公告，每日更新。除了查公告，強項是分析：廠商得標率與對手勝率、"
        "機關發包週期與下次發案預測、單案底價分析（出價建議）。"
        "廠商與機關請先用 find_entity 取得正式名稱／代碼再查報告。"
        "回答使用者時可附 ToBid 頁面連結供進一步瀏覽。"
    ),
)


def _get(fn, **params):
    p = {k: v for k, v in params.items() if v not in (None, "")}
    r = requests.get(f"{API}/api/{fn}", params=p, headers=UA, timeout=30)
    r.raise_for_status()
    d = r.json()
    if isinstance(d, dict) and d.get("error"):
        raise RuntimeError(d["error"])
    return d


def _row(r):
    """搜尋結果列瘦身。"""
    out = {"title": r.get("title"), "date": r.get("date"),
           "type": r.get("type"), "unit_name": r.get("unit_name"),
           "unit_id": r.get("unit_id"), "job_number": r.get("job_number")}
    if r.get("budget"):
        out["budget"] = r["budget"]
    if r.get("award_amount"):
        out["award_amount"] = r["award_amount"]
    if r.get("deadline"):
        out["deadline"] = r["deadline"]
    w = r.get("winners")
    if w:
        out["winners"] = w if isinstance(w, list) else w
    return out


@mcp.tool()
def search_tenders(q: str = "", kind: str = "", region: str = "",
                   year: int = 0, unit_id: str = "", vendor: str = "",
                   budget_min: int = 0, budget_max: int = 0,
                   page: int = 1) -> dict:
    """搜尋政府標案公告。

    q: 關鍵字（比對標題與機關名，例「冷氣」「智慧路燈」）。
    kind: tender=招標中 / award=已決標 / failed=流標，空=全部。
    region: 縣市（例「台北市」「高雄市」，「臺」寫成「台」）。
    year: 西元年（例 2026）。
    unit_id: 機關代碼（用 find_entity 取得）——查「某機關發的案」用這個，
             比 q 精確（q 是全文比對）。
    vendor: 廠商名稱（正式全名）——查該廠商投標／得標過的案。
    budget_min/budget_max: 預算金額範圍（新台幣元）。
    回傳最新 10 筆與總數；需要更多用 page 翻頁。
    """
    d = _get("search", q=q, kind=kind, region=region,
             year=year or None, unit_id=unit_id, vendor=vendor,
             budget_min=budget_min or None, budget_max=budget_max or None,
             page=page, size=10, lite=1, sort="date")
    return {"total": d.get("total"), "page": page,
            "results": [_row(r) for r in (d.get("results") or [])[:10]],
            "web": f"{SITE}/?q={q}" if q else SITE}


@mcp.tool()
def get_tender(unit_id: str, job_number: str) -> dict:
    """單一標案的完整歷程：招標→決標的每則公告、預算與決標金額、
    得標廠商、競爭態勢（幾家投標／是否單一投標）、是否為續約案。
    unit_id 與 job_number 來自 search_tenders 的結果列。"""
    d = _get("case", unit_id=unit_id, job_number=job_number)
    events = [{"date": e.get("date"), "type": e.get("type")}
              for e in (d.get("events") or [])][:15]
    out = {"title": d.get("title"), "unit_name": d.get("unit_name"),
           "budget": d.get("budget"), "award_amount": d.get("award_amount"),
           "deadline": d.get("deadline"), "won": (d.get("won") or [])[:5],
           "failed_times": d.get("retries") or 0, "events": events,
           "web": f"{SITE}/?case={unit_id}|{job_number}"}
    c = d.get("compete")
    if c:
        out["compete"] = {"bidders": c.get("bidders"),
                          "sole_bid": bool(c.get("sole"))}
    inc = d.get("incumbent")
    if inc:
        out["incumbent"] = {"streak": inc.get("streak"),
                            "last_winner": inc.get("last_winner"),
                            "note": "此案連年由同一廠商得標"}
    return out


@mcp.tool()
def price_analysis(unit_id: str, job_number: str) -> dict:
    """底價分析：這個案子大概會以多少錢成交。
    依歷史「決標／預算比」給三檔出價建議（保守／典型／積極），
    比較基準依樣本充足度自動選：相似案（標題關鍵詞比對）＞同機關＞同類別＞全庫。
    適合在使用者問「這案該報多少」「值不值得投」時使用。"""
    d = _get("bargain", unit_id=unit_id, job_number=job_number)
    out = {"title": d.get("title"), "budget": d.get("budget"),
           "basis": (d.get("ref") or {}).get("scope"),
           "typical_ratio_pct": (d.get("ref") or {}).get("median")}
    imp = d.get("implied")
    if imp:
        out["suggested_bid"] = {"conservative": imp.get("p75"),
                                "typical": imp.get("median"),
                                "aggressive": imp.get("p25"),
                                "note": "保守=競爭少時可試；積極=想搶下來要到這"}
    for key, label in (("sim_stats", "similar_cases"),
                       ("unit_stats", "this_unit"), ("all_stats", "all_db")):
        s = d.get(key)
        if s:
            out[label] = {"median_pct": s.get("median"), "p25": s.get("p25"),
                          "p75": s.get("p75"), "n": s.get("n")}
    if d.get("award_amount"):
        out["actual_award"] = d["award_amount"]
    return out


@mcp.tool()
def vendor_report(name: str) -> dict:
    """廠商情報報告：得標率、已知得標總額、最大客戶、單一投標比例
    （開標時只有它一家的案子占比，全庫平均 50.1%）、最常交手的對手與相對勝率、
    近期得標與「近期輸給誰」。name 必須是正式全名（先用 find_entity 查）。
    適合分析競爭對手或盡職調查。"""
    d = _get("vendor_report", name=name)
    out = {"name": d.get("name"), "tax_id": d.get("vid"),
           "participations": d.get("participations"), "wins": d.get("wins"),
           "win_rate_pct": d.get("win_rate"),
           "known_award_total": (d.get("money") or {}).get("total_award"),
           "sole_bid_rate_pct": d.get("sole_rate"),
           "web": f"{SITE}/?vendor={name}"}
    out["top_clients"] = [{"unit": c.get("unit_name"), "wins": c.get("wins"),
                           "amount": c.get("amount")}
                          for c in (d.get("top_clients") or [])[:5]]
    out["main_categories"] = [{"category": c[0], "n": c[1]}
                              for c in (d.get("cats") or [])[:3]]
    out["top_rivals"] = [{"name": r.get("name"), "met": r.get("met"),
                          "this_vendor_wins": r.get("my_wins"),
                          "rival_wins": r.get("their_wins")}
                         for r in (d.get("rivals") or [])[:5]]
    out["recent_losses"] = [{"date": x.get("date"), "title": x.get("title"),
                             "lost_to": x.get("winner"),
                             "award_amount": x.get("award_amount")}
                            for x in (d.get("lost_recent") or [])[:5]]
    r = d.get("ratio")
    if r and r.get("median") is not None:
        out["award_to_budget_median_pct"] = r["median"]
    return out


@mcp.tool()
def unit_report(unit: str) -> dict:
    """機關情報報告：發包規模與金額、主要供應商、供應商集中度、
    競爭程度（平均投標家數／單一投標率／流標率）、發案旺月，以及
    「固定週期標案」——每年重複招標的案與**預估下次發案時間**。
    unit 可以是機關代碼（如 3.76.54）或機關全名（會自動查代碼）。
    適合回答「這個機關好不好投」「它什麼時候會再發案」。"""
    uid = unit.strip()
    if not uid.replace(".", "").replace("-", "").isdigit():
        lk = _get("lookup", q=uid)
        units = lk.get("units") or []
        hit = next((u for u in units if u.get("unit_name") == uid), None) or \
            (units[0] if units else None)
        if not hit:
            raise RuntimeError(f"找不到機關：{unit}（用 find_entity 先查正式名稱）")
        uid = hit["unit_id"]
    d = _get("unit_report", unit_id=uid)
    out = {"unit_name": d.get("unit_name"), "unit_id": uid,
           "total_notices": d.get("total"),
           "fail_rate_pct": d.get("fail_rate"),
           "avg_bidders": d.get("avg_bidders"),
           "sole_bid_rate_pct": d.get("sole_rate"),
           "top5_vendor_share_pct": d.get("top5_share"),
           "known_award_total": (d.get("money") or {}).get("total_award"),
           "web": f"{SITE}/?unit={uid}"}
    md = d.get("month_dist")
    if md:
        avg = sum(md) / 12 or 1
        out["peak_months"] = [i + 1 for i, v in enumerate(md) if v > avg * 1.3]
    out["top_vendors"] = [{"name": v.get("name"), "wins": v.get("wins"),
                           "amount": v.get("amount")}
                          for v in (d.get("top_vendors") or [])[:5]]
    out["recurring_cases"] = [
        {"title": x.get("title"), "consecutive_wins": x.get("streak"),
         "last_winner": x.get("last_winner"),
         "next_expected": (f"{x['next_y']} 年 {x['next_m']} 月前後"
                           if x.get("next_y") else None)}
        for x in (d.get("incumbents") or [])[:6]]
    r = d.get("ratio")
    if r and r.get("median") is not None:
        out["award_to_budget_median_pct"] = r["median"]
    return out


@mcp.tool()
def compare_vendors(vendor_a: str, vendor_b: str) -> dict:
    """兩家廠商的同場對戰紀錄：交手幾次、各贏幾次。
    兩個名稱都要是正式全名（先用 find_entity 查）。
    適合回答「A 跟 B 誰比較強」「我常輸給誰」。"""
    d = _get("vendor_report", name=vendor_a)
    rivals = d.get("rivals") or []
    hit = next((r for r in rivals
                if r.get("name") == vendor_b
                or vendor_b in (r.get("name") or "")
                or (r.get("name") or "") in vendor_b), None)
    if not hit:
        return {"vendor_a": vendor_a, "vendor_b": vendor_b,
                "met": 0,
                "note": ("近期同場紀錄中沒有交手（統計取 A 最近數千次投標的同場對手；"
                         "沒交手通常代表市場或地區不重疊）"),
                "a_top_rivals": [r.get("name") for r in rivals[:5]]}
    return {"vendor_a": vendor_a, "vendor_b": vendor_b,
            "met": hit.get("met"),
            "a_wins": hit.get("my_wins"), "b_wins": hit.get("their_wins"),
            "note": "同場=兩家投同一個案；勝場=該場由誰得標"}


@mcp.tool()
def hot_opportunities() -> dict:
    """流標機會：反覆流標、至今未決標的案子——競爭者少、機關急著發包，
    是新廠商切入的好標的。回傳最新 10 筆。"""
    d = _get("hot", min=2)
    return {"note": "這些案子已流標 2 次以上且尚未決標，通常會放寬條件重招",
            "results": [{"title": r.get("title"), "unit_name": r.get("unit_name"),
                         "failed_times": r.get("fails"),
                         "budget": r.get("budget"),
                         "last_date": r.get("last"),
                         "unit_id": r.get("unit_id"),
                         "job_number": r.get("job_number")}
                        for r in (d.get("cases") or [])[:10]]}


@mcp.tool()
def find_entity(q: str) -> dict:
    """用不完整的名稱找機關或廠商的正式名稱與代碼。
    例：輸入「台電」找台灣電力公司相關、「北市府」找臺北市政府相關。
    vendor_report / unit_report / compare_vendors 需要正式名稱，先用這個查。"""
    d = _get("lookup", q=q)
    return {"vendors": [{"name": v.get("name"), "wins": v.get("wins"),
                         "records": v.get("records")}
                        for v in (d.get("vendors") or [])[:8]],
            "units": [{"unit_name": u.get("unit_name"),
                       "unit_id": u.get("unit_id"),
                       "notices": u.get("records")}
                      for u in (d.get("units") or [])[:8]]}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
