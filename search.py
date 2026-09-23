# -*- coding: utf-8 -*-
"""
train-plan 图搜索: 在铁路走廊图上枚举 直达 / 中转 / 买长乘短 / 买短乘长 方案
用法示例:
  python search.py --from-city 上海 --to-city 武汉 --date YYYY-MM-DD --after 18:00 \
      --arrive-by "YYYY-MM-DD 12:00" --people 1 --budget 800 --out report.html
约束: 受 --max-queries 限制(防风控), lib12306 自带限速+缓存。
"""
import argparse, datetime as dt, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib12306 as L
import fares
from coords import coord_of

HERE = os.path.dirname(os.path.abspath(__file__))
SEATS = ("sw", "zy", "ze", "yw", "yz", "rw", "gr", "wz")
SEAT_CN = {"sw": "商务座", "zy": "一等座", "ze": "二等座", "yw": "硬卧", "yz": "硬座",
           "rw": "软卧", "gr": "高级软卧", "wz": "无座"}
SEAT_COMFORT = {"sw": 1.0, "gr": 0.8, "zy": 0.6, "rw": 0.5, "yw": 0.3, "ze": 0.2, "yz": -0.6, "wz": -1.8}
BUDGET = {"n": 0}
PRICE_CACHE = {}

def qbudget(max_q):
    BUDGET["n"] += 1
    if BUDGET["n"] > max_q:
        raise RuntimeError("查询预算(%d)用尽, 已基于当前数据出报告" % max_q)

def tickets(date, frm, to, max_q):
    qbudget(max_q)
    return L.tickets(date, frm, to)

def sched(train_no, frm, to, date, max_q):
    qbudget(max_q)
    return L.schedule(train_no, frm, to, date)

def seat_val(v):
    return None if v in ("", "无") else ("候补" if v == "候补" else v)

def row_seats(r):
    return {k: seat_val(r[k]) for k in SEATS if r.get(k) not in (None, "", "无", "候补", "0", 0)}

def has_seat(r, classes=("ze", "yw", "yz", "rw", "zy", "sw", "gr", "wz")):
    return r["buy"] == "Y" and any(r.get(k) not in (None, "", "无", "候补", "0", 0) for k in classes)

def parse_hhmm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)

def lishi_min(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)

def dep_dt(date, hhmm):
    d = dt.date.fromisoformat(date)
    mins = parse_hhmm(hhmm)
    return dt.datetime.combine(d, dt.time()) + dt.timedelta(minutes=mins)

def corridor_hubs(o_city, d_city, cap=14):
    """用站点坐标挑出 O→D 走廊带内的候选枢纽: 按城市去重(优先 东 站), 离目的地由近到远"""
    import coords as C
    a, b = C.coord_of(o_city), C.coord_of(d_city)
    if not a or not b:
        return []
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return []
    cand = []
    for st, (x, y) in C.COORDS.items():
        t = ((x - ax) * dx + (y - ay) * dy) / L2
        if not (0.06 <= t <= 0.97):
            continue
        px, py = ax + t * dx, ay + t * dy
        if (x - px) ** 2 + (y - py) ** 2 < 1.2 ** 2:
            city = next((c for c in C.CITY_FALLBACK if st.startswith(c)), st[:2])
            cand.append((t, city, st))
    best = {}
    for t, city, st in sorted(cand, key=lambda kv: -kv[0]):
        if city in best:
            continue
        def pref(suffix):
            m = [s for tt, c, s in cand if c == city and s.endswith(suffix)]
            return m[0] if m else None
        best[city] = pref("东") or pref("南") or pref("北") or st
    return [best[c] for c in sorted(best, key=lambda c: -max(t for t, cc, s in cand if cc == c))][:cap]

def arr_dt(dep, lishi):
    return dep + dt.timedelta(minutes=lishi)

# ---------- 城市展开 ----------
def load_city_stations():
    raw = L.station_data_text()
    by_city = {}
    for chunk in raw.split("@")[1:]:
        f = chunk.split("|")
        if len(f) >= 8 and f[2]:
            by_city.setdefault(f[7], []).append((f[1], f[2]))
    return by_city

