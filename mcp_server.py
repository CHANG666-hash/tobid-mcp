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
        "另有官網查詢頁資料（每日更新）：採購預告（procurement_forecast，招標前 1～3 個月的預告）、"
        "公開閱覽（public_reading）、廠商拒絕往來與 101 條停權紀錄（vendor_compliance）、"
        "採購評選委員（evaluation_committee／committee_member／search_committee_members／"
        "unit_committee／vendor_committee）、財物變賣出租（asset_sales）。"
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
    比較基準依樣本充足度自動選：相似案（標題關鍵詞比對）＞同機關＞同細類＞同大類＞全庫。
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
                       ("unit_stats", "this_unit"), ("fine_stats", "this_category"),
                       ("all_stats", "all_db")):
        s = d.get(key)
        if s:
            out[label] = {"median_pct": s.get("median"), "p25": s.get("p25"),
                          "p75": s.get("p75"), "n": s.get("n")}
            if s.get("label"):
                out[label]["category"] = s["label"]
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



# ---------------------------------------------------------------- 官網查詢頁資料（extra.db，每日更新）

@mcp.tool()
def procurement_forecast(q: str = "", unit: str = "", limit: int = 20) -> dict:
    """採購預告：機關在正式招標前公布的「幾月要招、預算多少」，通常早 1～3 個月，
    是唯一能搶在公告前準備的來源。q 篩標案名稱或機關，unit 給機關代碼（含下級機關）。
    回傳預定招標年月、預定預算、招標方式、履約地點與官網連結。"""
    d = _get("predict", q=q, unit_id=unit, upcoming=1, size=min(max(limit, 1), 50))
    return {"total": d.get("total"),
            "items": [{"tender_month": x.get("tender_ym"), "title": x.get("title"),
                       "unit_name": x.get("unit_name"), "unit_id": x.get("unit_id"),
                       "case_no": x.get("case_no"), "tender_way": x.get("tender_way"),
                       "budget": x.get("budget"), "deadline_month": x.get("deadline_ym"),
                       "category": x.get("category"), "location": x.get("location"),
                       "official_url": x.get("url")} for x in d.get("items") or []],
            "web": f"{SITE}/?tab=predict" + (f"&q={q}" if q else "")}


@mcp.tool()
def public_reading(q: str = "", unit: str = "", limit: int = 20) -> dict:
    """公開閱覽：招標文件草案公開徵求廠商意見的案件（閱覽期內），
    廠商可在意見截止日前向機關提出規格或資格意見。q 篩標案或機關，unit 給機關代碼。"""
    d = _get("tpread", q=q, unit_id=unit, size=min(max(limit, 1), 50))
    return {"total": d.get("total"),
            "items": [{"reading_period": f"{x.get('period_start')} – {x.get('period_end')}",
                       "opinion_deadline": x.get("opinion_deadline"), "title": x.get("title"),
                       "unit_name": x.get("unit_name"), "unit_id": x.get("unit_id"),
                       "case_no": x.get("case_no"), "tender_way": x.get("tender_way"),
                       "amount_range": x.get("amount_range"),
                       "summary": (x.get("summary") or "")[:200], "official_url": x.get("url")}
                      for x in d.get("items") or []],
            "web": f"{SITE}/?tab=tpread"}


