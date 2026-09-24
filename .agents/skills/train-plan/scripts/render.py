# -*- coding: utf-8 -*-
"""
渲染交互式HTML报告: 内嵌SVG中国省市边界地图(离线零依赖) + 铁路票根风格可排序卡片。
单文件HTML, 浏览器直接打开, 无需任何服务与网络。
"""
import json, math, os
from html import escape
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
CHINA = os.path.join(HERE, "assets", "china_adm1.geojson")
if not os.path.exists(CHINA):
    CHINA = os.path.join(HERE, "assets", "china_full.json")
W, H = 980, 780
PAD = 16
LON0, LON1, LAT0, LAT1 = 73.0, 136.0, 17.5, 54.8
LEGC = ["#1d5fa8", "#1d6b45", "#b45309", "#7c3aed", "#c0392b", "#0e7490", "#be185d", "#4d7c0f"]
PROVINCE_NAMES = {
    "Hainan Province": "海南", "Taiwan Province": "台湾", "Guangxi Zhuang Autonomous Region": "广西",
    "Fujian Province": "福建", "Yunnan Province": "云南", "Guizhou Province": "贵州",
    "Jiangxi Province": "江西", "Hunan Province": "湖南", "Zhejiang Province": "浙江",
    "Shanghai Municipality": "上海", "Chongqing Municipality": "重庆", "Hubei Province": "湖北",
    "Sichuan Province": "四川", "Anhui Province": "安徽", "Jiangsu Province": "江苏",
    "Henan Province": "河南", "Tibet Autonomous Region": "西藏", "Shandong Province": "山东",
    "Qinghai Province": "青海", "Ningxia Ningxia Hui Autonomous Region": "宁夏",
    "Shaanxi Province": "陕西", "Tianjin Municipality": "天津", "Shanxi Province": "山西",
    "Beijing Municipality": "北京", "Gansu Province": "甘肃", "Hebei Province": "河北",
    "Liaoning Province": "辽宁", "Jilin Province": "吉林", "Xinjiang Uyghur Autonomous Region": "新疆",
    "Inner Mongolia Autonomous Region": "内蒙古", "Heilongjiang Province": "黑龙江",
    "Macau Special Administrative Region": "澳门", "Hong Kong Special Administrative Region": "香港",
    "Guangzhou Province": "广东",
}

def _merc(lon, lat):
    return math.radians(lon), math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

def build_projection():
    x0, y0 = _merc(LON0, LAT1)
    x1, y1 = _merc(LON1, LAT0)
    s = min((W - 2 * PAD) / (x1 - x0), (H - 2 * PAD) / (y0 - y1))
    ox = (W - (x1 - x0) * s) / 2
    oy = (H - (y0 - y1) * s) / 2
    def proj(lon, lat):
        x, y = _merc(lon, lat)
        return round((x - x0) * s + ox, 1), round((y0 - y) * s + oy, 1)
    return proj

def china_svg_parts():
    proj = build_projection()
    if not os.path.exists(CHINA):
        return [], []
    with open(CHINA, encoding="utf-8") as source:
        d = json.load(source)
    parts, labels = [], []
    for feat in d["features"]:
        name = (feat.get("properties") or {}).get("shapeName") or (feat.get("properties") or {}).get("name") or ""
        geom = feat.get("geometry") or {}
        polys = geom["coordinates"] if geom.get("type") == "MultiPolygon" else (
            [geom["coordinates"]] if geom.get("type") == "Polygon" else [])
        path, bx0, by0, bx1, by1 = [], 1e9, 1e9, -1e9, -1e9
        for poly in polys:
            for ring in poly:
                pts = []
                for lon, lat in ring:
                    if not (LON0 - 2 <= lon <= LON1 + 2 and LAT0 - 2 <= lat <= LAT1 + 2):
                        continue
                    px, py = proj(lon, lat)
                    pts.append("%g %g" % (px, py))
                    bx0 = min(bx0, px); by0 = min(by0, py); bx1 = max(bx1, px); by1 = max(by1, py)
                if len(pts) >= 3:
                    path.append("M" + "L".join(pts) + "Z")
        if path:
            parts.append(" ".join(path))
            if name and (bx1 - bx0) > 60 and (by1 - by0) > 42:
                short = PROVINCE_NAMES.get(name, name)
                labels.append((short, (bx0 + bx1) / 2, (by0 + by1) / 2))
    return parts, labels