def primary_station(stations):
    # 城市 主站: 与城市同名 > 东 > 南 > 第一个
    for suf in ("", "东", "南"):
        for name, code in stations:
            if name.endswith(suf) and (suf or name == name):
                if suf == "" or True:
                    pass
    name0, code0 = stations[0]
    for suf in ("东", "南"):
        for name, code in stations:
            if name.endswith(suf):
                return name, code
    return name0, code0

# ---------- 方案构造 ----------
def leg_info(r, date):
    return {
        "date": date, "train": r["code"], "train_no": r["train_no"],
        "from": r["from"], "from_cn": L.STATION.get(r["from"], r["from"]),
        "to": r["to"], "to_cn": L.STATION.get(r["to"], r["to"]),
        "dep": r["dep"], "arr": r["arr"], "lishi": r["lishi"],
        "seats": {SEAT_CN[k]: v for k, v in row_seats(r).items() if v},
        "qfrom": r["qfrom"], "qto": r["qto"], "seat_types": r["seat_types"],
    }

def make_plan(ptype, legs, dates, notes=(), buy_short_info=None, ext_info=None):
    dep0 = dep_dt(dates[0], legs[0]["dep"])
    arrN = arr_dt(dep_dt(dates[-1], legs[-1]["dep"]), lishi_min(legs[-1]["lishi"]))
    transfers = []
    for i in range(len(legs) - 1):
        a = arr_dt(dep_dt(dates[i], legs[i]["dep"]), lishi_min(legs[i]["lishi"]))
        b = dep_dt(dates[i + 1], legs[i + 1]["dep"])
        buf = int((b - a).total_seconds() // 60)
        same = legs[i]["to"] == legs[i + 1]["from"]
        transfers.append({"station": L.STATION.get(legs[i]["to"], legs[i]["to"]),
                          "buffer_min": buf, "same_station": same})
        if buf < 0:
            return None
    return {"type": ptype, "legs": legs, "dates": dates, "transfers": transfers,
            "dep_dt": dep0.isoformat(sep=" "), "arr_dt": arrN.isoformat(sep=" "),
            "duration_min": int((arrN - dep0).total_seconds() // 60),
            "notes": list(notes), "buy_short": buy_short_info, "ext": ext_info,
            "price_pp": None, "prices": [], "comfort": None}

def comfort_score(plan, people):
    c = 7.0
    for leg in plan["legs"]:
        dur_share = lishi_min(leg["lishi"]) / max(plan["duration_min"], 1)
        inv = {v: k for k, v in SEAT_CN.items()}
        best = max([SEAT_COMFORT.get(inv.get(s), -0.5) for s, v in leg["seats"].items()], default=-1.5)
        c += best * dur_share * 1.6
        if "无座" in leg["seats"]:
            c -= 1.0 * lishi_min(leg["lishi"]) / 60.0 * dur_share
    for t in plan["transfers"]:
        c -= 1.0
        if t["buffer_min"] < 20: c -= 1.0
        if not t["same_station"]: c -= 0.5
    if plan["arr_dt"][11:16] <= "06:30": c -= 1.0
    return round(max(0.0, min(10.0, c)), 1)

PRICE_KEY = {"商务座": ("A9",), "一等座": ("M",), "二等座": ("O",), "硬座": ("A1",),
             "硬卧": ("A3",), "软卧": ("A4",), "高级软卧": ("A6",), "无座": ("WZ",), "动卧": ("F",)}

def _price_for_available(d_price, seats_avail):
    """仅用有余票席别的票价；接口缺少对应席别时保持未知。"""
    if not isinstance(d_price, dict):
        return None
    candidates = []
    for name, available in seats_avail.items():
        if available in (None, "", "无", "候补", "0", 0):
            continue
        for key in PRICE_KEY.get(name, ()):
            value = d_price.get(key)
            try:
                number = float(str(value).strip().replace("¥", "").replace("￥", ""))
            except (TypeError, ValueError):
                continue
            if number > 0:
                candidates.append(number)
    return min(candidates) if candidates else None

def price_legs(plan, date_keys, max_q):
    """按每段【实际可买席别】取价; 单段失败重试(绕缓存); 全成才算有价"""
    total = 0.0
    ok = True
    for leg in plan["legs"]:
        key = (leg["train_no"], leg["qfrom"], leg["qto"], leg["seat_types"], leg["date"], tuple(sorted(leg["seats"].items())))
        p = PRICE_CACHE.get(key)
        for attempt in range(0 if p is not None else 2):
            try:
                if attempt == 0:
                    qbudget(max_q)
                    d = L.price(leg["train_no"], leg["qfrom"], leg["qto"], leg["seat_types"], leg["date"])
                else:
                    time.sleep(1.2)
                    qbudget(max_q)
                    url = (L.BASE + "/otn/leftTicket/queryTicketPrice?train_no=%s&from_station_no=%s"
                           "&to_station_no=%s&seat_types=%s&train_date=%s"
                           % (leg["train_no"], leg["qfrom"], leg["qto"], leg["seat_types"], leg["date"]))
                    d = L.http_json(url, ttl=0, label="票价重试 " + leg["train_no"]).get("data")
                if d:
                    p = _price_for_available(d, leg["seats"])
            except RuntimeError:
                ok = False
                break
            if p is not None:
                break
        if p is None:
            ok = False
            continue
        leg["price"] = p
        PRICE_CACHE[key] = p
        total += p
    if ok and total > 0 and not plan.get("buy_short"):
        plan["price_pp"] = round(total, 1)
    plan["prices"] = [leg.get("price") for leg in plan["legs"]]
    return plan

# ---------- 主搜索 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-city", required=True)
    ap.add_argument("--to-city", required=True)
    ap.add_argument("--date", required=True, help="最早出发日期 YYYY-MM-DD")
    ap.add_argument("--after", default="00:00", help="最早可出发时刻 HH:MM")
    ap.add_argument("--arrive-by", required=True, help="到达截止 'YYYY-MM-DD HH:MM'")
    ap.add_argument("--people", type=int, default=1)
    ap.add_argument("--budget", type=float, default=None, help="单人预算(元)")
    ap.add_argument("--max-transfers", type=int, default=3)
    ap.add_argument("--max-queries", type=int, default=100)
    ap.add_argument("--max-hubs", type=int, default=10)
    ap.add_argument("--out", default="report.html")
    a = ap.parse_args()

    by_city = load_city_stations()
    if a.from_city not in by_city or a.to_city not in by_city:
        print("!! 城市不在站表中:", a.from_city, a.to_city); sys.exit(1)
    O = by_city[a.from_city]; D = by_city[a.to_city]
    (o_name, o_code), (d_name, d_code) = primary_station(O), primary_station(D)
    next_day = (dt.date.fromisoformat(a.date) + dt.timedelta(days=1)).isoformat()
    windows = [(a.date, a.after, "23:59"), (next_day, "00:00", "23:59")]  # 出发日+次日全天, 由 arrive-by 兜底过滤
    deadline = dt.datetime.fromisoformat(a.arrive_by)
    plans = []
    network_rows = {}
    def query_edge(day, frm, to):
        key = (day, frm, to)
        if key not in network_rows:
            network_rows[key] = tickets(day, frm, to, a.max_queries)
        return network_rows[key]

    def in_window(date, dep, arrive_by_dt=None):
        return dep_dt(date, dep)

    # ---- 0. 直达 ----
    print(">> 直达扫描 %s(%s)→%s(%s)" % (o_name, o_code, d_name, d_code))
    direct_rows = []
    for w_date, w_from, w_to in windows:
        rows = query_edge(w_date, o_code, d_code)
        for r in rows:
            if w_from <= r["dep"] <= w_to:
                r2 = dict(r); r2["_date"] = w_date
                direct_rows.append(r2)
    for r in direct_rows:
        if r["dep"] < a.after and r["_date"] == a.date: continue
        dep = dep_dt(r["_date"], r["dep"])
        if dep < dt.datetime.combine(dt.date.fromisoformat(a.date), dt.time()) + dt.timedelta(minutes=parse_hhmm(a.after)): continue
        arr = arr_dt(dep, lishi_min(r["lishi"]))
        if arr > deadline: continue
        if has_seat(r):
            plans.append(make_plan("直达", [leg_info(r, r["_date"])], [r["_date"]]))
    print("   直达可行: %d" % len(plans))

    # ---- 中转 hub 采集: 时刻表中间站 + 坐标走廊内插(双保险, 不依赖单一数据源) ----
    hub_freq = {}
    sample = sorted(direct_rows, key=lambda r: lishi_min(r["lishi"]))[:6]
    for r in sample:
        try:
            stops = sched(r["train_no"], r["from"], r["to"], r["_date"], a.max_queries)
        except Exception:
            continue
        seq = [s["station"] for s in stops]
        try:
            i0 = seq.index(r["from"]); i1 = seq.index(r["to"])
        except ValueError:
            continue
        for h in seq[i0 + 1: i1]:
            hub_freq[h] = hub_freq.get(h, 0) + 1
    sched_hubs = [h for h, _ in sorted(hub_freq.items(), key=lambda kv: -kv[1])]
    geo_hubs = corridor_hubs(a.from_city, a.to_city)
    # 目的地侧枢纽必须保留(拆分段最有价值), 再补时刻表高频枢纽, 再补其余地理枢纽
    merged = list(dict.fromkeys(list(geo_hubs[:3]) + sched_hubs + list(geo_hubs[3:])))[: max(a.max_hubs, 6)]
    hubs = merged
    print(">> 候选中转枢纽:", hubs)

    if a.max_transfers >= 2:
        # 一次性建立走廊边集: 出发站->每个枢纽、每个枢纽->到达站、枢纽间相邻走廊。
        # 一程中转只依赖前两类边, 必须无条件覆盖; 枢纽间边支持多次换乘, 预算不足时靠后截断。
        hub_codes = [L.NAME[h] for h in hubs if h in L.NAME]
        corridor = list(reversed(hub_codes))  # 按出发→到达方向排列
        edges, seen_edges = [], set()

        def add_edge(src, dst):
            if src != dst and (src, dst) not in seen_edges:
                seen_edges.add((src, dst))
                edges.append((src, dst))

        for h in hub_codes:
            add_edge(o_code, h)
            add_edge(h, d_code)
        for idx, src in enumerate(corridor):
            for dst in corridor[idx + 1: idx + 4]:
                add_edge(src, dst)
        adjacency = {code: [] for code in set([o_code, d_code] + hub_codes)}
        for src, dst in edges:
            if BUDGET["n"] >= a.max_queries - 20: break
            for day, low, high in windows:
                try:
                    rows = query_edge(day, src, dst)
                except RuntimeError:
                    break
                for row in rows:
                    if has_seat(row) and low <= row["dep"] <= high:
                        depart = dep_dt(day, row["dep"])
                        arrive = arr_dt(depart, lishi_min(row["lishi"]))
                        if arrive <= deadline:
                            adjacency[src].append((row, day, depart, arrive))
        frontier = [(o_code, [], [], None, {o_code})]
        for depth in range(1, a.max_transfers + 2):
            following = []
            for station, legs, dates, prior_arrival, visited in frontier:
                for row, day, depart, arrive in adjacency.get(station, []):
                    if row["from"] != station or row["to"] in visited: continue
                    if prior_arrival is not None and (depart - prior_arrival).total_seconds() < 15 * 60: continue
                    if prior_arrival is None and depart < dep_dt(a.date, a.after): continue
                    leg = leg_info(row, day)
                    path, days = legs + [leg], dates + [day]
                    if row["to"] == d_code:
                        if depth >= 2:
                            plan = make_plan("中转", path, days)
                            if plan: plans.append(plan)
                    elif depth <= a.max_transfers:
                        following.append((row["to"], path, days, arrive, visited | {row["to"]}))
            frontier = following[:5000]
        dedup = {}
        for plan in plans:
            key = tuple((leg["train_no"], leg["from"], leg["to"], leg["date"]) for leg in plan["legs"])
            dedup.setdefault(key, plan)
        plans = list(dedup.values())

    # ---- 1. 一程中转 ----
    tele_O = {c for _, c in O}
    for h in ([] if a.max_transfers >= 2 else hubs):
        h_code = L.NAME.get(h)
        if not h_code: continue
        leg1s, leg2s = [], []
        try:
            for w_date, w_from, w_to in windows:
                for r in query_edge(w_date, o_code, h_code):
                    if w_from <= r["dep"] <= w_to and has_seat(r):
                        r2 = dict(r); r2["_date"] = w_date; leg1s.append(r2)
            for w_date, w_from, w_to in windows:
                for r in query_edge(w_date, h_code, d_code):
                    if w_from <= r["dep"] <= w_to and has_seat(r):
                        r2 = dict(r); r2["_date"] = w_date; leg2s.append(r2)
        except RuntimeError as e:
            print("  预算耗尽于 hub", h); break
        for l1 in leg1s:
            d1 = dep_dt(l1["_date"], l1["dep"]); a1 = arr_dt(d1, lishi_min(l1["lishi"]))
            if a1 > deadline: continue
            buf_need = 15
            for l2 in leg2s:
                d2 = dep_dt(l2["_date"], l2["dep"])
                buf = int((d2 - a1).total_seconds() // 60)
                if buf < buf_need: continue
                if l1["to"] != l2["from"]: continue
                a2 = arr_dt(d2, lishi_min(l2["lishi"]))
                if a2 > deadline: continue
                p = make_plan("中转", [leg_info(l1, l1["_date"]), leg_info(l2, l2["_date"])],
                              [l1["_date"], l2["_date"]])
                if p: plans.append(p)
    print("   一程中转后方案总数: %d" % len(plans))

    # ---- 2. 买短乘长(直达车次的分段拆票+车上补票) ----
    tried = 0
    for r in sorted(direct_rows, key=lambda x: (x["buy"] == "Y", lishi_min(x["lishi"]))):
        if tried >= 5 or BUDGET["n"] >= a.max_queries - 20: break
        if r["buy"] == "Y" and has_seat(r): continue  # 直达本来就有票就不用拆
        try:
            stops = sched(r["train_no"], r["from"], r["to"], r["_date"], a.max_queries)
        except Exception:
            continue
        seq = [s["station"] for s in stops]
        try:
            i0, i1 = seq.index(r["from"]), seq.index(r["to"])
        except ValueError:
            continue
        mids = seq[i0 + 1: i1]
        if not mids: continue
        for split in {mids[-1], mids[len(mids) // 2]}:
            s_code = L.NAME.get(split)
            if not s_code: continue
            try:
                short = tickets(r["_date"], r["from"], s_code, a.max_queries)
            except RuntimeError:
                break
            hit = [x for x in short if x["code"] == r["code"] and x["dep"] == r["dep"] and has_seat(x)]
            if not hit: continue
            x = hit[0]
            leg1 = leg_info(x, r["_date"])
            # 第2段在车上补票(无需票)
            dep = dep_dt(r["_date"], r["dep"]); arr = arr_dt(dep, lishi_min(r["lishi"]))
            if arr > deadline: continue
            p = make_plan("买短乘长", [leg1], [r["_date"]],
                          notes=["%s→%s 区间需车上找列车长补票(无座,按公布票价)" % (split, L.STATION.get(r["to"], r["to"]))],
                          buy_short_info={"split": split, "rest": "%s→%s" % (split, L.STATION.get(r["to"], r["to"]))})
            if p:
                p["arr_dt"] = arr.isoformat(sep=" ")
                p["duration_min"] = int((arr - dep).total_seconds() // 60)
                p["buy_short"]["arrival"] = p["arr_dt"]
                plans.append(p); tried += 1
            break
    print("   买短乘长候选: %d" % sum(1 for p in plans if p["type"] == "买短乘长"))

    # ---- 3. 买长乘短(买到目的地下一站, 提前下车) ----
    tried = 0
    for r in sorted(direct_rows, key=lambda x: lishi_min(x["lishi"])):
        if tried >= 5 or BUDGET["n"] >= a.max_queries - 20: break
        if r["end"] == r["to"]: continue
        try:
            stops = sched(r["train_no"], r["from"], r["to"], r["_date"], a.max_queries)
        except Exception:
            continue
        seq = [s["station"] for s in stops]
        if r["to"] not in seq or seq[-1] == r["to"]: continue
        d_next = seq[seq.index(r["to"]) + 1]
        n_code = L.NAME.get(d_next)
        if not n_code: continue
        try:
            longer = tickets(r["_date"], r["from"], n_code, a.max_queries)
        except RuntimeError:
            break
        hit = [x for x in longer if x["code"] == r["code"] and x["dep"] == r["dep"] and has_seat(x)]
        if not hit: continue
        x = hit[0]
        dep = dep_dt(r["_date"], r["dep"]); arr = arr_dt(dep, lishi_min(r["lishi"]))
        if arr > deadline: continue
        leg = leg_info(x, r["_date"]); leg["alight_cn"] = L.STATION.get(r["to"], r["to"])
        p = make_plan("买长乘短", [leg], [r["_date"]],
                      notes=["票面买到 %s, 在 %s 提前下车(差价不退)" % (d_next, L.STATION.get(r["to"], r["to"]))],
                      ext_info={"beyond": d_next})
        if p:
            p["arr_dt"] = arr.isoformat(sep=" ")
            p["duration_min"] = int((arr - dep).total_seconds() // 60)
            plans.append(p); tried += 1
    print("   买长乘短候选: %d" % sum(1 for p in plans if p["type"] == "买长乘短"))

    def fetch_fare(leg):
        qbudget(a.max_queries)
        return L.price(leg["train_no"], leg["qfrom"], leg["qto"], leg["seat_types"], leg["date"])

    def retry_fare(leg):
        qbudget(a.max_queries)
        url = (L.BASE + "/otn/leftTicket/queryTicketPrice?train_no=%s&from_station_no=%s"
               "&to_station_no=%s&seat_types=%s&train_date=%s"
               % (leg["train_no"], leg["qfrom"], leg["qto"], leg["seat_types"], leg["date"]))
        return L.http_json(url, ttl=0, label="票价重试 " + leg["train_no"]).get("data")

    summary = fares.hydrate(plans, fetch_fare, _price_for_available,
                            a.max_queries - BUDGET["n"],
                            lambda: a.max_queries - BUDGET["n"], retry_fare)
    print("   票价: %d 个唯一票段, %d 次查询, %d/%d 方案完整核价" %
          (summary["unique_legs"], summary["requests"], summary["priced_plans"], len(plans)))
    for p in plans:
        p["comfort"] = comfort_score(p, a.people)
        p["over_budget"] = bool(a.budget is not None and p["price_pp"] is not None
                                and p["price_pp"] > a.budget)
        if p["price_pp"] is None:
            reasons = sorted({leg.get("price_status", "") for leg in p["legs"]
                              if leg.get("price") is None})
            if p.get("buy_short"):
                reasons.append("车上补票区间价格未知")
            p.setdefault("notes", []).append("未能完整核价：" + "、".join(reasons))
    plans.sort(key=lambda p: (p["price_pp"] is None, p["price_pp"] or 9e9))
    result = {"params": vars(a), "from_city": a.from_city, "to_city": a.to_city,
              "plans": plans, "generated_at": dt.datetime.now().isoformat(sep=" ", timespec="seconds")}
    print(">> 方案 %d 个" % len(plans))
    import render
    render.render(result, os.path.abspath(a.out))
    print(">> 报告 →", os.path.abspath(a.out))

if __name__ == "__main__":
    main()