@mcp.tool()
def vendor_compliance(name: str) -> dict:
    """廠商的政府採購法第 101 條相關紀錄：拒絕往來（生效中／期滿）、註銷拒絕往來、
    停權案例（含申訴結果）。name 必須是正式全名。全部為政府電子採購網公告的事實，
    請附來源並註明「停權案例含申訴審議中或已撤銷者，以官網記載的救濟結果為準」。
    拒絕往來期間依第 103 條不得參加投標或作為決標對象或分包廠商。"""
    d = _get("blacklist", name=name)
    return {"name": name, "currently_debarred": d.get("active", 0) > 0,
            "debarments": [{"status": "生效中" if r.get("active") else "已期滿",
                            "unit_name": r.get("unit_name"), "title": r.get("title"),
                            "reason": r.get("reason"), "effective": r.get("effective"),
                            "end_date": r.get("end_date"), "period": r.get("period"),
                            "appeal": r.get("appeal")} for r in d.get("rvlm") or []],
            "revoked": [{"unit_name": r.get("unit_name"), "title": r.get("title"), "note": r.get("note")}
                        for r in d.get("revoked") or []],
            "article_101_cases": [{"source": r.get("src"), "unit_name": r.get("unit_name"),
                                   "title": r.get("title"), "clause": r.get("clause"),
                                   "dispute": r.get("dispute"), "relief": r.get("relief")}
                                  for r in d.get("oneoone") or []],
            "sources": d.get("sources"), "updated": d.get("updated"),
            "web": f"{SITE}/?vendor={name}"}


_MEMBER_NOTE = ("評選由全體委員合議、結果經機關核定；以下為政府電子採購網公開名單與決標公告的事實彙整，"
                "不代表個別委員對結果的影響。同名可能為不同人，請對照現職與學經歷。")


@mcp.tool()
def evaluation_committee(unit_id: str, job_number: str) -> dict:
    """某一案的採購評選委員名單（機關公開者）：姓名、現職、與本案相關學經歷。
    未公開時回傳機關的說明。回答時請附上合議制聲明。"""
    d = _get("committee", unit_id=unit_id, job_number=job_number)
    items = d.get("items") or []
    if not items:
        return {"found": False, "note": "此案在政府電子採購網沒有評選委員名單（可能非評選案、或尚未傳輸）"}
    it = items[0]
    return {"found": True, "title": it.get("title"), "unit_name": it.get("unit_name"),
            "is_public": it.get("is_public") == "是", "public_note": it.get("public_note"),
            "transmitted_at": it.get("transmitted_at"),
            "members": [{"name": m.get("評選委員姓名"), "job": m.get("評選委員職業"),
                         "background": (m.get("與採購案相關之學經歷") or "")[:200]}
                        for m in it.get("members") or []],
            "note": _MEMBER_NOTE, "web": f"{SITE}/?case={unit_id}%7C{job_number}"}


@mcp.tool()
def committee_member(name: str) -> dict:
    """採購評選委員個人紀錄：評選案數、資料期間、現職版本、常評選的機關、類別比例、
    常一起出現的委員、評選案的得標廠商彙整、決標／預算比（基準為全部評選案）與最近案件。
    姓名要完整；不確定時先用 search_committee_members。回答時請附合議制聲明。"""
    try:
        d = _get("member", name=name)
    except RuntimeError as e:
        if "查無" in str(e):
            return {"found": False, "hint": "找不到這個姓名，請先用 search_committee_members 找正確全名"}
        raise
    r = d.get("ratio") or {}
    b = d.get("ratio_base") or {}
    return {"name": d.get("name"), "cases": d.get("n"), "awarded_cases": d.get("awarded_n"),
            "first_date": d.get("first_date"), "last_date": d.get("last_date"),
            "jobs": [{"job": j[0], "cases": j[1]} for j in d.get("jobs") or []],
            "backgrounds": [x[0][:200] for x in d.get("backgrounds") or []][:2],
            "frequent_units": [{"unit_name": u[0], "cases": u[1]} for u in (d.get("units") or [])[:6]],
            "categories": [{"category": c[0], "cases": c[1]} for c in d.get("cats") or []],
            "co_members": [{"name": c[0], "cases": c[1]} for c in (d.get("co_members") or [])[:8]],
            "top_winners": [{"vendor": w[0], "wins": w[1]} for w in (d.get("top_winners") or [])[:8]],
            "award_to_budget": ({"cases": r.get("n"), "at_budget_pct": r.get("at_budget"),
                                 "discounted_pct": r.get("cut_share"), "discounted_mean_pct": r.get("cut_mean"),
                                 "baseline_all_evaluated_cases_at_budget_pct": b.get("at_budget")} if r else None),
            "recent_cases": [{"date": c.get("date"), "title": c.get("title"), "unit_name": c.get("unit_name"),
                              "unit_id": c.get("unit_id"), "case_no": c.get("case_no"),
                              "award": c.get("award"), "winners": c.get("winners")}
                             for c in (d.get("cases") or [])[:10]],
            "note": _MEMBER_NOTE, "web": f"{SITE}/?member={name}"}