TPL = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>归途 · __FROM__至__TO__</title>
<style>__STYLE__</style></head><body><section id="opening"><div><div class="eyebrow">长路有尽处 · 归灯未眠</div><h1>回<em>家</em></h1><p>把远方折成一张车票，沿着铁路线，回到一盏为你亮着的灯。</p><div class="origin">__FROM__ — __TO__</div><button id="enterReport">查看回家路线</button></div><div class="home-ticket" aria-label="渡船与归途车票视觉开场"><svg class="river-scene" viewBox="0 0 520 190" role="img" aria-label="暮色江面上，一叶小船驶向岸边灯火"><defs><linearGradient id="riverFade" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#f1cb8e" stop-opacity=".25"/><stop offset="1" stop-color="#f1cb8e" stop-opacity="0"/></linearGradient></defs><circle cx="390" cy="42" r="27" fill="#efc688" opacity=".8"/><path d="M0 111 Q88 81 163 108 T320 102 Q432 76 520 106 V190 H0Z" fill="#321f1d" opacity=".45"/><path d="M0 125 Q96 111 177 126 T340 121 T520 119 M0 143 Q97 128 186 144 T371 137 T520 141 M0 165 Q90 149 170 167 T363 155 T520 160" fill="none" stroke="#e5b778" stroke-opacity=".34" stroke-width="1.5"/><path d="M174 130 Q233 139 297 129 L281 145 Q235 154 194 143Z" fill="#deaa68"/><path d="M233 132V45 M235 50L290 123H235Z" fill="#f3d5a0" opacity=".9"/><path d="M231 61L193 124H231Z" fill="#d99865"/><path d="M213 151 Q253 160 292 151" fill="none" stroke="#f5d294" opacity=".7"/><path d="M370 103L392 77L414 103 M376 102V127H408V102" fill="none" stroke="#e9c58d" stroke-width="2"/><rect x="389" y="105" width="10" height="14" fill="#f2c16e"/></svg><div class="ticket-paper"><div class="ticket-head"><span class="ticket-brand">THE WAY HOME · 归途车票</span><span class="ticket-class">HOMEBOUND / 001</span></div><div class="ticket-route"><div class="ticket-city">__FROM__<small>DEPARTURE / 出发</small></div><div class="ticket-arrow">→</div><div class="ticket-city">__TO__<small>ARRIVAL / 到达</small></div></div><div class="ticket-meta"><div>日期<b>__DATE__</b></div><div>人数<b>__PEOPLE__ 人</b></div><div>状态<b>一路平安</b></div></div><div class="ticket-stamp">归心似箭</div><div class="ticket-watermark">回家</div></div><div class="ticket-stub"><svg class="boat-mark" viewBox="0 0 120 64" aria-label="旧船票意象"><path d="M12 43 Q59 51 106 43 L94 53 Q59 60 24 53 Z" fill="#b46b4e" opacity=".9"/><path d="M58 42V12 M59 13L89 39H59Z" fill="#d5aa6c" opacity=".86"/><path d="M58 17L36 38H58Z" fill="#f0d4a0" opacity=".72"/><path d="M8 56 Q42 48 76 57 T112 55" fill="none" stroke="#b78b60" stroke-width="1.5"/><circle cx="98" cy="12" r="5" fill="#d9a760" opacity=".55"/></svg><strong>HOME</strong>旧船票的远方<br/>换作火车票<br/>仍向灯火去</div></div></section><div id="reportShell" class="hidden-shell">
<header class="report-head">
  <h1><span style="font:11px Consolas,monospace;letter-spacing:.2em;color:#9bc0c9;display:block;margin-bottom:5px">THE WAY HOME / 行程方案</span>__FROM__ — __TO__</h1><button id="backIntro">返回开场</button>
  <div class="meta"><b>出发 __DATE__ __AFTER__ 后</b><b>到达不晚于 __BY__</b><b>__PEOPLE__ 人</b><b>目标 ≤ __BUDGET__ 元/人</b></div>
