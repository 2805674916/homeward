# -*- coding: utf-8 -*-
"""
lib12306.py — 12306 查询公共库（脚手架）
设计原则:
  1. 限速: 距上次官方请求至少 MIN_INTERVAL 秒, 绝不并发
  2. 缓存: 响应落盘 .cache/, 余票 TTL 短、时刻表/票价 TTL 长, 重复探索零请求
  3. 退避: 空响应/错误页/限流时按 BACKOFF 指数等待, 连续失败主动抛错让人休息
  4. c_url: 12306 会轮换 leftTicket 路径(queryZ/queryG/...), 按 302/c_url 提示自动跟随
"""
import json, os, subprocess, time, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache")
os.makedirs(CACHE, exist_ok=True)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
BASE = "https://kyfw.12306.cn"
JAR = os.path.join(CACHE, "cookies.txt")
MIN_INTERVAL = 3.0            # 官方接口最小间隔(秒)
BACKOFF = [10, 30, 60, 120]   # 失败退避序列(秒)
TTL_TICKET = 180              # 余票缓存 3 分钟
TTL_PRICE = 600               # 票价缓存 10 分钟
TTL_SCHEDULE = 86400          # 时刻表缓存 1 天

# ---- 站名电报码 ----
def station_data_text():
    path = os.path.join(CACHE, "station_name.js")
    if not os.path.exists(path):
        url = BASE + "/otn/resources/js/framework/station_name.js"
        result = subprocess.run(["curl", "-fsSL", "--max-time", "25", "-A", UA, url],
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode or result.stdout.count("@") < 100:
            raise RuntimeError("无法获取 12306 站名表；请检查网络后重试")
        with open(path, "w", encoding="utf-8") as output:
            output.write(result.stdout)
    with open(path, encoding="utf-8", errors="ignore") as source:
        return source.read()

STATION = {}
NAME = {}

def load_stations():
    if STATION:
        return
    for chunk in station_data_text().split("@")[1:]:
        fields = chunk.split("|")
        if len(fields) >= 3:
            STATION[fields[2]] = fields[1]
    NAME.update({name: code for code, name in STATION.items()})

load_stations()

_last_ts = 0.0
_paths = ["queryG", "queryZ", "query", "queryA", "queryE"]  # 最近已知有效路径优先

def _pace():
    global _last_ts
    w = MIN_INTERVAL - (time.time() - _last_ts)
    if w > 0:
        time.sleep(w)
    _last_ts = time.time()

def _curl(url):
    return subprocess.run(
        ["curl", "-sL", "--max-time", "25", "-A", UA, "-c", JAR, "-b", JAR,
         "-H", "Referer: " + BASE + "/otn/leftTicket/init", url],
        capture_output=True, text=True, encoding="utf-8", errors="replace").stdout

# ---- 缓存 ----
def _cpath(key):
    return os.path.join(CACHE, key + ".json")

def cache_get(key, ttl):
    p = _cpath(key)
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < ttl:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None

def cache_put(key, data):
    with open(_cpath(key), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

# ---- 带限速/退避的单次 GET ----
def http_json(url, ttl=0, label=""):
    """返回解析后的 JSON(dict); 非法响应按退避重试; 全部失败抛 RuntimeError。ttl>0 时走缓存。"""
    key = hashlib.sha1(url.encode()).hexdigest()[:20]
    if ttl:
        c = cache_get(key, ttl)
        if c is not None:
            return c
    last_err = None
    for i, wait in enumerate([0] + BACKOFF):
        if wait:
            print("  [退避 %ds] %s ..." % (wait, label or url[:60]), file=sys.stderr) if False else None
            time.sleep(wait)
        _pace()
        body = _curl(url).strip()
        if not body:
            last_err = "empty"; continue
        if body.lstrip().startswith("<"):
            last_err = "error-page"; continue   # 12306 软限流页
        try:
            j = json.loads(body)
        except Exception:
            last_err = "not-json"; continue
        if isinstance(j, dict) and j.get("c_url"):
            # 路径轮换提示: {"c_url":"leftTicket/queryG"} -> 切换首选路径后重试
            np = j["c_url"].split("/")[-1]
            if np in _paths:
                _paths.remove(np)
            _paths.insert(0, np)
            last_err = "c_url:" + np; continue
        if ttl:
            cache_put(key, j)
        return j
    raise RuntimeError("12306 持续异常(%s), 疑似限流; 请等待几分钟后再试" % last_err)

# ---- 余票 ----
def _ticket_url(date, frm, to, path):
    return (BASE + "/otn/leftTicket/%s?leftTicketDTO.train_date=%s"
            "&leftTicketDTO.from_station=%s&leftTicketDTO.to_station=%s&purpose_codes=ADULT"
            % (path, date, frm, to))

_warmed = False

def warm_session():
    """leftTicket 需要预热会话: 每进程先取一次 init 页, 等 3 秒再查, 否则返回空。"""
    global _warmed
    if _warmed:
        return
    _pace()
    _curl(BASE + "/otn/leftTicket/init")
    time.sleep(3.0)
    _warmed = True

def tickets(date, frm, to):
    """返回解析后的车次列表(list of dict), 已按出发时间排序。同城查询会合并返回, 行内含真实发到站。"""
    warm_session()
    for path in list(_paths):
        try:
            j = http_json(_ticket_url(date, frm, to, path), ttl=TTL_TICKET, label="%s %s->%s" % (date, frm, to))
        except RuntimeError:
            continue
        if isinstance(j, dict) and j.get("status") and isinstance(j.get("data"), dict):
            rows = [parse_row(x) for x in j["data"].get("result", [])]
            rows.sort(key=lambda r: r["dep"])
            return rows
    raise RuntimeError("余票查询失败: %s %s->%s" % (date, frm, to))

def parse_row(line):
    f = line.split("|")
    return {
        "code": f[3], "train_no": f[2],
        "from": f[6], "to": f[7],
        "start": STATION.get(f[4], f[4]), "end": STATION.get(f[5], f[5]),
        "dep": f[8], "arr": f[9], "lishi": f[10], "buy": f[11],
        "sw": f[32], "zy": f[31], "ze": f[30], "yz": f[29], "yw": f[28],
        "wz": f[26], "rw": f[23], "gr": f[21],
        "seat_types": f[35], "qfrom": f[16], "qto": f[17],
    }

def fmt_row(r):
    seats = " ".join("%s:%s" % (k, r[k]) for k in ("sw", "zy", "ze", "yw", "yz", "rw", "gr", "wz") if r[k] != "")
    return ("%-6s %s(%s)->%s(%s) %s~%s 历时%s 可购:%s | %s" %
            (r["code"], r["from"], r["from"], r["to"], r["to"],
             r["dep"], r["arr"], r["lishi"], r["buy"], seats))

# ---- 时刻表 ----
def _int_or_0(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0

def schedule(train_no, frm, to, date):
    """优先 czxx/queryByTrainNo; 失败/为空时回退 queryTrainInfo(两套端点互为备份)"""
    url = (BASE + "/otn/czxx/queryByTrainNo?train_no=%s&from_station_telecode=%s"
           "&to_station_telecode=%s&depart_date=%s" % (train_no, frm, to, date))
    rows = None
    try:
        j = http_json(url, ttl=TTL_SCHEDULE, label="时刻表 " + train_no)
        rows = (j.get("data") or {}).get("data") if isinstance(j, dict) else None
    except RuntimeError:
        rows = None
    if not rows:
        url2 = (BASE + "/otn/queryTrainInfo/query?leftTicketDTO.train_no=%s"
                "&leftTicketDTO.train_date=%s" % (train_no, date))
        j2 = http_json(url2, ttl=TTL_SCHEDULE, label="时刻表2 " + train_no)
        rows = (j2.get("data") or {}).get("data") if isinstance(j2, dict) else None
    if not rows:
        raise RuntimeError("时刻表查询失败: " + train_no)
    out = []
    for s in rows:
        out.append({"station": s.get("station_name"), "arrive": s.get("arrive_time") or s.get("arrival_time", "--"),
                    "depart": s.get("start_time", "--"), "stop": _int_or_0(s.get("stopover_time")),
                    "station_no": s.get("station_no")})
    return out

# ---- 票价 ----
def price(train_no, qfrom, qto, seat_types, date):
    """qfrom/qto 为 4 位站序(f[16]/f[17]), seat_types 为 f[35]"""
    url = (BASE + "/otn/leftTicket/queryTicketPrice?train_no=%s&from_station_no=%s"
           "&to_station_no=%s&seat_types=%s&train_date=%s"
           % (train_no, qfrom, qto, seat_types, date))
    j = http_json(url, ttl=TTL_PRICE, label="票价 " + train_no)
    return j.get("data") if isinstance(j, dict) else None

SEAT_LABEL = {"OT": "商务座", "TZ": "特等座", "ZY": "一等座", "ZE": "二等座",
              "SW": "商务座", "YZ": "硬座", "YB": "硬卧", "RW": "软卧",
              "SRRB": "动卧", "WZ": "无座", "GR": "高级软卧", "YYRW": "一等卧", "MIN": "最低"}