@mcp.tool()
def search_committee_members(q: str) -> dict:
    """用姓名、現職或機關名稱找採購評選委員；回傳評選案數最多的前幾位。"""
    d = _get("member_search", q=q)
    return {"members": [{"name": m.get("name"), "cases": m.get("n"),
                         "job": (m.get("jobs") or [["", 0]])[0][0],
                         "frequent_units": [u[0] for u in (m.get("units") or [])[:3]]}
                        for m in (d.get("items") or [])[:15]],
            "database_members": d.get("members")}


@mcp.tool()
def unit_committee(unit: str) -> dict:
    """機關常找的評選委員：席次數、占比與前 5 位集中度（40% 以上代表委員圈子相對固定）。
    unit 為機關代碼（先用 find_entity 查）。"""
    d = _get("unit_committee", unit_id=unit)
    return {"unit_id": unit, "evaluated_cases": d.get("cases"), "public_cases": d.get("public_cases"),
            "seats": d.get("seats"), "top5_share_pct": d.get("top5_share"),
            "members": [{"name": m.get("name"), "seats": m.get("n"), "share_pct": m.get("share"), "job": m.get("job")}
                        for m in (d.get("members") or [])[:10]],
            "note": _MEMBER_NOTE}


@mcp.tool()
def vendor_committee(name: str) -> dict:
    """廠商投過且有公開名單的案子裡最常遇到的評選委員：同案次數、其中得標次數，
    並附該廠商整體得標率作為基準。name 必須是正式全名。回答時請附合議制聲明，
    不要推論委員與廠商之間的關係。"""
    d = _get("vendor_committee", name=name)
    rec, w = d.get("overall_records") or 0, d.get("overall_wins") or 0
    return {"name": name, "evaluated_cases_bid": d.get("eval_cases"), "evaluated_cases_won": d.get("eval_wins"),
            "overall_win_rate_pct": round(w * 100 / rec, 1) if rec else None,
            "members": [{"name": m.get("name"), "job": m.get("job"), "met": m.get("met"), "won": m.get("won")}
                        for m in (d.get("members") or [])[:10]],
            "note": _MEMBER_NOTE}


@mcp.tool()
def asset_sales(q: str = "", kind: str = "sell", open_only: bool = True, limit: int = 20) -> dict:
    """公家機關財物變賣（kind=sell）或出租（kind=rent）公告：車輛、設備、廢料、場地、攤位等。
    q 篩財物名稱或機關；open_only 只列還沒截止的。回傳公告日、截止日、底價、開標時間、標的所在地與官網連結。"""
    d = _get("assets", q=q, kind=kind, open=1 if open_only else "", size=min(max(limit, 1), 50))
    return {"total": d.get("total"), "kind": d.get("kind"),
            "items": [{"asset": x.get("asset_name"), "unit_name": x.get("unit_name"), "case_no": x.get("case_no"),
                       "notice_date": x.get("notice_date"), "deadline": x.get("deadline"),
                       "floor_price": x.get("price"), "bid_opening": x.get("method"), "location": x.get("location"),
                       "deposit": x.get("deposit"),
                       "official_url": x.get("url")} for x in d.get("items") or []],
            "web": f"{SITE}/?tab=assets"}


if __name__ == "__main__":
    # 預設 stdio（本地執行、Docker、Glama 檢查器都用這個）；
    # 生產部署（pcc-mcp.service）以環境變數切成 streamable-http。
    mcp.run(transport=os.environ.get("MCP_TRANSPORT", "stdio"))