</header>
<div id="bar">
  <span style="color:var(--mut);font-size:12.5px">排序:</span>
  <button class="chip on" data-sort="price">价格</button>
  <button class="chip" data-sort="arr">到达早</button>
  <button class="chip" data-sort="dur">历时短</button>
  <button class="chip" data-sort="comfort">舒适度</button>
  <span style="width:12px"></span>
  <span style="color:var(--mut);font-size:12.5px">类型:</span>
  <button class="chip on" data-ft="全部">全部</button>
  <button class="chip" data-ft="直达">直达</button>
  <button class="chip" data-ft="中转">中转</button>
  <button class="chip" data-ft="买短乘长">买短乘长</button>
  <button class="chip" data-ft="买长乘短">买长乘短</button>
  <button class="chip" data-ft="买长又买短">买长又买短</button>

  <label style="font-size:12px;color:var(--mut)">换乘不超过 <select id="maxTransfers" aria-label="最多换乘次数"><option value="3" selected>3 次</option><option value="0">0 次</option><option value="1">1 次</option><option value="2">2 次</option></select></label>
  <span style="color:var(--mut);font-size:12px">共 <b id="cnt"></b> 个方案 · 生成于 __GEN__</span>
</div>
<div id="wrap"><div id="list"></div>
<div id="mapbox">
  <svg id="cmap" viewBox="0 0 __W__ __H__" preserveAspectRatio="xMidYMid meet">
    <g id="provs"></g>
    <g id="routes"></g>
    <g id="nodes"></g>
    <g id="plabels"></g>
  </svg>
  <div class="map-top"><span>所选行程 · 地理位置</span><span>北 ↑</span></div>
  <div id="maplegend"></div>
