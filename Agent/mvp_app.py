#!/usr/bin/env python3
"""Local Product Knowledge MVP with deterministic analysis and a small web UI."""

import csv
import html
import json
import math
import re
import threading
import unicodedata
from collections import defaultdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import median
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "Dataset" / "DataProcessed" / "product_dataset_ready.csv"
MANIFEST_PATH = ROOT / "Dataset" / "ImageCache" / "manifest.csv"
IMAGE_DIR = ROOT / "Dataset" / "ImageCache" / "files"
HOST = "127.0.0.1"
PORT = 8765


def clean_text(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def number(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def integer(value):
    return int(number(value, 0))


def fmt_number(value):
    if value is None:
        return "N/A"
    value = float(value)
    if abs(value - round(value)) < 1e-9:
        return f"{int(value):,}"
    return f"{value:,.2f}"


def fmt_money(value, country):
    currency = "VND" if country == "vn" else "IDR" if country == "id" else "local"
    return f"{fmt_number(value)} {currency}"


def pct_change(old, new):
    if old in (None, 0):
        return None
    return (new - old) / old * 100


def latest_row(rows):
    return max(rows, key=lambda row: row.get("date", "")) if rows else None


def tokenize(value):
    return set(clean_text(value).split())


def safe_json(value):
    return json.dumps(value, ensure_ascii=False)


class KnowledgeBase:
    def __init__(self):
        self.rows = []
        self.by_item = defaultdict(list)
        self.latest = {}
        self.image_by_item = defaultdict(list)
        self._load_data()
        self._load_images()

    def _load_data(self):
        with DATA_PATH.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                row["_name"] = clean_text(row.get("product_name"))
                row["_price"] = number(row.get("price_num"))
                row["_sold"] = number(row.get("monthly_sold_value_num"))
                row["_rating"] = number(row.get("rating_num"))
                row["_discount"] = number(row.get("discount_percent_num"))
                row["_voucher"] = number(row.get("voucher_discount_num"))
                row["_revenue"] = row["_price"] * row["_sold"]
                row["_catid"] = str(row.get("catid") or "")
                row["_brand"] = clean_text(row.get("brand"))
                row["_tokens"] = tokenize(row.get("product_name"))
                self.rows.append(row)
                key = self.item_key(row)
                self.by_item[key].append(row)
        for key, rows in self.by_item.items():
            self.latest[key] = latest_row(rows)

    def _load_images(self):
        if not MANIFEST_PATH.exists():
            return
        with MANIFEST_PATH.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("status") != "downloaded":
                    continue
                local = Path(row.get("local_path") or "")
                filename = local.name
                if not filename or not (IMAGE_DIR / filename).exists():
                    continue
                for item_id in (row.get("item_ids") or "").split(";"):
                    if item_id:
                        self.image_by_item[item_id].append(filename)

    @staticmethod
    def item_key(row):
        return (row.get("country_code", ""), row.get("shop_id", ""), row.get("item_id", ""))

    def scope_rows(self, country=None, shop_id=None):
        return [
            row for row in self.rows
            if (not country or row.get("country_code") == country)
            and (not shop_id or row.get("shop_id") == str(shop_id))
        ]

    def resolve(self, query, country=None, shop_id=None):
        query = str(query or "").strip()
        scoped = self.scope_rows(country, shop_id)
        item_match = re.search(r"(?:item[_ ]?id|sku)\s*[:=#]?\s*(\d+)", query, re.I)
        if item_match:
            item_id = item_match.group(1)
            matches = [row for row in scoped if row.get("item_id") == item_id]
        else:
            raw_numbers = re.findall(r"\b\d{8,}\b", query)
            matches = [row for row in scoped if row.get("item_id") in raw_numbers]
            if not matches:
                q = clean_text(query)
                q_tokens = set(q.split())
                scored = []
                for row in scoped:
                    overlap = len(q_tokens & row["_tokens"])
                    if q and q in row["_name"]:
                        overlap += 5
                    if overlap:
                        scored.append((overlap, row))
                matches = [row for _, row in sorted(scored, key=lambda item: item[0], reverse=True)[:20]]
        grouped = defaultdict(list)
        for row in matches:
            grouped[self.item_key(row)].append(row)
        return [latest_row(rows) for rows in grouped.values()]

    def peer_rows(self, target, limit=None):
        rows = []
        for key, row in self.latest.items():
            if key == self.item_key(target):
                continue
            if row.get("country_code") != target.get("country_code"):
                continue
            same_category = target.get("_catid") and row.get("_catid") == target.get("_catid")
            same_brand = target.get("_brand") and row.get("_brand") == target.get("_brand")
            if same_category or same_brand:
                rows.append(row)
        return rows[:limit] if limit else rows

    def answer(self, question, country=None, shop_id=None):
        intent = classify_intent(question)
        if intent == "promotion_effectiveness":
            return self.promotion_answer(question, country, shop_id)
        target_candidates = self.resolve(question, country, shop_id)
        if intent == "similar_product":
            if len(target_candidates) != 1:
                return self.ambiguous(target_candidates, "Để tìm sản phẩm tương tự, hãy cung cấp item_id hoặc tên sản phẩm cụ thể.")
            return self.similar_answer(target_candidates[0])
        if intent == "sales_decline":
            if len(target_candidates) != 1:
                return self.ambiguous(target_candidates, "Để phân tích sales, hãy cung cấp item_id hoặc tên sản phẩm cụ thể.")
            return self.sales_answer(target_candidates[0])
        if intent == "category_relation":
            if len(target_candidates) != 1:
                return self.ambiguous(target_candidates, "Hãy cung cấp item_id hoặc tên sản phẩm để xem quan hệ category.")
            return self.category_answer(target_candidates[0])
        if len(target_candidates) == 1:
            return self.product_answer(target_candidates[0])
        return self.ambiguous(target_candidates, "Hãy cung cấp item_id, URL hoặc tên sản phẩm cụ thể.")

    def ambiguous(self, candidates, message):
        return {
            "status": "ambiguous_entity" if candidates else "insufficient_evidence",
            "intent": "entity_resolution",
            "answer": message,
            "evidence": [self.card(row) for row in candidates[:5]],
            "limitations": ["Tên gần giống chỉ tạo candidate list; MVP không tự chọn khi có nhiều kết quả."],
        }

    def card(self, row):
        return {
            "item_id": row.get("item_id"),
            "country_code": row.get("country_code"),
            "shop_id": row.get("shop_id"),
            "product_name": row.get("product_name"),
            "price": row["_price"],
            "monthly_sold": row["_sold"],
            "date": row.get("date"),
            "image": self.image_by_item.get(row.get("item_id"), [None])[0],
        }

    def product_answer(self, target):
        return {
            "status": "ok",
            "intent": "product_lookup",
            "answer": f"Đã tìm thấy sản phẩm {target.get('item_id')}: {target.get('product_name')}",
            "evidence": [
                {"label": "Product", "value": target.get("product_name"), "source": "product_dataset_ready.csv: product_name"},
                {"label": "Price", "value": fmt_money(target["_price"], target.get("country_code")), "source": "price_num"},
                {"label": "Recent sold proxy", "value": fmt_number(target["_sold"]), "source": "monthly_sold_value_num"},
                {"label": "Rating", "value": fmt_number(target["_rating"]), "source": "rating_num"},
            ],
            "cards": [self.card(target)],
            "limitations": ["monthly_sold_value là sales proxy, không phải doanh thu thật."],
        }

    def sales_answer(self, target):
        history = sorted(self.by_item[self.item_key(target)], key=lambda row: row.get("date", ""))
        if len(history) < 2:
            return {"status": "insufficient_evidence", "intent": "sales_decline", "answer": "Sản phẩm này chưa có đủ hai snapshot để kết luận tăng/giảm.", "evidence": [self.card(target)]}
        first, last = history[0], history[-1]
        sold_change = pct_change(first["_sold"], last["_sold"])
        price_change = pct_change(first["_price"], last["_price"])
        peer = self.peer_rows(last)
        peer_sold = median([row["_sold"] for row in peer]) if peer else None
        direction = "tăng" if sold_change is not None and sold_change > 0 else "giảm" if sold_change is not None and sold_change < 0 else "không đổi rõ"
        answer = f"Sales proxy của sản phẩm {last.get('item_id')} {direction} từ {fmt_number(first['_sold'])} xuống {fmt_number(last['_sold'])} giữa {first.get('date')} và {last.get('date')} ({fmt_number(sold_change)}%)."
        evidence = [
            {"label": "Sales change", "value": f"{fmt_number(first['_sold'])} -> {fmt_number(last['_sold'])} ({fmt_number(sold_change)}%)", "source": "monthly_sold_value_num theo date"},
            {"label": "Price change", "value": f"{fmt_money(first['_price'], first.get('country_code'))} -> {fmt_money(last['_price'], last.get('country_code'))} ({fmt_number(price_change)}%)", "source": "price_num theo date"},
            {"label": "Promotion latest", "value": f"discount={fmt_number(last['_discount'])}%, voucher={fmt_money(last['_voucher'], last.get('country_code'))}", "source": "discount_percent_num/voucher_discount_num"},
        ]
        if peer_sold is not None:
            evidence.append({"label": "Peer median sales", "value": fmt_number(peer_sold), "source": "same country + same category/brand latest rows"})
        return {"status": "ok", "intent": "sales_decline", "answer": answer, "evidence": evidence, "cards": [self.card(last)], "limitations": ["Đây là tương quan ngắn hạn trên 3 snapshot; không đủ chứng minh causal effect.", "monthly_sold_value không phải doanh thu thật."]}

    def similar_answer(self, target):
        candidates = self.peer_rows(target)
        scored = []
        for row in candidates:
            category = 1.0 if target.get("_catid") and target.get("_catid") == row.get("_catid") else 0.0
            brand = 1.0 if target.get("_brand") and target.get("_brand") == row.get("_brand") else 0.0
            union = target["_tokens"] | row["_tokens"]
            text_score = len(target["_tokens"] & row["_tokens"]) / len(union) if union else 0.0
            price_score = max(0.0, 1.0 - abs(target["_price"] - row["_price"]) / max(target["_price"], 1))
            score = category * 0.35 + brand * 0.2 + text_score * 0.25 + price_score * 0.2
            scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        top = [{**self.card(row), "score": round(score, 4)} for score, row in scored[:5]]
        if not top:
            return {"status": "insufficient_evidence", "intent": "similar_product", "answer": "Không tìm thấy candidate cùng country/category/brand.", "limitations": ["MVP chưa dùng image embedding."]}
        return {"status": "ok", "intent": "similar_product", "answer": f"Đã tìm thấy {len(top)} sản phẩm tương tự theo baseline category, brand, title và price.", "evidence": top, "cards": [self.card(target)] + [self.card(row) for _, row in scored[:5]], "limitations": ["Đây là similar-product baseline, chưa phải same-product verification.", "Image embedding chưa được dùng trong điểm hiện tại."]}

    def promotion_answer(self, question, country, shop_id):
        groups = defaultdict(list)
        for row in self.scope_rows(country, shop_id):
            has_promo = row["_discount"] > 0 or bool(row.get("promotion_id"))
            has_voucher = row["_voucher"] > 0 or bool(row.get("voucher_code"))
            group = "promo_and_voucher" if has_promo and has_voucher else "promo_only" if has_promo else "voucher_only" if has_voucher else "no_promo"
            groups[group].append(row)
        result = []
        for group, rows in sorted(groups.items()):
            result.append({"group": group, "product_count": len(rows), "median_sold": median([row["_sold"] for row in rows]) if rows else 0, "median_estimated_revenue": median([row["_revenue"] for row in rows]) if rows else 0})
        result.sort(key=lambda row: row["median_estimated_revenue"], reverse=True)
        scope = f"{country or 'all countries'}" + (f" / shop {shop_id}" if shop_id else "")
        return {"status": "ok", "intent": "promotion_effectiveness", "answer": f"So sánh mô tả các nhóm promotion trong phạm vi {scope}. Nhóm đứng đầu theo median estimated revenue proxy là {result[0]['group']} nếu có dữ liệu.", "evidence": result, "limitations": ["Đây là observational comparison, không chứng minh promotion gây ra uplift.", "estimated revenue = price * monthly_sold_value là proxy.", "Nhóm có ít sản phẩm cần được diễn giải thận trọng."]}

    def category_answer(self, target):
        return {"status": "ok", "intent": "category_relation", "answer": f"Sản phẩm {target.get('item_id')} thuộc platform category catid={target.get('catid')}; shop category được lưu trong các trường shop_category_ids/shop_category_names nếu có.", "evidence": [{"label": "Platform category", "value": target.get("catid") or "N/A", "source": "products.catid"}, {"label": "Shop categories", "value": target.get("shop_category_names") or "N/A", "source": "product_categories + category_list"}], "cards": [self.card(target)], "limitations": ["Không nối shop category với category_platform bằng cùng category_id."]}


def classify_intent(question):
    text = clean_text(question)
    if any(word in text for word in ("tuong tu", "similar", "same product", "doi thu")):
        return "similar_product"
    if any(word in text for word in ("khuyen mai", "voucher", "promotion", "promo")) and any(word in text for word in ("hieu qua", "tot nhat", "best", "so sanh")):
        return "promotion_effectiveness"
    if any(word in text for word in ("category", "danh muc", "thuoc danh muc")):
        return "category_relation"
    if any(word in text for word in ("giam", "doanh so", "sales", "ban chay", "tang")):
        return "sales_decline"
    return "product_lookup"


def infer_country(question):
    text = clean_text(question)
    if re.search(r"\bvn\b|viet nam|vietnam", text):
        return "vn"
    if re.search(r"\bid\b|indonesia", text):
        return "id"
    return None


KB = KnowledgeBase()


def image_response(filename):
    if not re.fullmatch(r"[a-f0-9]{64}\.[a-z0-9]+", filename):
        return None
    path = IMAGE_DIR / filename
    if not path.exists() or not path.is_file():
        return None
    return path


HTML = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Product Knowledge MVP</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#17202a;background:#f4f6f8}*{box-sizing:border-box}body{margin:0}main{max-width:1120px;margin:0 auto;padding:36px 20px 56px}.eyebrow{color:#26705b;font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.header{display:flex;justify-content:space-between;gap:24px;align-items:end;margin-bottom:28px}.header h1{font-size:34px;line-height:1.05;margin:8px 0}.header p{margin:0;color:#5b6570;max-width:650px}.status{border:1px solid #cfe5dc;background:#effaf5;color:#1d6a53;padding:10px 14px;border-radius:8px;font-size:13px;white-space:nowrap}.panel{background:#fff;border:1px solid #dfe5e9;border-radius:8px;box-shadow:0 8px 24px #2434470d}.ask{padding:18px}.ask-row{display:flex;gap:10px}.ask input{flex:1;border:1px solid #bac6cf;border-radius:6px;padding:13px 14px;font-size:15px;outline:none}.ask input:focus{border-color:#278064;box-shadow:0 0 0 3px #2780641f}.ask button{border:0;border-radius:6px;background:#1f6f59;color:white;font-weight:700;padding:0 20px;cursor:pointer}.ask button:disabled{opacity:.6}.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.chip{border:1px solid #d8e0e5;background:#f8fafb;border-radius:999px;padding:7px 10px;color:#44515d;cursor:pointer;font-size:12px}.layout{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:18px;margin-top:18px}.result{padding:22px;min-height:360px}.result h2{font-size:18px;margin:0 0 10px}.answer{font-size:17px;line-height:1.55;color:#26323b;margin:0 0 20px}.meta{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0 20px}.tag{background:#edf4f1;color:#23644f;border-radius:999px;padding:5px 9px;font-size:12px}.section-title{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#74808a;font-weight:800;margin:22px 0 9px}.evidence{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:9px}.evidence-item{border:1px solid #e3e8eb;border-radius:6px;padding:11px}.evidence-item strong{display:block;font-size:12px;color:#68737c;margin-bottom:5px}.evidence-item span{font-size:14px;line-height:1.35}.table-wrap{overflow:auto}.data-table{width:100%;border-collapse:collapse;font-size:13px}.data-table th,.data-table td{text-align:left;border-bottom:1px solid #e8ecef;padding:10px 8px;vertical-align:top}.data-table th{font-size:11px;color:#6b7680;text-transform:uppercase;letter-spacing:.04em}.side{padding:18px}.side h3{font-size:14px;margin:0 0 12px}.side p,.side li{font-size:13px;line-height:1.5;color:#5d6872}.side ul{padding-left:18px}.card-list{display:grid;gap:10px}.product-card{display:flex;gap:10px;border:1px solid #e3e8eb;border-radius:6px;padding:9px}.product-card img{width:54px;height:54px;object-fit:cover;border-radius:4px;background:#eef1f2}.product-card strong{font-size:12px;display:block;line-height:1.3}.product-card small{color:#68737c;display:block;margin-top:4px}.empty{color:#75818b;text-align:center;padding:70px 20px}.error{color:#9d302b;background:#fff1f0;border:1px solid #f2c4c0;border-radius:6px;padding:12px}.muted{color:#71808b;font-size:12px}@media(max-width:800px){main{padding:22px 13px 40px}.header{display:block}.status{display:inline-block;margin-top:12px}.layout{grid-template-columns:1fr}.ask-row{display:block}.ask button{width:100%;padding:12px;margin-top:8px}.header h1{font-size:29px}}
</style></head><body><main>
<div class="header"><div><div class="eyebrow">Local Product Knowledge MVP</div><h1>Hỏi dữ liệu sản phẩm</h1><p>Tra cứu sản phẩm, so sánh sales ngắn hạn, tìm sản phẩm tương tự và xem nhóm promotion bằng dữ liệu processed.</p></div><div class="status">● Local · deterministic</div></div>
<section class="panel ask"><div class="ask-row"><input id="question" placeholder="Ví dụ: Sản phẩm nào tương tự item_id 123...?" autocomplete="off"><button id="ask">Phân tích</button></div><div class="chips"><button class="chip">Sản phẩm nào tương tự item_id 42657274673?</button><button class="chip">Promotion nào hiệu quả nhất ở VN?</button><button class="chip">Xem sản phẩm item_id 42657274673</button></div></section>
<div class="layout"><section class="panel result" id="result"><div class="empty">Nhập một câu hỏi để bắt đầu.</div></section><aside class="panel side"><h3>MVP đang hỗ trợ</h3><ul><li>Product lookup theo item_id, URL hoặc tên.</li><li>Sales comparison trên các snapshot.</li><li>Similar-product baseline.</li><li>So sánh promo/voucher theo nhóm.</li><li>Evidence và limitation cho từng câu trả lời.</li></ul><h3>Phạm vi dữ liệu</h3><p>VN + ID · 3 snapshot · <code>product_dataset_ready.csv</code></p><p class="muted">MVP chưa dùng LLM. Các phép tính chạy cố định để dễ kiểm tra.</p></aside></div>
</main><script>
const input=document.querySelector('#question'),button=document.querySelector('#ask'),result=document.querySelector('#result');
document.querySelectorAll('.chip').forEach(x=>x.addEventListener('click',()=>{input.value=x.textContent; input.focus();}));
function esc(x){return String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function card(c){return `<div class="product-card">${c.image?`<img src="/image/${esc(c.image)}" alt="">`:''}<div><strong>${esc(c.product_name)}</strong><small>item_id ${esc(c.item_id)} · ${esc(c.country_code)} · sold ${esc(c.monthly_sold)}</small></div></div>`}
function render(data){let out=`<h2>${esc(data.intent||'Analysis')}</h2><p class="answer">${esc(data.answer||'')}</p><div class="meta"><span class="tag">status: ${esc(data.status)}</span>${data.confidence?`<span class="tag">confidence: ${esc(data.confidence)}</span>`:''}</div>`; if(data.evidence?.length){if(data.evidence[0].group){out+=`<div class="section-title">Comparison</div><div class="table-wrap"><table class="data-table"><thead><tr><th>Group</th><th>Products</th><th>Median sold</th><th>Median revenue proxy</th></tr></thead><tbody>${data.evidence.map(x=>`<tr><td>${esc(x.group)}</td><td>${esc(x.product_count)}</td><td>${esc(x.median_sold)}</td><td>${esc(x.median_estimated_revenue)}</td></tr>`).join('')}</tbody></table></div>`}else{out+=`<div class="section-title">Evidence</div><div class="evidence">${data.evidence.map(x=>`<div class="evidence-item"><strong>${esc(x.label||x.item_id||'Candidate')}</strong><span>${esc(x.value??(x.product_name||('score '+x.score)))}</span>${x.source?`<small class="muted">${esc(x.source)}</small>`:''}</div>`).join('')}</div>`;}}
if(data.cards?.length){out+=`<div class="section-title">Products</div><div class="card-list">${data.cards.map(card).join('')}</div>`}if(data.limitations?.length){out+=`<div class="section-title">Limitations</div><ul>${data.limitations.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`}result.innerHTML=out;}
async function ask(){const q=input.value.trim();if(!q)return;button.disabled=true;result.innerHTML='<div class="empty">Đang phân tích...</div>';try{const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});render(await r.json());}catch(e){result.innerHTML='<div class="error">Không gọi được local MVP.</div>'}finally{button.disabled=false;}}
button.addEventListener('click',ask);input.addEventListener('keydown',e=>{if(e.key==='Enter')ask()});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def send_bytes(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_bytes(200, "text/html; charset=utf-8", HTML.encode("utf-8"))
            return
        if parsed.path.startswith("/image/"):
            path = image_response(unquote(parsed.path.removeprefix("/image/")))
            if not path:
                self.send_error(404)
                return
            content_type = "image/jpeg" if path.suffix in (".jpg", ".jpeg") else "image/png" if path.suffix == ".png" else "image/webp"
            self.send_bytes(200, content_type, path.read_bytes())
            return
        self.send_error(404)

    def do_POST(self):
        if urlparse(self.path).path != "/api/ask":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length))
            question = str(payload.get("question") or "").strip()
            country = payload.get("country_code") or infer_country(question)
            result = KB.answer(question, country, payload.get("shop_id"))
            self.send_bytes(200, "application/json; charset=utf-8", safe_json(result).encode("utf-8"))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_bytes(400, "application/json; charset=utf-8", safe_json({"status": "error", "error": str(exc)}).encode("utf-8"))


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Product Knowledge MVP: http://{HOST}:{PORT}", flush=True)
    print(f"Loaded rows: {len(KB.rows)} | products: {len(KB.latest)} | cached images: {sum(len(x) for x in KB.image_by_item.values())}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