</div></div>
<div id="hint">说明：只有所有票段查得对应可购席别票价时才显示确定合计；缺价显示“待核价”，绝不按里程推测票价。带 * 的合计含补票参考价——按 12306 同车公布票价核出，补票段为无座，以列车长补票为准。“买短乘长”方案含车上补票区间；“买长乘短”提前下车差价不退。地图以站点间地理示意线展示，车次和耗时在分段详情中查看，点击左侧卡片切换。购票请前往 <b>12306 官方 App/网站</b>。</div>
<script>
const DATA = __DATA__;
const CN = {people: DATA.params.people};
const TYPE_COLOR = {"直达":"#1d6b45","中转":"#1d5fa8","买短乘长":"#b45309","买长乘短":"#6d28d9","买长又买短":"#a94332"};
const LEGC = ["#1d5fa8","#1d6b45","#b45309","#7c3aed","#c0392b","#0e7490","#be185d","#4d7c0f"];
let curSort="price", curFt="全部", sel=-1;
const byId = {}; DATA.plans.forEach((p,i)=>byId[i]=p);
function coord(st){ return DATA.coords[st]||null; }
function esc(value){ return String(value??"").replace(/[&<>"']/g,c=>c.charCodeAt(0)===34?"&quot;":({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;"}[c])); }
function stars(c){ const n=Math.round(c/2); return "★".repeat(n)+"☆".repeat(5-n); }
function durCN(m){ return Math.floor(m/60)+"小时"+String(m%60).padStart(2,"0")+"分"; }
function legDur(l){ const [h,m]=l.lishi.split(":"); return (+h)*60+(+m); }
function md(s){ return s? s.slice(5,10).replace("-","/") : ""; }
function addDays(s,n){ const p=s.split("-").map(Number); const d=new Date(p[0],p[1]-1,p[2]+n); return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0"); }
function legArrDate(l){ const t=l.dep.split(":").map(Number), s=l.lishi.split(":").map(Number); return addDays(l.date, Math.floor((t[0]*60+t[1]+s[0]*60+s[1])/1440)); }
function money(p){ return p==null?"—":((p.est?"≈¥":"¥")+p.v); }

function cardHTML(p,i){
  const depDate = p.dep_dt? md(String(p.dep_dt).slice(0,10)) : md(p.legs[0].date);
  const arrDate = p.arr_dt? md(String(p.arr_dt).slice(0,10)) : md(p.legs[p.legs.length-1].date);
  const last = p.legs[p.legs.length-1];
  const legs = p.legs.map((l,j)=>{
    const seats = Object.entries(l.seats).map(([k,v])=>`<span class="ok">${esc(k)} ${esc(v)}</span>`).join(" · ")||"—";
    const col = LEGC[j%LEGC.length];
    const pr = l.price==null? " · 待核价" : ` · <span class="pr">¥${l.price.v}</span>`;
    const crossDay = j>0 && l.date !== p.legs[j-1].date;
    const tr = j>0 && p.transfers[j-1] ? `<div class="tr"><b>${esc(p.transfers[j-1].station)}</b> 换乘${crossDay?' · <span style="color:var(--gold)">跨天</span>':''} · 等${p.transfers[j-1].buffer_min}分 · ${p.transfers[j-1].kind||(p.transfers[j-1].same_station?"同站":"需跨站")} · 本程历时 ${durCN(legDur(l))}</div>` : "";
    const aD = legArrDate(l);
    return (j? tr : "") + `<div class="leg"><span><span class="dotc" style="background:${col}"></span><span class="t">${esc(l.train)}</span></span>
      <span><b class="date">${md(l.date)}</b> ${esc(l.from_cn)} <b class="time">${l.dep}</b> → ${aD!==l.date? `<b class="date">${md(aD)}</b>`:""} <b class="time">${l.arr}</b> ${esc(l.alight_cn||l.to_cn)}</span>
      <span class="seat">${seats}${pr}</span></div>`;
  }).join("");
  const notes = (p.notes||[]).map(n=>`<div class="note">${esc(n)}</div>`).join("");
  const pp = p.price_pp==null? (p.price_ref!=null? `¥${p.price_ref.v}<span style="font-size:11px;vertical-align:top">*</span>` : "待核价") : "¥"+p.price_pp.v;
  const tot = p.price_pp!=null? "共 ¥"+(p.price_pp.v*CN.people).toFixed(1)
            : p.price_ref!=null? `含补票参考 ¥${p.supp_ref.v}/人 · 共 ¥${(p.price_ref.v*CN.people).toFixed(1)}`
            : (p.known_price==null?"各段未查价":"已核价 ¥"+p.known_price+"/人，非全程价");
  return `<div class="card ${p.over_budget?"over":""}" id="card${i}" style="--spine:${TYPE_COLOR[p.type]};animation-delay:${(i%12)*40}ms" onclick="pick(${i})">
    <div class="tk-head">
      <span class="badge b-${esc(p.type)}">${esc(p.type)}</span>
      ${p.legs.map(l=>`<span class="train">${esc(l.train)}</span>`).join('<span style="color:var(--mut)">→</span>')}
      <span class="dur">${esc(p.legs[0].from_cn)} <b class="date">${depDate}</b> ${p.legs[0].dep} → ${esc(last.alight_cn||last.to_cn)} ${arrDate!==depDate? `<b class="date">${arrDate}</b>`:""} <b class="time">${last.arr}</b> · ${durCN(p.duration_min)}</span>
      <div class="price"><div class="pp">${pp}</div><div class="tot">${p.price_pp?"/人 · ":""}${tot}</div></div>
    </div>
    <div class="tk-body">${legs}</div>
    ${notes}
    <div class="cfoot">
      <span>舒适度 <span class="stars">${stars(p.comfort)}</span> ${p.comfort}/10</span>
      <span>换乘 ${p.transfers.length} 次</span>
      <span>到达 ${esc(p.arr_dt)}</span>
      <button class="cp" onclick="copyPlan(event,${i})">复制购票信息</button>
    </div>
  </div>`;
}
function visible(){
  let arr = DATA.plans.map((p,i)=>[p,i]).filter(([p])=>(curFt==="全部"||p.type===curFt)&&p.transfers.length<=+document.getElementById("maxTransfers").value);
  const P = p => p.price_pp!=null? p.price_pp.v : (p.price_ref!=null? p.price_ref.v : 9e9);
  const key = {price:P, arr:p=>p.arr_dt, dur:p=>p.duration_min, comfort:p=>-p.comfort}[curSort];
  arr.sort((a,b)=>{ const x=key(a[0]),y=key(b[0]); return (typeof x==="string"?x.localeCompare(y):x-y)||a[1]-b[1]; });
  return arr;
}
function renderList(){
  const arr = visible();
  document.getElementById("list").innerHTML = arr.map(([p,i])=>cardHTML(p,i)).join("") || "<div style='padding:30px;color:var(--mut)'>当前筛选无方案</div>";
  document.getElementById("cnt").textContent = arr.length;
}
function drawRoutes(){
  const g = document.getElementById("routes"); g.innerHTML = "";
  const nodes = document.getElementById("nodes"); nodes.innerHTML = "";

  if(sel>=0){ const p=byId[sel]; p.legs.forEach((l,j)=>drawSeg({...l,to_cn:l.alight_cn||l.to_cn}, LEGC[j%LEGC.length], 4)); drawStops(p); legend(p); }
  else document.getElementById("maplegend").innerHTML = "点击左侧方案查看路线";
}
function drawSeg(l,color,w,label){
  const a = coord(l.from_cn), b = coord(l.to_cn);
  if(!a||!b) return;
  const g = document.getElementById("routes");
  const el = document.createElementNS("http://www.w3.org/2000/svg","path");
  const d = `M${a[0]} ${a[1]} Q${(a[0]+b[0])/2} ${(a[1]+b[1])/2 - 18} ${b[0]} ${b[1]}`;
  el.setAttribute("d", d);
  el.setAttribute("fill","none"); el.setAttribute("stroke",color); el.setAttribute("stroke-width",w);
  el.setAttribute("stroke-linecap","round"); el.setAttribute("class","route-main");
  const wake = document.createElementNS("http://www.w3.org/2000/svg","path");
  wake.setAttribute("d", d); wake.setAttribute("fill","none"); wake.setAttribute("stroke","#fffdf6"); wake.setAttribute("stroke-width",w+7); wake.setAttribute("stroke-linecap","round"); wake.setAttribute("class","route-wake");
  g.appendChild(wake);
  if(w<=2) el.setAttribute("opacity",".5");
  g.appendChild(el);
  if(label && Math.hypot(a[0]-b[0],a[1]-b[1])>115){
    const mx=(a[0]+b[0])/2, my=(a[1]+b[1])/2-16;
    const t = document.createElementNS("http://www.w3.org/2000/svg","text");
    t.setAttribute("x",mx); t.setAttribute("y",my); t.setAttribute("text-anchor","middle");
    t.setAttribute("font-size","12"); t.setAttribute("font-weight","700"); t.setAttribute("fill",color);
    t.setAttribute("stroke","#fffdf6"); t.setAttribute("stroke-width","4"); t.setAttribute("paint-order","stroke");
    t.textContent = `${label.train} · ${label.dur}`;
    g.appendChild(t);
  }
}
function drawStops(p){
  const nodes=document.getElementById("nodes"), seen=new Set();
  const stops=[p.legs[0].from_cn,...p.legs.map(l=>l.alight_cn||l.to_cn)];
  stops.forEach((st,index)=>{
    const c=coord(st); if(!c||seen.has(st))return; seen.add(st);
    const dot=document.createElementNS("http://www.w3.org/2000/svg","circle");
    for(const [k,v] of Object.entries({cx:c[0],cy:c[1],r:7,fill:index===0?"#175437":index===stops.length-1?"#c0392b":"#b45309",stroke:"white","stroke-width":2}))dot.setAttribute(k,v);
    nodes.appendChild(dot);
    const number=document.createElementNS("http://www.w3.org/2000/svg","text");
    number.setAttribute("x",c[0]);number.setAttribute("y",c[1]+3.2);
    number.setAttribute("text-anchor","middle");number.setAttribute("font-size","9");
    number.setAttribute("font-weight","700");number.setAttribute("fill","white");
    number.textContent=String(index+1);nodes.appendChild(number);
    const title=document.createElementNS("http://www.w3.org/2000/svg","title");title.textContent=`${index+1}. ${st}`;dot.appendChild(title);
  });
}
function legend(p){
  const lg=document.getElementById("maplegend");
  const stations=[p.legs[0].from_cn,...p.legs.map(l=>l.alight_cn||l.to_cn)];
  lg.innerHTML=`<div class="legend-head"><strong>沿途车次与换乘</strong><span>${p.transfers.length} 次换乘</span></div>`+
    p.legs.map((l,j)=>{
      const to=l.alight_cn||l.to_cn;
      const suffix=j<p.legs.length-1?`<small>在 ${esc(to)} 换乘 · ${p.transfers[j]?.buffer_min??"—"} 分钟</small>`:`<small>抵达 ${esc(to)}</small>`;
      return `<div class="route-index-row"><span class="route-index-num">${j+1}—${j+2}</span><span class="sw" style="background:${LEGC[j%LEGC.length]}"></span><div><b>${esc(l.train)}</b> <span class="date">${md(l.date)}</span> ${esc(l.from_cn)} → ${esc(to)}${suffix}</div></div>`;
    }).join("")+
    `<div class="route-index-actions"><button class="cp" onclick="zoomTo('route')">聚焦线路</button><button class="cp" onclick="zoomTo('full')">全国视野</button></div>`;
}
let zoomMode = "route";
function zoomTo(mode){
  zoomMode=mode; const svg=document.getElementById("cmap");
  if(mode==="full"||sel<0){svg.setAttribute("viewBox","0 0 980 780");return;}
  const pts=[]; byId[sel].legs.forEach(l=>{for(const st of [l.from_cn,l.alight_cn||l.to_cn]){const c=coord(st);if(c)pts.push(c)}});
  if(!pts.length)return;
  const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);
  const x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
  const box=document.getElementById("mapbox");
  const aspect=box.clientWidth/Math.max(1,box.clientHeight);
  let w=Math.max(210,x1-x0+180),h=Math.max(170,y1-y0+140);
  if(w/h<aspect)w=h*aspect;else h=w/aspect;
  svg.setAttribute("viewBox",`${(x0+x1-w)/2} ${(y0+y1-h)/2} ${w} ${h}`);
}
function pick(i){
  sel=i; drawRoutes(); zoomTo(zoomMode);

  document.querySelectorAll('#list .card').forEach(c=>c.classList.remove('sel'));
  const el=document.getElementById("card"+i); if(el){el.classList.add("sel");}
}
function copyPlan(e,i){
  e.stopPropagation();
  const p=byId[i];
  const lp = l => l.price==null? " 待核价" : ` ¥${l.price.v}`;
  const txt = p.legs.map((l,j)=>`【第${j+1}程】${l.date} ${l.train} ${l.from_cn}(${l.from})→${l.to_cn}(${l.to}) ${l.dep}-${l.arr} ${Object.entries(l.seats).map(([k,v])=>k+v).join("/")}${p.buy_short&&j===p.legs.length-1?"(后段车上补票)":""}${lp(l)}`).join("\\n")+`\\n合计约 ${p.price_pp==null? (p.price_ref!=null? "¥"+p.price_ref.v+"/人(含补票参考¥"+p.supp_ref.v+")" : "—") : (p.price_pp.est?"≈¥":"¥")+p.price_pp.v+"/人"} ×${CN.people}人`;
  navigator.clipboard.writeText(txt).then(()=>{e.target.textContent="已复制";setTimeout(()=>e.target.textContent="复制购票信息",1500);});
}
document.querySelectorAll("#bar .chip[data-sort]").forEach(b=>b.onclick=()=>{document.querySelectorAll("#bar .chip[data-sort]").forEach(x=>x.classList.remove("on"));b.classList.add("on");curSort=b.dataset.sort;renderList();drawRoutes();});
document.querySelectorAll("#bar .chip[data-ft]").forEach(b=>b.onclick=()=>{document.querySelectorAll("#bar .chip[data-ft]").forEach(x=>x.classList.remove("on"));b.classList.add("on");curFt=b.dataset.ft;renderList();drawRoutes();});

document.getElementById("maxTransfers").onchange=()=>{renderList();const first=visible()[0];if(first)pick(first[1]);else{sel=-1;drawRoutes();}};
renderList();
if(DATA.plans.length) pick(visible()[0][1]);
if(window.ResizeObserver) new ResizeObserver(()=>zoomTo(zoomMode)).observe(document.getElementById("mapbox"));
document.getElementById("enterReport").onclick=()=>{document.getElementById("opening").style.display="none";document.getElementById("reportShell").classList.remove("hidden-shell");window.scrollTo(0,0);zoomTo(zoomMode);document.getElementById("backIntro").focus()};document.getElementById("backIntro").onclick=()=>{document.getElementById("reportShell").classList.add("hidden-shell");document.getElementById("opening").style.display="grid";document.getElementById("enterReport").focus()};
</script></div></body></html>"""

def render(result, out_path):
    params = result["params"]
    import coords as C
    proj = build_projection()
    coords_ll, coords = {}, {}
    for p in result["plans"]:
        for leg in p["legs"]:
            for st in (leg["from_cn"], leg.get("alight_cn") or leg["to_cn"]):
                if st not in coords_ll:
                    ll = C.coord_of(st)
                    if ll:
                        coords_ll[st] = ll
                        coords[st] = proj(ll[0], ll[1])
    plans_view = json.loads(json.dumps(result["plans"], ensure_ascii=False))
    for p in plans_view:
        for leg in p["legs"]:
            v = leg.get("price")
            leg["price"] = {"v": v, "est": False} if isinstance(v, (int, float)) else None
        quoted = [leg["price"]["v"] for leg in p["legs"] if leg["price"] is not None]
        complete = len(quoted) == len(p["legs"]) and not p.get("buy_short")
        p["price_pp"] = {"v": round(sum(quoted), 1), "est": False} if complete else None
        p["known_price"] = round(sum(quoted), 1) if quoted else None
        p["price_ref"] = {"v": p["price_ref"], "est": False} if isinstance(p.get("price_ref"), (int, float)) else None
        p["supp_ref"] = {"v": p["supp_ref"]} if isinstance(p.get("supp_ref"), (int, float)) else None
        budget_price = p["price_pp"]["v"] if p["price_pp"] else (
            p["price_ref"]["v"] if p["price_ref"] else p["known_price"])
        p["over_budget"] = bool(params.get("budget") is not None and
                                budget_price is not None and
                                budget_price > params["budget"])

    provs, plabels = china_svg_parts()
    if not provs:
        result.setdefault("map_note", "未安装授权省界数据；当前仅显示站点地理位置")
    prov_html = "".join('<path class="prov" d="%s"></path>' % d for d in provs)
    label_html = "".join('<text class="plabel" x="%g" y="%g">%s</text>' % (x, y, escape(n)) for n, x, y in plabels)
    data = {
        "params": {"people": params.get("people", 1), "budget": params.get("budget"),
                   "date": params.get("date"), "after": params.get("after"),
                   "arrive_by": params.get("arrive_by")},
        "from_city": result["from_city"], "to_city": result["to_city"],
        "generated_at": result.get("generated_at", ""), "coords": coords, "plans": plans_view,
    }
    fields = {
        "__FROM__": result["from_city"], "__TO__": result["to_city"],
        "__DATE__": params.get("date", ""), "__AFTER__": params.get("after", ""),
        "__BY__": params.get("arrive_by", ""), "__PEOPLE__": params.get("people", 1),
        "__BUDGET__": params.get("budget") or "—", "__GEN__": result.get("generated_at", ""),
        "__W__": W, "__H__": H,
    }
    html = TPL
    for key, value in fields.items():
        html = html.replace(key, escape(str(value)))
    html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("<", "\\u003c"))
    html = html.replace("__STYLE__", (Path(HERE) / "base.css").read_text(encoding="utf-8") + (Path(HERE) / "design.css").read_text(encoding="utf-8"))
    if not provs:
        html = html.replace("所选行程 · 地理位置", "所选行程 · 站点示意（省界未安装）")
    html = html.replace('<g id="provs"></g>', '<g id="provs">' + prov_html + "</g>")
    html = html.replace('<g id="plabels"></g>', '<g id="plabels">' + label_html + "</g>")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    import sys
    render(json.load(open(sys.argv[1], encoding="utf-8")), sys.argv[2] if len(sys.argv) > 2 else "report.html")
    print("rendered")
