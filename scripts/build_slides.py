"""Sinh bộ slide trình bày Gladiators từ `docs/design/ultimate solution.md`.

Mọi con số trong deck phải là số **đo được** — hoặc trích từ spec, hoặc từ
artifact eval/QA có đường dẫn. Không có con số nào được viết tay ở đây mà không
truy được về nguồn ghi trong `SOURCES`.

    .venv/Scripts/python.exe scripts/build_slides.py
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

OUT = Path("docs/presentation/Gladiators_Architecture.pptx")

# --- design tokens ----------------------------------------------------------
NAVY = RGBColor(0x0F, 0x2A, 0x43)
INK = RGBColor(0x14, 0x1B, 0x24)
BODY = RGBColor(0x33, 0x41, 0x4E)
MUTED = RGBColor(0x6B, 0x7A, 0x8A)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
PANEL = RGBColor(0xF2, 0xF5, 0xF8)
LINE = RGBColor(0xD8, 0xE0, 0xE8)

TEAL = RGBColor(0x0E, 0x7C, 0x86)
BLUE = RGBColor(0x1E, 0x4D, 0x8C)
AMBER = RGBColor(0xC9, 0x6F, 0x1E)
RED = RGBColor(0xA6, 0x33, 0x3F)
PURPLE = RGBColor(0x6B, 0x46, 0x8F)
GREEN = RGBColor(0x2F, 0x7A, 0x4F)
GREY = RGBColor(0x8A, 0x97, 0xA5)

SERIES = [BLUE, TEAL, AMBER, PURPLE, RED, GREY]

FONT = "Segoe UI"
W, H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.62)
CONTENT_TOP = Inches(1.62)


def _txt(frame, text, size, color, bold=False, italic=False, space_after=0,
         align=PP_ALIGN.LEFT, para=None, font=FONT):
    p = frame.paragraphs[0] if para is None else para
    p.alignment = align
    p.space_after = Pt(space_after)
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = color
    r.font.name = font
    return p


def box(slide, x, y, w, h, fill=None, line=None, line_w=1.0):
    from pptx.enum.shapes import MSO_SHAPE

    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    sh.shadow.inherit = False
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(line_w)
    return sh


def tb(slide, x, y, w, h):
    t = slide.shapes.add_textbox(x, y, w, h)
    tf = t.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return tf


class Deck:
    def __init__(self):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = W, H
        self.blank = self.prs.slide_layouts[6]
        self.n = 0

    def _bg(self, slide, color=WHITE):
        box(slide, 0, 0, W, H, fill=color)

    def _chrome(self, slide, kicker):
        """Footer: kicker trái, số slide phải."""
        self.n += 1
        y = H - Inches(0.46)
        box(slide, MARGIN, y - Inches(0.08), W - 2 * MARGIN, Emu(9525), fill=LINE)
        f = tb(slide, MARGIN, y, Inches(9), Inches(0.3))
        _txt(f, kicker, 9, MUTED)
        f2 = tb(slide, W - MARGIN - Inches(1.2), y, Inches(1.2), Inches(0.3))
        _txt(f2, f"{self.n:02d}", 9, MUTED, bold=True, align=PP_ALIGN.RIGHT)

    def slide(self, title, sub=None, kicker="Gladiators · Analytical QA System"):
        s = self.prs.slides.add_slide(self.blank)
        self._bg(s)
        box(s, MARGIN, Inches(0.58), Inches(0.055), Inches(0.42), fill=TEAL)
        f = tb(s, MARGIN + Inches(0.22), Inches(0.52), W - 2 * MARGIN - Inches(0.3), Inches(0.55))
        _txt(f, title, 25, INK, bold=True)
        if sub:
            f2 = tb(s, MARGIN + Inches(0.22), Inches(1.06), W - 2 * MARGIN - Inches(0.3), Inches(0.4))
            _txt(f2, sub, 12, MUTED)
        self._chrome(s, kicker)
        return s


# ---------------------------------------------------------------------------
# helpers cho các khối nội dung hay dùng
# ---------------------------------------------------------------------------

def bullets(slide, x, y, w, items, size=13, gap=9, bullet_color=TEAL):
    """items: list[str] hoặc list[tuple[str, str]] = (đầu đề đậm, phần còn lại)."""
    tf = tb(slide, x, y, w, Inches(4.6))
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        head, rest = (it, None) if isinstance(it, str) else it
        r = p.add_run()
        r.text = "▪  "
        r.font.size = Pt(size)
        r.font.color.rgb = bullet_color
        r.font.name = FONT
        r2 = p.add_run()
        r2.text = head
        r2.font.size = Pt(size)
        r2.font.bold = rest is not None
        r2.font.color.rgb = INK if rest is not None else BODY
        r2.font.name = FONT
        if rest:
            r3 = p.add_run()
            r3.text = " " + rest
            r3.font.size = Pt(size)
            r3.font.color.rgb = BODY
            r3.font.name = FONT
    return tf


def card(slide, x, y, w, h, title, lines, accent=TEAL, title_size=12, body_size=10.5):
    box(slide, x, y, w, h, fill=PANEL)
    box(slide, x, y, Inches(0.045), h, fill=accent)
    tf = tb(slide, x + Inches(0.22), y + Inches(0.16), w - Inches(0.4), h - Inches(0.3))
    _txt(tf, title, title_size, INK, bold=True, space_after=5)
    for ln in lines:
        p = tf.add_paragraph()
        _txt(tf, ln, body_size, BODY, space_after=3, para=p)
    return tf


def stat(slide, x, y, w, value, label, accent=TEAL, vsize=27):
    tf = tb(slide, x, y, w, Inches(1.0))
    _txt(tf, value, vsize, accent, bold=True, space_after=1)
    p = tf.add_paragraph()
    _txt(tf, label, 10, MUTED, space_after=0, para=p)


def table(slide, x, y, w, rows, col_w=None, head_fill=NAVY, size=10.5,
          row_h=Inches(0.32), head_size=10.5, aligns=None):
    nrow, ncol = len(rows), len(rows[0])
    shp = slide.shapes.add_table(nrow, ncol, x, y, w, row_h * nrow)
    t = shp.table
    t.first_row = True
    if col_w:
        total = sum(col_w)
        for i, cw in enumerate(col_w):
            t.columns[i].width = Emu(int(w * cw / total))
    for ri, row in enumerate(rows):
        t.rows[ri].height = row_h
        for ci, val in enumerate(row):
            c = t.cell(ri, ci)
            c.margin_left = c.margin_right = Inches(0.09)
            c.margin_top = c.margin_bottom = Inches(0.02)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            c.fill.solid()
            if ri == 0:
                c.fill.fore_color.rgb = head_fill
            else:
                c.fill.fore_color.rgb = WHITE if ri % 2 else PANEL
            tf = c.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = (aligns[ci] if aligns else PP_ALIGN.LEFT)
            r = p.add_run()
            r.text = str(val)
            r.font.size = Pt(head_size if ri == 0 else size)
            r.font.bold = ri == 0
            r.font.color.rgb = WHITE if ri == 0 else BODY
            r.font.name = FONT
    return t


def mono(slide, x, y, w, h, lines, fill=RGBColor(0x10, 0x1C, 0x28), fg=RGBColor(0xC8, 0xD6, 0xE2),
         size=10, highlight=None):
    """Khối code/trace. highlight: dict[int index dòng] -> RGBColor."""
    box(slide, x, y, w, h, fill=fill)
    tf = tb(slide, x + Inches(0.2), y + Inches(0.14), w - Inches(0.35), h - Inches(0.26))
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(2)
        r = p.add_run()
        r.text = ln
        r.font.size = Pt(size)
        r.font.name = "Consolas"
        r.font.color.rgb = (highlight or {}).get(i, fg)
        r.font.bold = i in (highlight or {})
    return tf


def style_chart(chart, size=10, legend=True, legend_pos=XL_LEGEND_POSITION.BOTTOM):
    chart.font.size = Pt(size)
    chart.font.name = FONT
    chart.font.color.rgb = BODY
    chart.has_legend = legend
    if legend:
        chart.legend.position = legend_pos
        chart.legend.include_in_layout = False


def color_points(plot, colors):
    for i, pt in enumerate(plot.series[0].points):
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = colors[i % len(colors)]


# ===========================================================================
#  BUILD
# ===========================================================================

d = Deck()

# --- 01 TITLE --------------------------------------------------------------
s = d.prs.slides.add_slide(d.blank)
box(s, 0, 0, W, H, fill=NAVY)
box(s, 0, 0, Inches(0.09), H, fill=TEAL)
box(s, Inches(7.9), 0, Inches(5.44), H, fill=RGBColor(0x13, 0x33, 0x50))

f = tb(s, Inches(1.0), Inches(1.55), Inches(6.6), Inches(0.4))
_txt(f, "HỆ THỐNG HỎI ĐÁP PHÂN TÍCH THƯƠNG MẠI ĐIỆN TỬ", 11.5,
     RGBColor(0x6F, 0xC7, 0xD1), bold=True)

f = tb(s, Inches(1.0), Inches(2.05), Inches(6.6), Inches(2.0))
_txt(f, "GLADIATORS", 52, WHITE, bold=True, space_after=4)
p = f.add_paragraph()
_txt(f, "Kiến trúc trả lời không-được-đoán", 25, RGBColor(0xA9, 0xC4, 0xD8), para=p)

box(s, Inches(1.0), Inches(4.05), Inches(1.5), Inches(0.03), fill=TEAL)

f = tb(s, Inches(1.0), Inches(4.35), Inches(6.3), Inches(1.4))
_txt(f, "Mọi con số hiển thị phải truy vết được về evidence.", 14,
     RGBColor(0xD3, 0xE1, 0xEC), space_after=5)
p = f.add_paragraph()
_txt(f, "Không chắc thì từ chối — im lặng trả lời sai là chế độ hỏng tệ nhất.",
     14, RGBColor(0xD3, 0xE1, 0xEC), para=p)

f = tb(s, Inches(1.0), Inches(6.25), Inches(6.6), Inches(0.6))
_txt(f, "Source of truth: docs/design/ultimate solution.md  ·  Baseline ef3a380  ·  09/08/2026",
     10, RGBColor(0x7F, 0x9A, 0xB0))

# panel phải: 4 số lõi
for i, (v, l) in enumerate([
    ("86", "semantic object trong catalog"),
    ("S1→S9", "chín chặng, ba lớp kiểm độc lập"),
    ("0", "SQL do LLM sinh"),
    ("1.0", "verifier mutation detection"),
]):
    y = Inches(1.75) + i * Inches(1.15)
    box(s, Inches(8.55), y, Inches(0.035), Inches(0.78), fill=TEAL)
    tf = tb(s, Inches(8.82), y - Inches(0.04), Inches(4.1), Inches(0.9))
    _txt(tf, v, 27, WHITE, bold=True, space_after=2)
    p = tf.add_paragraph()
    _txt(tf, l, 10.5, RGBColor(0x9F, 0xBA, 0xCF), para=p)
d.n += 1

# --- 02 BÀI TOÁN -----------------------------------------------------------
s = d.slide("Bài toán và ranh giới",
            "Vì sao một hệ hỏi-đáp analytics lại phải được thiết kế quanh việc TỪ CHỐI")

bullets(s, MARGIN, CONTENT_TOP, Inches(6.5), [
    ("Đầu vào:", "câu hỏi tiếng Việt / Anh / Bahasa về dữ liệu sàn TMĐT hai thị trường VN + ID."),
    ("Dataset đóng băng:", "không cập nhật, không suy diễn ngoài phạm vi quan sát được."),
    ("Ràng buộc lõi:", "mọi con số hiển thị phải truy được về evidence — artifact, row key, "
     "công thức, unit, dataset version, caveat."),
    ("Chế độ hỏng cần chống:", "không phải crash. Crash thì ồn ào. Nguy hiểm là câu trả lời "
     "trôi chảy, có evidence, có mục “Độ tin cậy: High” — nhưng trả lời một câu hỏi khác."),
], size=13.5, gap=13)

box(s, MARGIN, Inches(4.75), Inches(6.5), Inches(1.85), fill=RGBColor(0xFD, 0xF4, 0xF5))
box(s, MARGIN, Inches(4.75), Inches(0.05), Inches(1.85), fill=RED)
tf = tb(s, MARGIN + Inches(0.25), Inches(4.94), Inches(6.0), Inches(1.5))
_txt(tf, "Ca kinh điển — bgk13, đo 09/08", 12, RED, bold=True, space_after=6)
for ln in [
    "Hỏi:  “Vì sao số listing tại VN giảm mạnh từ 01/07 đến 03/07?”",
    "Thật: 581 → 668. Listing TĂNG 87. Tiền đề “giảm mạnh” là sai.",
    "Hệ (trước sửa): “Có 668 listing.”  gate=allow · verified=True · High",
]:
    p = tf.add_paragraph()
    _txt(tf, ln, 10.5, BODY, space_after=3, para=p)

card(s, Inches(7.5), CONTENT_TOP, Inches(5.2), Inches(2.35),
     "Năm yêu cầu đồng thời (§1.1)", [
         "1  Không trả lời bằng capability gần đúng",
         "2  Analytical ngoài macro vẫn chạy được offline",
         "3  Context chọn theo chủ đề, có budget đo được",
         "4  Câu phức hợp tách được, ghép deterministic",
         "5  Mọi số truy ngược tới artifact + row key",
     ], accent=BLUE)

card(s, Inches(7.5), Inches(4.15), Inches(5.2), Inches(2.45),
     "Ba lớp kiểm hỏi ba câu khác nhau", [
         "Gate        →  Được phép trả lời không?",
         "Alignment   →  Có đang trả lời ĐÚNG câu hỏi?",
         "Verifier    →  Số hiển thị có evidence không?",
         "",
         "bgk13 lọt vì Gate ✓ và Verifier ✓. Lớp Alignment (A22)",
         "sinh ra để lấp đúng khe hở đó.",
     ], accent=AMBER)

# --- 03 DỮ LIỆU ------------------------------------------------------------
s = d.slide("Mô hình dữ liệu và vì sao bài toán hữu hạn hoá được",
            "Không gian câu trả lời bị đóng lại một cách có chủ đích")

for i, (v, l, c) in enumerate([
    ("3", "snapshot: 01–03/07/2026", BLUE),
    ("3.341", "dòng dữ liệu", TEAL),
    ("1.157", "product listing", AMBER),
    ("20", "shop", PURPLE),
    ("2", "thị trường (vn · id)", GREEN),
]):
    stat(s, MARGIN + i * Inches(2.48), CONTENT_TOP, Inches(2.3), v, l, accent=c, vsize=30)

box(s, MARGIN, Inches(2.72), W - 2 * MARGIN, Emu(9525), fill=LINE)

bullets(s, MARGIN, Inches(3.0), Inches(6.4), [
    ("Grain nhỏ nhất là product listing", "= {country}:{shop_id}:{item_id}. Không có SKU, "
     "không có customer, không có order-level."),
    ("86 semantic object", "trong catalog. Câu hỏi không rơi vào tập này thì bị từ chối — "
     "đây chính là thứ làm không gian trả lời trở nên hữu hạn và kiểm được."),
    ("monthly_sold là proxy hiển thị", "của một cửa sổ chưa xác nhận → cấm cộng qua các "
     "snapshot vì sẽ tính trùng."),
], size=12.5, gap=11)

card(s, Inches(7.3), Inches(3.0), Inches(5.4), Inches(3.4),
     "Zero-variance đã biết — không phân tích được, và hệ phải nói thế", [
         "is_ad_bool          → False trên toàn bộ dữ liệu",
         "is_sold_out_bool    → False trên toàn bộ dữ liệu",
         "",
         "Hệ không được trả lời “0% listing chạy quảng cáo”.",
         "Câu đúng là “dataset không quan sát được thuộc tính này”.",
         "",
         "Cùng nguyên tắc: thiếu dữ liệu thì GẮN CỜ, không điền 0.",
         "Điền 0 làm “không đo được” trông giống hệt “đo được và",
         "bằng phẳng” — hai kết luận trái ngược, một hiển thị.",
     ], accent=RED, body_size=10.5)

# --- 04 KIẾN TRÚC S1→S9 ----------------------------------------------------
s = d.slide("Kiến trúc đích — chín chặng, mỗi chặng một hợp đồng kiểu",
            "Không chặng nào được phép tin chặng trước mà không kiểm lại")

stages = [
    ("S1", "PARSE", "parser.py", "StructuredRequest", BLUE),
    ("S2", "ROUTE", "external/router.py", "internal · hybrid · abstain", BLUE),
    ("S3", "ENTITY", "entity_resolution.py", "ID → tên → fuzzy → BGE", BLUE),
    ("S4", "GATE-PRE", "gate.py", "allow · clarify · abstain", AMBER),
    ("S5", "PLAN", "synthesizer / decomposer", "LogicalQueryPlan (IR v1.0)", TEAL),
    ("S6", "EXECUTE", "compiler + executor", "SQLGlot · DuckDB read-only", TEAL),
    ("S7", "EVIDENCE", "contracts.Evidence", "bản ghi bất biến", PURPLE),
    ("S8", "VERIFY", "verifier.py", "mọi số phải khớp evidence", RED),
    ("S9", "GATE-OUT", "alignment + verify", "fail ⇒ A-VERIFICATION-FINAL", RED),
]
x0, w_, gap = MARGIN, Inches(1.32), Inches(0.09)
for i, (sid, name, mod, out, c) in enumerate(stages):
    x = x0 + i * (w_ + gap)
    box(s, x, CONTENT_TOP, w_, Inches(2.42), fill=PANEL)
    box(s, x, CONTENT_TOP, w_, Inches(0.052), fill=c)
    tf = tb(s, x + Inches(0.12), CONTENT_TOP + Inches(0.16), w_ - Inches(0.22), Inches(2.1))
    _txt(tf, sid, 10.5, c, bold=True, space_after=3)
    p = tf.add_paragraph(); _txt(tf, name, 11, INK, bold=True, space_after=6, para=p)
    p = tf.add_paragraph(); _txt(tf, mod, 8.5, MUTED, italic=True, space_after=5, para=p)
    p = tf.add_paragraph(); _txt(tf, out, 9, BODY, space_after=0, para=p)
    if i < len(stages) - 1:
        a = tb(s, x + w_ - Inches(0.02), CONTENT_TOP + Inches(1.05), Inches(0.14), Inches(0.3))
        _txt(a, "›", 13, GREY, bold=True, align=PP_ALIGN.CENTER)

box(s, MARGIN, Inches(4.35), W - 2 * MARGIN, Inches(0.86), fill=RGBColor(0xEF, 0xF6, 0xF7))
box(s, MARGIN, Inches(4.35), Inches(0.05), Inches(0.86), fill=TEAL)
tf = tb(s, MARGIN + Inches(0.25), Inches(4.5), W - 2 * MARGIN - Inches(0.5), Inches(0.6))
_txt(tf, "Điểm mạnh cấu trúc: mỗi mũi tên là một hợp đồng Pydantic có schema_version, "
         "không phải một lời gọi hàm.", 12, INK, bold=True, space_after=3)
p = tf.add_paragraph()
_txt(tf, "Một chặng hỏng thì hỏng ồn ào tại biên của nó, không lan thành câu trả lời sai ở cuối.",
     11, BODY, para=p)

cols = [
    ("Fail-closed là mặc định", "Không chắc ⇒ clarify hoặc abstain. Với câu mơ hồ hoặc thứ "
     "dataset không có, từ chối là HÀNH VI ĐÚNG, không phải lỗi.", GREEN),
    ("Không có raw-SQL path", "Không mở ở runtime dưới bất kỳ hình thức nào. SQL chỉ do "
     "compiler deterministic sinh, chỉ chạy qua executor read-only.", BLUE),
    ("Evidence bất biến", "ContextBundle chỉ chứa bản copy đã guard. Sửa Evidence gốc ⇒ "
     "verifier lệch ⇒ mọi câu chuyển A-VERIFICATION-FINAL.", PURPLE),
]
for i, (t, b, c) in enumerate(cols):
    card(s, MARGIN + i * Inches(4.12), Inches(5.42), Inches(3.9), Inches(1.16), t, [b], accent=c,
         title_size=11, body_size=10)

# --- 05 BA LỚP KIỂM --------------------------------------------------------
s = d.slide("Ba lớp kiểm độc lập — và khe hở giữa chúng",
            "Đây là luận điểm kiến trúc trung tâm của hệ thống")

layers = [
    ("GATE", "gate.py", "Được phép trả lời không?",
     ["Sáu phase: capability → intent/entity →", "forbidden op/grain/fanout → currency →",
      "alignment → missing slot", "", "Thu hết issue trong phase rồi mới chọn",
      "theo priority registry."], AMBER),
    ("ALIGNMENT · A22", "alignment.py", "Có đang trả lời ĐÚNG câu hỏi?",
     ["Chạy ba lần trên cùng digest:", "  pre-execution   digest ↔ plan",
      "  post-execution  plan ↔ evidence", "  pre-answer      evidence ↔ claims", "",
      "Bắt: country_dropped, date_range_narrowed,", "grouping_dropped, premise_contradicted…"], TEAL),
    ("VERIFIER", "verifier.py", "Số hiển thị có evidence không?",
     ["scan_numbers quét MỌI chữ số trong answer", "và đòi evidence hậu thuẫn.", "",
      "Citation phải trỏ evidence có thật.", "", "mutation detection giữ 1.0 — tụt là dấu hiệu",
      "bản vá đã TẮT một phép kiểm."], RED),
]
for i, (name, mod, q, lines, c) in enumerate(layers):
    x = MARGIN + i * Inches(4.12)
    box(s, x, CONTENT_TOP, Inches(3.9), Inches(3.15), fill=PANEL)
    box(s, x, CONTENT_TOP, Inches(3.9), Inches(0.055), fill=c)
    tf = tb(s, x + Inches(0.24), CONTENT_TOP + Inches(0.2), Inches(3.45), Inches(2.8))
    _txt(tf, name, 14, INK, bold=True, space_after=2)
    p = tf.add_paragraph(); _txt(tf, mod, 9, MUTED, italic=True, space_after=7, para=p)
    p = tf.add_paragraph(); _txt(tf, q, 11, c, bold=True, space_after=8, para=p)
    for ln in lines:
        p = tf.add_paragraph(); _txt(tf, ln, 9.5, BODY, space_after=2, para=p)

box(s, MARGIN, Inches(5.0), W - 2 * MARGIN, Inches(1.6), fill=RGBColor(0x10, 0x1C, 0x28))
tf = tb(s, MARGIN + Inches(0.3), Inches(5.16), Inches(6.0), Inches(1.3))
_txt(tf, "Khe hở mà A22 sinh ra để lấp", 12, RGBColor(0x6F, 0xC7, 0xD1), bold=True, space_after=6)
for ln in ["TC29 / TC39: gate cho phép ✓ · verifier pass ✓",
           "→ nhưng hệ trả “474 listing” cho một câu hỏi về MỨC GIẢM GIÁ.",
           "Con số có evidence thật. Nó chỉ là đáp án của một câu hỏi khác."]:
    p = tf.add_paragraph()
    _txt(tf, ln, 10.5, RGBColor(0xC8, 0xD6, 0xE2), space_after=3, para=p)

tf = tb(s, Inches(7.3), Inches(5.16), Inches(5.4), Inches(1.3))
_txt(tf, "Vì sao ba lớp phải ĐỘC LẬP", 12, RGBColor(0x6F, 0xC7, 0xD1), bold=True, space_after=6)
for ln in ["Ba lớp dùng chung một phép kiểm thì chỉ là một lớp mặc ba áo.",
           "Gate đọc request. A22 đối chiếu request ↔ plan ↔ evidence ↔ answer.",
           "Verifier chỉ nhìn chữ số trên màn hình. Không lớp nào tin lớp kia."]:
    p = tf.add_paragraph()
    _txt(tf, ln, 10.5, RGBColor(0xC8, 0xD6, 0xE2), space_after=3, para=p)

# --- 06 BẤT BIẾN -----------------------------------------------------------
s = d.slide("Bảy bất biến — vi phạm là hỏng hệ thống, không phải hỏng một câu",
            "§1.2 và §3 của spec. Đây là thứ được bảo vệ bằng CI, không bằng quy ước")

inv = [
    ("01", "LLM không bao giờ tính số, không bao giờ quyết định gate",
     "LLM chỉ: đoán intent, sinh plan IR, sinh search query, trích span, diễn giải câu chữ. "
     "Mọi output phải qua validator deterministic trước khi ảnh hưởng bất cứ gì.", BLUE),
    ("02", "source_tier khoá btc_dataset",
     "External data không bao giờ đi qua analytical compiler hoặc DuckDB.", BLUE),
    ("03", "External evidence luôn context_only",
     "source_tier=external, mapping_status=needs_review. Cấm tính toán hoặc suy nhân quả "
     "xuyên tier (A20-TIER).", TEAL),
    ("04", "Evidence object bất biến",
     "ContextBundle chỉ chứa bản copy đã guard.", TEAL),
    ("05", "Không mở raw-SQL path ở runtime",
     "Dưới bất kỳ hình thức nào.", AMBER),
    ("06", "Fail-closed",
     "Không chắc thì clarify hoặc abstain. clarify KHÔNG phải lỗi.", AMBER),
    ("07", "Schema đổi phải additive / backward-compatible",
     "Fixture cũ không được hỏng âm thầm.", PURPLE),
]
for i, (num, title, desc, c) in enumerate(inv):
    col, row = i % 2, i // 2
    x = MARGIN + col * Inches(6.16)
    y = CONTENT_TOP + row * Inches(0.98)
    w_ = Inches(11.9) if i == 6 else Inches(5.9)
    box(s, x, y, w_, Inches(0.85), fill=PANEL)
    box(s, x, y, Inches(0.045), Inches(0.85), fill=c)
    tf = tb(s, x + Inches(0.2), y + Inches(0.1), Inches(0.5), Inches(0.6))
    _txt(tf, num, 15, c, bold=True)
    tf = tb(s, x + Inches(0.72), y + Inches(0.1), w_ - Inches(0.95), Inches(0.7))
    _txt(tf, title, 11, INK, bold=True, space_after=3)
    p = tf.add_paragraph()
    _txt(tf, desc, 9.5, BODY, space_after=0, para=p)

box(s, MARGIN, Inches(6.05), W - 2 * MARGIN, Inches(0.6), fill=RGBColor(0xFD, 0xF4, 0xF5))
tf = tb(s, MARGIN + Inches(0.25), Inches(6.17), W - 2 * MARGIN - Inches(0.5), Inches(0.4))
_txt(tf, "Cạm bẫy đã cắn người thật:  “nan is None” trả về False — 63 listing bị void điểm "
         "được gán nhãn “Steady”, tức “không chấm được” hiện ra thành “bình thường”.",
     10.5, RED, bold=True)

# --- 07 CATALOG + CHART 1 --------------------------------------------------
s = d.slide("Semantic catalog — tầng khoá LLM ra khỏi mọi quyết định vật lý",
            "CHART 1/4 · 86 semantic object, đo tại HEAD bằng gladiators.domain.catalog")

cd = CategoryChartData()
cd.categories = ["derived_metric", "measure", "dimension", "entity", "context"]
cd.add_series("Số object", (33, 25, 14, 11, 3))
gf = s.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, MARGIN, Inches(1.75),
                        Inches(5.0), Inches(4.35), cd)
ch = gf.chart
style_chart(ch, size=11, legend_pos=XL_LEGEND_POSITION.BOTTOM)
color_points(ch.plots[0], [BLUE, TEAL, AMBER, PURPLE, GREY])
ch.plots[0].has_data_labels = True
dl = ch.plots[0].data_labels
dl.number_format = '0'
dl.number_format_is_linked = False
dl.font.size = Pt(11)
dl.font.bold = True
dl.font.color.rgb = WHITE
dl.font.name = FONT

tf = tb(s, Inches(2.42), Inches(3.28), Inches(1.2), Inches(0.7))
_txt(tf, "86", 26, INK, bold=True, align=PP_ALIGN.CENTER, space_after=0)
p = tf.add_paragraph()
_txt(tf, "object", 9.5, MUTED, align=PP_ALIGN.CENTER, para=p)

bullets(s, Inches(5.95), Inches(1.85), Inches(6.8), [
    ("BindingKind trả lời “giá trị lấy từ đâu”:", "column · expression · aggregate · "
     "tool_computed · context_only · unavailable."),
    ("CI fail khi khai sai:", "binding=column mà cột không tồn tại, expression thiếu handler, "
     "tool_computed trỏ handler không có thật, hoặc context_only lọt vào SQL plan."),
    ("Mỗi object exposed bắt buộc có alias tiếng Việt", "và ít nhất một alias Anh hoặc Bahasa. "
     "AliasIndex là nguồn NL binding duy nhất, có index_hash đi vào cache version."),
    ("Cùng surface trỏ nhiều ref ⇒ trả ambiguity.", "Tuyệt đối không dùng thứ tự tên ref để "
     "phá hoà — một grain bị chọn ngầm là một câu hỏi khác bị trả lời ngầm."),
], size=12, gap=12)

box(s, Inches(5.95), Inches(5.35), Inches(6.78), Inches(1.02), fill=RGBColor(0xEF, 0xF6, 0xF7))
box(s, Inches(5.95), Inches(5.35), Inches(0.05), Inches(1.02), fill=TEAL)
tf = tb(s, Inches(6.2), Inches(5.5), Inches(6.3), Inches(0.8))
_txt(tf, "Vì sao tầng này là điểm mạnh, không phải thủ tục thừa", 11, INK, bold=True, space_after=4)
p = tf.add_paragraph()
_txt(tf, "Catalog biến một bài toán mở (“trả lời mọi câu hỏi về dữ liệu”) thành bài toán đóng "
         "(“trả lời trong 86 object đã chứng nhận”). Đóng thì kiểm được, đo được, và từ chối được "
         "một cách có lý do tra cứu được.", 10.5, BODY, para=p)

# --- 08 HAI TRỤC TRỰC GIAO -------------------------------------------------
s = d.slide("Hai trục trực giao — bài học đắt nhất của vòng 09/08",
            "§3.1.1 · Dùng một trục cho hai vai là nguyên nhân gốc của CompilationError")

mono(s, MARGIN, CONTENT_TOP, Inches(6.2), Inches(2.15), [
    "parser      → grouping = ('dim.date', 'entity.product_listing')",
    "catalog     → answerability = \"exposed_as_dimension\"",
    "              physical      = ()            ← RỖNG",
    "synthesizer → sinh plan GROUP BY trên ref đó",
    "validator   → valid = True, 0 issue         ← CHO QUA",
    "compiler    → CompilationError              ← CRASH",
], highlight={2: RGBColor(0xFF, 0xB4, 0xA2), 5: RGBColor(0xFF, 0x8A, 0x7A)}, size=10.5)

tf = tb(s, MARGIN, Inches(3.98), Inches(6.2), Inches(1.2))
_txt(tf, "Mâu thuẫn nằm BÊN TRONG một object catalog: nó tự khai “exposed as dimension” "
         "trong khi không có cột vật lý nào.", 11.5, INK, bold=True, space_after=6)
p = tf.add_paragraph()
_txt(tf, "Validator tin lời khai. Compiler thi hành thực tế. Không tầng nào đối chiếu hai điều "
         "đó với nhau — và 28/83 ref mang cùng mâu thuẫn.", 11, BODY, para=p)

card(s, MARGIN, Inches(5.35), Inches(6.2), Inches(1.25),
     "Ba tầng giờ hỏi CÙNG một câu hỏi", [
         "catalog     → CatalogError, eager tại import",
         "validate_plan → issue non_physical_grouping (A19-PLAN-GROUPING)",
         "compiler    → tra counting_key, không so tên ref",
     ], accent=GREEN, body_size=10)

table(s, Inches(6.95), CONTENT_TOP, Inches(5.78), [
    ["AnalysisRole", "Nghĩa", "Gom nhóm", "Đếm"],
    ["physical_dimension", "chia kết quả — bắt buộc có cột", "✔", "✔"],
    ["analysis_unit", "định danh một dòng LÀ GÌ", "✘", "✔"],
    ["computed_value", "đại lượng đo hoặc dẫn xuất", "✘", "✘"],
    ["context_only", "không bao giờ vào LogicalQueryPlan", "✘", "✘"],
], col_w=[26, 44, 15, 15], row_h=Inches(0.44), size=10,
   aligns=[PP_ALIGN.LEFT, PP_ALIGN.LEFT, PP_ALIGN.CENTER, PP_ALIGN.CENTER])

card(s, Inches(6.95), Inches(4.42), Inches(5.78), Inches(2.18),
     "Trực giao, không thay thế nhau", [
         "derived.product_count  =  binding=aggregate  (lấy giá trị thế nào)",
         "                       +  counts_unit=entity.product_listing  (đếm gì)",
         "",
         "entity.shop có cột shop_id → vừa GROUP BY được vừa đếm được.",
         "entity.product_listing không có cột → chỉ đếm được.",
         "Hai năng lực độc lập, phải khai bằng hai trường khác nhau.",
         "",
         "Thêm một đơn vị đếm được = sửa catalog, KHÔNG phải thêm nhánh if.",
     ], accent=BLUE, body_size=10)

# --- 09 CAPABILITY MATCHER -------------------------------------------------
s = d.slide("CapabilityMatcher — từ chối có cấu trúc thay vì đoán gần đúng",
            "§3.5–3.6 · Thay CertifiedShape; là nguồn duy nhất để build IntentRegistry")

tf = tb(s, MARGIN, CONTENT_TOP, Inches(6.3), Inches(0.4))
_txt(tf, "Quy tắc chọn — thứ tự bắt buộc", 12.5, INK, bold=True)
steps = [
    ("1", "Loại MỌI spec có blocker", "shape, measure thừa/thiếu, grouping, aggregation, filter, qualifier, scope"),
    ("2", "Ưu tiên spec cụ thể theo score", "macro · template · tool · insight"),
    ("3", "Không có spec cụ thể → xét analytical", "thử synthesizer trước, ngoài grammar mới sang decomposer"),
    ("4", "Không có analytical hợp lệ → A-CAPABILITY-MISS", "không hạ xuống macro gần nhất"),
    ("5", "Hoà điểm → cue term phá hoà", "chỉ SAU khi đã lọc blocker"),
    ("6", "Vẫn hoà → clarify", "không tự chọn"),
]
for i, (n, t, sub) in enumerate(steps):
    y = Inches(2.12) + i * Inches(0.72)
    box(s, MARGIN, y, Inches(6.3), Inches(0.63), fill=PANEL if i % 2 == 0 else WHITE)
    box(s, MARGIN, y, Inches(0.04), Inches(0.63), fill=TEAL if i < 3 else AMBER)
    tf = tb(s, MARGIN + Inches(0.2), y + Inches(0.05), Inches(0.34), Inches(0.5))
    _txt(tf, n, 13, TEAL if i < 3 else AMBER, bold=True)
    tf = tb(s, MARGIN + Inches(0.6), y + Inches(0.06), Inches(5.6), Inches(0.55))
    _txt(tf, t, 11, INK, bold=True, space_after=2)
    p = tf.add_paragraph(); _txt(tf, sub, 9.5, MUTED, para=p)

card(s, Inches(7.25), CONTENT_TOP, Inches(5.48), Inches(2.6),
     "A-CAPABILITY-MISS trả bốn phần deterministic", [
         "1  Hệ đã nhận diện measure / grouping / shape nào",
         "2  Blocker THẬT: thiếu dữ liệu · zero variance ·",
         "     unavailable binding · chưa có phép tính duyệt",
         "3  Một đến ba câu hỏi GẦN NHẤT làm được, sinh từ",
         "     CapabilitySpec bằng cách nới đúng MỘT trục",
         "4  Dữ liệu / quyết định cần bổ sung để mở năng lực",
         "",
         "Reason lấy từ CapabilityDecision.decision_blockers —",
         "không suy lại bằng template riêng.",
     ], accent=BLUE, body_size=10)

box(s, Inches(7.25), Inches(4.4), Inches(5.48), Inches(2.2), fill=RGBColor(0xFD, 0xF4, 0xF5))
box(s, Inches(7.25), Inches(4.4), Inches(0.05), Inches(2.2), fill=RED)
tf = tb(s, Inches(7.5), Inches(4.58), Inches(5.0), Inches(1.9))
_txt(tf, "Khả năng khắc phục THẮNG thứ tự phase (§4.5.1)", 11.5, RED, bold=True, space_after=6)
for ln in [
    "Trước: priority = thứ tự gọi trong source ⇒ gate chọn rule",
    "BẮN SỚM NHẤT, không phải rule mô tả đúng vấn đề.",
    "",
    "bgk16  mã 99999999999 không tồn tại",
    "   → hệ nói: “Cần chọn thị trường VN hoặc ID”",
    "bgk14  hỏi lợi nhuận (dataset không có cột)",
    "   → hệ nói: “Thiếu country để khoá scope”",
    "",
    "Cả hai gợi ý một hành động KHÔNG THỂ giúp gì. Luật mới:",
    "min(key=(not fixable, priority)) — issue không khắc phục",
    "được thắng, và không kèm gợi ý “hãy nêu rõ X”.",
]:
    p = tf.add_paragraph()
    _txt(tf, ln, 9.5, BODY, space_after=2, para=p)

# --- 10 SYNTHESIZER --------------------------------------------------------
s = d.slide("DeterministicPlanSynthesizer — lớp ngữ pháp đóng chạy không cần LLM",
            "§5 · Chạy TRƯỚC AnalyticalDecomposer; ngoài ngữ pháp thì chuyển tiếp, không nới")

box(s, MARGIN, CONTENT_TOP, Inches(6.2), Inches(2.5), fill=RGBColor(0x10, 0x1C, 0x28))
tf = tb(s, MARGIN + Inches(0.28), CONTENT_TOP + Inches(0.2), Inches(5.7), Inches(2.2))
_txt(tf, "NGỮ PHÁP RELEASE", 10, RGBColor(0x6F, 0xC7, 0xD1), bold=True, space_after=8)
for ln in [
    "1 bound scalar measure  hoặc  1 certified RatioSpec",
    "×  0..2 bound dimensions",
    "×  shape ∈ {scalar, ratio, ranking, comparison, table}",
    "×  aggregation ∈ CatalogObject.valid_aggregations",
    "×  country BẮT BUỘC",
    "×  optional date",
    "×  ≤ 2 allowed predicate",
    "×  0..1 certified relation",
]:
    p = tf.add_paragraph()
    _txt(tf, ln, 11, RGBColor(0xC8, 0xD6, 0xE2), space_after=3, para=p, font="Consolas")

bullets(s, MARGIN, Inches(4.4), Inches(6.2), [
    ("Chỉ nhận binding column | expression | aggregate.", "tool_computed và context_only "
     "không bao giờ vào SQL plan."),
    ("find_path() KHÔNG được coi là bằng chứng đủ.", "Path phải khớp source, direction, grain "
     "và compiler adapter."),
    ("sum(monthly_sold) bị loại", "vì catalog không cho phép — cộng proxy qua snapshot là tính trùng."),
], size=11, gap=8)

card(s, Inches(7.25), CONTENT_TOP, Inches(5.48), Inches(2.5),
     "Acceptance — số, không phải lời", [
         "Bộ ít nhất 30 NL case có oracle",
         "provider=offline: ≥ 80% case trong grammar → allow",
         "0 case NGOÀI grammar bị synthesizer nhận",
         "Mutation shape/aggregation/grouping → plan phải đổi",
         "     tương ứng hoặc bị chặn",
         "Zero denominator không được thành chia-cho-0,",
         "     count thay thế, hoặc ratio bịa",
     ], accent=GREEN, body_size=10.5)

card(s, Inches(7.25), Inches(4.4), Inches(5.48), Inches(2.2),
     "Vì sao lớp này quan trọng hơn vẻ ngoài của nó", [
         "Đây là lớp trả lời được mà KHÔNG tốn một lời gọi LLM nào.",
         "",
         "Mỗi câu rơi vào ngữ pháp đóng là một câu:",
         "  · không có rủi ro model sinh plan sai",
         "  · độ trễ tính bằng mili-giây, không phải chục giây",
         "  · tái lập 100% giữa các lần chạy",
         "",
         "Ngữ pháp hẹp là lựa chọn có chủ đích, không phải thiếu sót.",
     ], accent=TEAL, body_size=10.5)

# --- 11 DECOMPOSER ---------------------------------------------------------
s = d.slide("AnalyticalDecomposer — tách câu hỏi phức hợp mà không mất ràng buộc",
            "§8 · Thay OpenAnalyticalPlanner. LLM chỉ đề xuất CÁCH TÁCH, không sinh SQL")

tf = tb(s, MARGIN, CONTENT_TOP, Inches(6.2), Inches(0.35))
_txt(tf, "Bốn composition operator — tập ĐÓNG, mỗi cái một hợp đồng riêng", 12, INK, bold=True)

ops = [
    ("side_by_side", "2–4 input · trình bày cạnh nhau",
     "Cho phép khác grain/unit. CẤM join, sum, average hoặc so sánh số tự động.", TEAL),
    ("union_scope", "2–4 input · cùng phép đo, scope rời nhau",
     "Schema/unit/grain giống nhau. VN+ID chỉ union để TRÌNH BÀY, aggregatable=false.", BLUE),
    ("join_on_relation", "đúng 2 input · nối qua relation đã chứng nhận",
     "Chỉ 1:1, N:1, 1:N khi cardinality assertion pass. N:M mặc định disabled.", AMBER),
    ("filter_then_measure", "đúng 2 input · producer sinh entity, consumer đo",
     "Key set lấy từ EXECUTION RESULT, không từ LLM. Tối đa 500 key.", PURPLE),
]
for i, (name, sig, desc, c) in enumerate(ops):
    y = Inches(2.08) + i * Inches(1.12)
    box(s, MARGIN, y, Inches(6.2), Inches(1.0), fill=PANEL)
    box(s, MARGIN, y, Inches(0.045), Inches(1.0), fill=c)
    tf = tb(s, MARGIN + Inches(0.22), y + Inches(0.11), Inches(5.8), Inches(0.85))
    _txt(tf, name, 11.5, c, bold=True, space_after=2, font="Consolas")
    p = tf.add_paragraph(); _txt(tf, sig, 9.5, MUTED, space_after=4, para=p)
    p = tf.add_paragraph(); _txt(tf, desc, 10, BODY, para=p)

card(s, Inches(7.25), CONTENT_TOP, Inches(5.48), Inches(2.42),
     "Không dùng quy tắc “hai topic thì luôn tách”", [
         "AtomicFeasibilityAnalyzer phải CHỨNG MINH một atomic plan",
         "không đủ, trước khi được phép tách:",
         "",
         "  · mọi SQL-bound ref trong một connected relation graph?",
         "  · có đúng MỘT target grain hợp lệ?",
         "  · unit tương thích? fanout có dedupe?",
         "  · output shape biểu diễn được bằng atomic IR?",
         "",
         "Nhiều grain đều hợp lệ ⇒ trả ambiguous_target_grain và",
         "CLARIFY — không chọn theo path cost hay thứ tự tên.",
     ], accent=BLUE, body_size=10)

card(s, Inches(7.25), Inches(4.22), Inches(5.48), Inches(2.38),
     "Ranh giới quyền của LLM trong khâu này", [
         "ĐƯỢC:  đề xuất subrequest, covered atom IDs, compose op",
         "CẤM:   sinh SQL, physical column, file path, join key",
         "",
         "request_hash · digest_hash · request_atoms do CALLER bọc",
         "từ trusted root state. Mọi giá trị model lặp lại trusted",
         "field bị REJECT, không dùng để ghi đè.",
         "",
         "Call budget: 1 proposal + 1/subplan + 1 repair/subplan,",
         "tối đa 4 subplan, mặc định 9 call/request. Vượt → fail-closed,",
         "không hạ xuống macro gần nhất.",
     ], accent=RED, body_size=10)

# --- 12 CONTEXT PACKER + CHART 2 -------------------------------------------
s = d.slide("Topic-routed context và ContextPacker — budget là hợp đồng, không phải gợi ý",
            "CHART 2/4 · §6–7 · Token budget mặc định theo từng stage, ghi vào trace")

cd = CategoryChartData()
cd.categories = ["AtomicPlan\n/P8", "Alternate\n/P10", "Generate\n/P2", "Critic\n/P9",
                 "Decomp.\nproposal", "Atomic\nrepair", "Adjudicate\n/P11", "Extract\n/P6"]
cd.add_series("Token budget", (6000, 6000, 4000, 4000, 3000, 3000, 3000, 2000))
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, MARGIN, Inches(1.78),
                        Inches(7.15), Inches(3.5), cd)
ch = gf.chart
style_chart(ch, size=10, legend=False)
pl = ch.plots[0]
pl.gap_width = 45
pl.has_data_labels = True
pl.data_labels.font.size = Pt(10)
pl.data_labels.font.bold = True
pl.data_labels.font.color.rgb = INK
pl.data_labels.font.name = FONT
color_points(pl, [BLUE, BLUE, TEAL, TEAL, AMBER, AMBER, PURPLE, GREY])
ch.value_axis.has_major_gridlines = True
ch.value_axis.major_gridlines.format.line.color.rgb = LINE
ch.value_axis.format.line.fill.background()
ch.category_axis.format.line.color.rgb = LINE

bullets(s, MARGIN, Inches(5.4), Inches(7.15), [
    ("Packer tự canonical-render rồi tự đếm token —", "không tin estimated_tokens do caller truyền."),
    ("Không bao giờ drop:", "hard constraints · digest · required refs/relations · validator "
     "feedback cho repair. Hard block vượt budget ⇒ fail context_budget_unsatisfied, "
     "KHÔNG cắt invariant."),
], size=11, gap=7)

card(s, Inches(8.1), Inches(1.78), Inches(4.63), Inches(2.6),
     "TopicRouter chỉ THU HẸP, không cấp quyền", [
         "Router KHÔNG chọn intent hay capability",
         "Router KHÔNG mở ref / relation / filter mới",
         "Router KHÔNG ra safety decision",
         "Router chỉ chọn context item cho planner",
         "",
         "Topic chưa qua gate ⇒ về broad slice đã admit,",
         "ghi topic_gate_disabled, KHÔNG đổi capability.",
         "",
         "Không bao giờ bỏ topic thứ ba — overflow giữ",
         "toàn bộ metadata, router không truncate.",
     ], accent=TEAL, body_size=10)

card(s, Inches(8.1), Inches(4.55), Inches(4.63), Inches(2.05),
     "Điều kiện bật routing — không có ngoại lệ", [
         "required-ref recall        = 100%",
         "required-relation recall   = 100%",
         "plan-valid rate            không giảm",
         "false_allow_rate           = 0",
         "mọi adversarial case       pass",
         "",
         "Token giảm là mục tiêu PHỤ, không được đem",
         "đổi lấy correctness.",
     ], accent=GREEN, body_size=10)

# --- 13 EVIDENCE -----------------------------------------------------------
s = d.slide("Chuỗi truy vết — vì sao mỗi con số đều chỉ về được nguồn gốc của nó",
            "Evidence là bản ghi bắt buộc, không phải metadata tuỳ chọn")

chain = [
    ("Dataset version", "hash immutable, pin cho TOÀN request", BLUE),
    ("Artifact + row key", "stable row/field key, không phải index", BLUE),
    ("Công thức + unit", "formula_version, unit, currency_code", TEAL),
    ("Evidence ID", "dataset ver + execution/subplan ID + row key", TEAL),
    ("Claim trong answer", "verifier đối chiếu từng chữ số", AMBER),
    ("Citation hiển thị", "[ev:…] phải trỏ evidence CÓ THẬT", RED),
]
for i, (t, sub, c) in enumerate(chain):
    x = MARGIN + i * Inches(2.06)
    box(s, x, CONTENT_TOP, Inches(1.88), Inches(1.55), fill=PANEL)
    box(s, x, CONTENT_TOP, Inches(1.88), Inches(0.05), fill=c)
    tf = tb(s, x + Inches(0.15), CONTENT_TOP + Inches(0.2), Inches(1.6), Inches(1.3))
    _txt(tf, t, 10.5, INK, bold=True, space_after=5)
    p = tf.add_paragraph(); _txt(tf, sub, 8.8, BODY, para=p)
    if i < 5:
        a = tb(s, x + Inches(1.88), CONTENT_TOP + Inches(0.6), Inches(0.18), Inches(0.3))
        _txt(a, "›", 13, GREY, bold=True, align=PP_ALIGN.CENTER)

tf = tb(s, MARGIN, Inches(3.55), Inches(6.2), Inches(0.35))
_txt(tf, "Output thật của hệ — trích nguyên văn, chạy offline 09/08", 12, INK, bold=True)
mono(s, MARGIN, Inches(3.95), Inches(6.2), Inches(2.65), [
    "Kết quả",
    "  Có 668 listing [ev:da6f3eef79f3:0001] trong phạm vi đã chọn.",
    "",
    "Phạm vi",
    "  Thị trường VN, snapshot 2026-07-03.",
    "",
    "Cách tính",
    "  Lọc đúng thị trường và snapshot, sau đó đếm distinct",
    "  product_listing_key.",
    "",
    "Giới hạn",
    "  Đây là số listing, không phải số SKU và không phải",
    "  số dòng snapshot.",
], size=10, highlight={1: RGBColor(0x8F, 0xE3, 0xC0), 12: RGBColor(0xFF, 0xCF, 0x9A),
                       13: RGBColor(0xFF, 0xCF, 0x9A)})

card(s, Inches(7.05), Inches(3.55), Inches(5.68), Inches(1.5),
     "Mỗi câu trả lời allow đều mang năm mục cố định", [
         "Kết quả · Phạm vi · Cách tính · Giới hạn · Độ tin cậy",
         "",
         "“Độ tin cậy: High” được định nghĩa tường minh là mức đầy đủ",
         "và nhất quán của EVIDENCE — không phải xác suất đúng.",
     ], accent=TEAL, body_size=10)

card(s, Inches(7.05), Inches(5.2), Inches(5.68), Inches(1.4),
     "Cạm bẫy: không viết chữ số vào message từ chối", [
         "verifier.scan_numbers quét mọi số và đòi evidence. Câu abstain",
         "không mang evidence, nên “1.157 listing” trong capability_messages",
         "bị chấm là số bịa — đã làm eval rơi từ 1.0 xuống 0.77.",
         "Mô tả phạm vi BẰNG LỜI.",
     ], accent=RED, body_size=10)

# --- 14 VÍ DỤ ABSTAIN / CLARIFY  (slide bắt buộc) --------------------------
s = d.slide("Từ chối đúng cách — sáu ca thật hệ đã chạy",
            "Trích nguyên văn output, provider=offline, 09/08/2026. Đây là HÀNH VI ĐÚNG, không phải lỗi")

cases = [
    ("ABSTAIN", "Lợi nhuận và margin tại VN là bao nhiêu?",
     "Dataset không có giá vốn, phí sàn hay chi phí vận hành nên không tính được lợi nhuận. "
     "… Vẫn trả lời được doanh thu proxy ước tính, giá và lượt bán proxy. "
     "Ví dụ: 'Doanh thu proxy ước tính ở VN tại snapshot mới nhất là bao nhiêu?'",
     "Nêu blocker THẬT + gợi ý câu gần nhất LÀM ĐƯỢC", RED),
    ("ABSTAIN", "Dự báo doanh số tháng sau tại VN",
     "Ba snapshot không đủ để lập dự báo hoặc seasonality đáng tin cậy. "
     "… Vẫn mô tả được chênh lệch giữa các snapshot đã quan sát.",
     "Từ chối ngoại suy — 3 điểm không thành xu hướng", RED),
    ("CLARIFY", "Giá trung bình tại Việt Nam và Indonesia cộng lại?",
     "Không thể cộng, quy đổi hoặc kết luận hơn-kém giữa VND và IDR: contract cross-tier "
     "derived value T-8c chưa được phê duyệt.",
     "Cross-currency là hard block, không phải tuỳ chọn", AMBER),
    ("CLARIFY", "Vì sao số listing tại VN giảm mạnh từ 01/07 đến 03/07?",
     "Evidence chỉ phủ 2026-07-03→2026-07-03 thay vì 2026-07-01→2026-07-03 đã hỏi.",
     "A22 coverage — trước 09/08 ca này trả “668” và PASS", AMBER),
    ("ABSTAIN", "Xếp hạng nhóm có giá trị cao nhất (nhiều nhóm bằng nhau)",
     "Nhiều nhóm cùng đạt giá trị cao nhất nên không xếp hạng được; chọn một nhóm sẽ là "
     "quyết định của hệ chứ không phải của dữ liệu.  [A22-ALIGN-RANK-TIE]",
     "Hoà thì không tự phá hoà", RED),
    ("ALLOW", "Tìm sản phẩm cùng mẫu tương tự \"id:1112776376:46456356622\"",
     "SCORA Honey Glow Tone Up Cream 30 Gr (điểm 0.95) [ev:794fca742fae:0001]; … "
     "Điểm chỉ dùng để xếp hạng tương đồng; không khẳng định cùng mẫu hoặc cùng SKU.",
     "Trả lời được nhưng vẫn tự giới hạn tuyên bố", GREEN),
]
for i, (act, q, ans, why, c) in enumerate(cases):
    col, row = i % 2, i // 2
    x = MARGIN + col * Inches(6.16)
    y = Inches(1.62) + row * Inches(1.72)
    box(s, x, y, Inches(5.95), Inches(1.58), fill=PANEL)
    box(s, x, y, Inches(0.045), Inches(1.58), fill=c)
    bdg = box(s, x + Inches(0.18), y + Inches(0.13), Inches(0.82), Inches(0.24), fill=c)
    tfb = bdg.text_frame
    tfb.margin_left = tfb.margin_right = tfb.margin_top = tfb.margin_bottom = 0
    tfb.word_wrap = False
    _txt(tfb, act, 8, WHITE, bold=True, align=PP_ALIGN.CENTER)
    tf = tb(s, x + Inches(1.1), y + Inches(0.13), Inches(4.7), Inches(0.28))
    _txt(tf, q, 9.5, INK, bold=True)
    tf = tb(s, x + Inches(0.2), y + Inches(0.46), Inches(5.55), Inches(0.78))
    _txt(tf, "“" + ans + "”", 9.2, BODY, italic=True)
    tf = tb(s, x + Inches(0.2), y + Inches(1.26), Inches(5.55), Inches(0.26))
    _txt(tf, "→ " + why, 9, c, bold=True)

box(s, MARGIN, Inches(6.75), W - 2 * MARGIN, Emu(9525), fill=LINE)

# --- 15 CHART 3: BGK-20 ----------------------------------------------------
s = d.slide("Đánh giá độc lập 20 câu — và sáu lớp lỗi đã khắc phục",
            "CHART 3/4 · Ground truth tính bằng pandas thuần, KHÔNG import gladiators")

cd = CategoryChartData()
cd.categories = ["Bỏ lỡ\n(đáng lẽ trả lời được)", "Từ chối đúng", "Hiển thị SỐ SAI", "Trả lời đúng"]
cd.add_series("Số câu / 20", (9, 6, 3, 2))
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, MARGIN, Inches(1.78),
                        Inches(6.1), Inches(2.95), cd)
ch = gf.chart
style_chart(ch, size=10.5, legend=False)
pl = ch.plots[0]
pl.gap_width = 55
pl.has_data_labels = True
pl.data_labels.font.size = Pt(12)
pl.data_labels.font.bold = True
pl.data_labels.font.color.rgb = INK
pl.data_labels.font.name = FONT
color_points(pl, [AMBER, GREEN, RED, BLUE][::-1])
ch.value_axis.has_major_gridlines = True
ch.value_axis.major_gridlines.format.line.color.rgb = LINE
ch.value_axis.format.line.fill.background()

tf = tb(s, MARGIN, Inches(4.82), Inches(6.1), Inches(0.9))
_txt(tf, "Chỉ số KHÔNG được đánh đổi: “hiển thị số sai” phải về 0.", 11.5, RED,
     bold=True, space_after=4)
p = tf.add_paragraph()
_txt(tf, "Tăng số câu trả lời được bằng cách NỚI LỎNG kiểm tra là đi ngược toàn bộ mục đích "
         "của kiến trúc này. Sau mỗi thay đổi, verifier_mutation_detection phải giữ 1.0 — "
         "nếu nó tụt, bản vá đã tắt một phép kiểm chứ không sửa một lỗi.", 10.5, BODY, para=p)

card(s, MARGIN, Inches(5.85), Inches(6.1), Inches(0.75),
     "Ba giới hạn của chính phép đo này — nói rõ để không đọc quá lời", [
         "N=20 (một câu lật đổi 5%) · bộ câu soạn SAU khi đã biết điểm yếu · "
         "chấm bằng luật máy, ba ca wrong_value đã kiểm tay",
     ], accent=GREY, title_size=10.5, body_size=9.5)

table(s, Inches(7.05), Inches(1.78), Inches(5.68), [
    ["Lớp lỗi", "Ca", "Trạng thái"],
    ["A · Entity ref là đơn vị phân tích,\nkhông phải khoá gom nhóm", "bgk01 · 02\nbgk08 · 11", "✔ đã hiện thực"],
    ["B · Coverage ≠ containment;\ntiền đề không được kiểm", "bgk13", "✔ đã hiện thực"],
    ["C · Phép đếm thừa hưởng bộ lọc\ncủa phép đo", "bgk03 · 10", "✔ đã hiện thực"],
    ["D · Blocker không khắc phục được\nphải thắng blocker khắc phục được", "bgk14 · 16", "✔ đã hiện thực"],
    ["E · Ánh xạ chữ → ký hiệu", "bgk05 · 11", "✔ đã hiện thực"],
    ["F · Chính sách trọng tài LLM", "toàn bộ", "✔ trace; precedence giữ nguyên"],
], col_w=[52, 18, 30], row_h=Inches(0.6), size=9.5, head_size=10)

tf = tb(s, Inches(7.05), Inches(6.05), Inches(5.68), Inches(0.55))
_txt(tf, "Xác minh lại 10/08:", 10.5, GREEN, bold=True, space_after=3)
p = tf.add_paragraph()
_txt(tf, "bgk01 → shop_count=10 ✔ · bgk02/11 crash → clarify có rule_id ✔ · "
         "bgk03 → 577/91 khớp oracle ✔ · bgk13 → clarify coverage ✔ · "
         "bgk16 → A-ENTITY-NOT-FOUND ✔ · bgk14 → A-MISSING-PROFIT ✔", 9.5, BODY, para=p)

# --- 16 CHART 4: EVAL SUITES -----------------------------------------------
s = d.slide("Trạng thái đo — bảy suite, đo lại sau vòng sửa sáu lớp lỗi",
            "CHART 4/4 · Đo tại HEAD nhánh MVP_Dai_V2 (1cf7327), provider=offline, --runs 3")

cd = CategoryChartData()
cd.categories = ["legacy questions\n60×3", "V2\n11×3", "A19\n6×3", "boundaries\n9×3",
                 "ambiguity\n4×3", "critic\n4×3", "counting\n3×3"]
cd.add_series("Điểm", (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0))
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, MARGIN, Inches(1.78),
                        Inches(7.4), Inches(3.35), cd)
ch = gf.chart
style_chart(ch, size=10, legend=False)
pl = ch.plots[0]
pl.gap_width = 50
pl.has_data_labels = True
dl = pl.data_labels
dl.number_format = '0.000'
dl.number_format_is_linked = False
dl.font.size = Pt(10.5)
dl.font.bold = True
dl.font.color.rgb = INK
dl.font.name = FONT
color_points(pl, [GREEN] * 7)
va = ch.value_axis
va.maximum_scale = 1.0
va.minimum_scale = 0.0
va.has_major_gridlines = True
va.major_gridlines.format.line.color.rgb = LINE
va.format.line.fill.background()

box(s, MARGIN, Inches(5.32), Inches(7.4), Inches(1.28), fill=RGBColor(0xFF, 0xFB, 0xF0))
box(s, MARGIN, Inches(5.32), Inches(0.05), Inches(1.28), fill=AMBER)
tf = tb(s, MARGIN + Inches(0.25), Inches(5.46), Inches(7.0), Inches(1.1))
_txt(tf, "Regression legacy 0.65 ghi trong CLAUDE.md §5 KHÔNG còn tái lập — và không phải do "
         "vòng sửa này", 11, AMBER, bold=True, space_after=5)
p = tf.add_paragraph()
_txt(tf, "Đo lại chính suite đó ở commit gốc TRƯỚC vòng sửa (31c1d6b, dựng worktree riêng) "
         "cũng cho 1.0. Con số 0.65/0.879/0.833 trong CLAUDE.md §5 đo ngày 08/08 tại 1df8e5b "
         "và đã cũ; nguyên nhân nó biến mất chưa được truy, nên deck KHÔNG nhận công. "
         "Điều kiểm được là trạng thái hiện tại, đo bằng lệnh in ở phụ đề.", 10, BODY, para=p)

card(s, Inches(8.32), Inches(1.78), Inches(4.41), Inches(2.35),
     "Chỉ số giữ nguyên 1.0 — không được phép tụt", [
         "verifier_mutation_detection     1.0",
         "evidence_accuracy               1.0",
         "citation_recall / precision     1.0",
         "routing_accuracy                1.0",
         "semantic_plan_success_rate      1.0",
         "plan_stability_rate             1.0",
         "crash_rate                      0.0",
     ], accent=GREEN, body_size=10)

card(s, Inches(8.32), Inches(4.3), Inches(4.41), Inches(2.3),
     "Hai luật vận hành khi đọc số", [
         "1 · Xác minh bằng HÀNH VI, không bằng cấu trúc.",
         "     Ref do tool tính trông giống hệt measure thật;",
         "     điểm bị void trông giống hệt điểm khoẻ mạnh.",
         "",
         "2 · Harness báo lạ thì NGHI HARNESS TRƯỚC.",
         "     Đã có harness nuốt exception khiến 188 phép đo",
         "     chạy với input rỗng.",
     ], accent=BLUE, body_size=10)

# --- 17 LLM vs DETERMINISTIC -----------------------------------------------
s = d.slide("LLM đóng góp gì — một phép đo trung thực đến mức bất tiện",
            "§4.12 · Cùng 20 câu, hai chế độ. Kết quả không phải thứ ta mong đợi")

for i, (v, l, c) in enumerate([
    ("0,9s", "toàn bộ 20 câu · offline", GREEN),
    ("394,1s", "toàn bộ 20 câu · LLM (deepseek)", RED),
    ("438×", "chi phí thời gian", RED),
    ("19/20", "kết cục GIỐNG HỆT NHAU", AMBER),
]):
    stat(s, MARGIN + i * Inches(3.1), CONTENT_TOP, Inches(2.9), v, l, accent=c, vsize=31)

box(s, MARGIN, Inches(2.78), W - 2 * MARGIN, Emu(9525), fill=LINE)

tf = tb(s, MARGIN, Inches(3.05), Inches(6.2), Inches(0.35))
_txt(tf, "Câu duy nhất khác biệt", 12, INK, bold=True)
mono(s, MARGIN, Inches(3.45), Inches(6.2), Inches(0.95), [
    "bgk16   offline → clarify / A-CROSS-CURRENCY-SCOPE",
    "        LLM     → clarify / A22-ALIGN-MEASURE",
], size=10.5)
tf = tb(s, MARGIN, Inches(4.55), Inches(6.2), Inches(0.5))
_txt(tf, "Một lý do từ chối đổi thành một lý do từ chối khác — không phải một câu trả lời tốt hơn.",
     10.5, BODY, italic=True)

table(s, MARGIN, Inches(5.15), Inches(6.2), [
    ["Đo trên 32 case có nhãn", "Độ đúng intent"],
    ["LLM thô", "71,9%"],
    ["Deterministic", "53,1%"],
    ["Sau khi MERGE (thực tế đang chạy)", "53,1%"],
], col_w=[70, 30], row_h=Inches(0.35), size=10.5,
   aligns=[PP_ALIGN.LEFT, PP_ALIGN.RIGHT])

card(s, Inches(7.05), Inches(3.05), Inches(5.68), Inches(1.75),
     "Đọc con số này cho đúng", [
         "LLM ĐANG đúng hơn ở tầng intent thô (71,9% so với 53,1%),",
         "nhưng luật precedence trong khâu merge cho deterministic",
         "thắng — nên đóng góp thực tế bằng 0.",
         "",
         "Đây KHÔNG phải lỗi cần vá gấp. Nó là một quyết định an toàn",
         "đang quá chặt.",
     ], accent=AMBER, body_size=10)

card(s, Inches(7.05), Inches(4.95), Inches(5.68), Inches(1.65),
     "Phạm vi vòng này — cố ý hẹp", [
         "✘  KHÔNG đổi luật precedence — đó là quyết định về an toàn,",
         "     cần W3/W4 cùng sign-off.",
         "✔  GHI chi phí/lợi ích vào trace từng request: llm_intent,",
         "     deterministic_intent, merge_winner, merge_reason.",
         "✔  KHÔNG gọi LLM ở nhánh mà precedence chắc chắn ghi đè.",
         "     Tối ưu chi phí thuần; đổi hành vi ở đây là LỖI.",
     ], accent=GREEN, body_size=10)

# --- 18 INSIGHT MART -------------------------------------------------------
s = d.slide("Insight Mart, PAM và dashboard — phần sản phẩm, cùng kỷ luật bằng chứng",
            "§12 · Bundle bất biến, build hai lần phải cho hash và thứ tự giống 100%")

mono(s, MARGIN, CONTENT_TOP, Inches(5.5), Inches(1.55), [
    "artifacts/insights/<dataset_version>/",
    "├── pam_scorecard.csv",
    "├── insight_cards.jsonl",
    "├── insight_evidence.jsonl",
    "└── manifest.json",
], size=11)

card(s, MARGIN, Inches(3.35), Inches(5.5), Inches(1.6),
     "Giao thức build — chống ghi đè âm thầm", [
         "1  Acquire lock theo dataset_version",
         "2  Ghi vào temp dir cùng parent → validate → atomic rename",
         "3  Cùng content hash  → idempotent success",
         "4  Cùng version, KHÁC hash → IMMUTABLE_INSIGHT_COLLISION",
         "     và KHÔNG overwrite",
     ], accent=BLUE, body_size=10)

card(s, MARGIN, Inches(5.1), Inches(5.5), Inches(1.5),
     "PAM là phân khúc LISTING dựa trên proxy — không phải buyer-RFM", [
         "pam_score = 100 × (0,30·activity + 0,40·momentum + 0,30·monetary)",
         "Chấm trong cohort country × platform_category; cohort nhỏ fallback country.",
         "KHÔNG BAO GIỜ rank VN với ID. Segment theo precedence cố định:",
         "InsufficientData → Dormant → Cooling → Star → Rising → Steady",
     ], accent=PURPLE, body_size=9.8)

tf = tb(s, Inches(6.4), CONTENT_TOP, Inches(6.33), Inches(0.35))
_txt(tf, "Bốn miner deterministic — và điều kiện KHÔNG phát card", 12, INK, bold=True)
miners = [
    ("Top movers", "positive snapshot_sales_delta_clean, top-k",
     "không phát khi delta null/≤0 hoặc transition qua gap", BLUE),
    ("Price move", "nêu hai biến cùng thay đổi, evidence riêng",
     "cấm causal wording; loại sentinel và previous price ≤ 0", TEAL),
    ("Voucher gap VN", "median sold proxy từng nhóm + sample size",
     "mỗi nhóm ≥10; cấm dùng chữ “lift” hay “hiệu quả”", AMBER),
    ("Data quality", "count, scope ảnh hưởng, phép tính bị ảnh hưởng",
     "không phát khi issue không có source/row mapping", RED),
]
for i, (n, does, nots, c) in enumerate(miners):
    y = Inches(2.05) + i * Inches(0.98)
    box(s, Inches(6.4), y, Inches(6.33), Inches(0.86), fill=PANEL)
    box(s, Inches(6.4), y, Inches(0.045), Inches(0.86), fill=c)
    tf = tb(s, Inches(6.62), y + Inches(0.09), Inches(5.95), Inches(0.72))
    _txt(tf, n, 10.5, c, bold=True, space_after=2)
    p = tf.add_paragraph(); _txt(tf, does, 9.5, BODY, space_after=2, para=p)
    p = tf.add_paragraph(); _txt(tf, "✘  " + nots, 9, MUTED, para=p)

card(s, Inches(6.4), Inches(6.0), Inches(6.33), Inches(0.6),
     "Ràng buộc UI", [
         "Percent, local currency và count KHÔNG dùng chung axis · không có country=all "
         "cho monetary chart · empty state phải nói “không đủ nhóm”, không render chart 0",
     ], accent=GREY, title_size=10.5, body_size=9.5)

# --- 19 EXTERNAL -----------------------------------------------------------
s = d.slide("External context — mở ra thế giới mà không để nó nhiễm vào con số",
            "§13 · Tavily. Mặc định OFF; replay bắt buộc, live có điều kiện")

tf = tb(s, MARGIN, CONTENT_TOP, Inches(6.2), Inches(0.35))
_txt(tf, "Ranh giới cứng — external không bao giờ chạm vào số nội bộ", 12, INK, bold=True)
walls = [
    "source_tier = \"external\"  ·  mapping_status = \"needs_review\"",
    "admission   = \"context_only\"  — clamp, không có ngoại lệ",
    "CẤM tính toán hoặc suy nhân quả xuyên tier   [A20-TIER]",
    "KHÔNG dùng để tính KPI, PAM, competitor price hay causal claim",
    "External panel tách hẳn khỏi internal KPI trên UI",
]
for i, ln in enumerate(walls):
    y = Inches(2.05) + i * Inches(0.5)
    box(s, MARGIN, y, Inches(6.2), Inches(0.42), fill=PANEL if i % 2 == 0 else WHITE)
    box(s, MARGIN, y, Inches(0.04), Inches(0.42), fill=RED)
    tf = tb(s, MARGIN + Inches(0.22), y + Inches(0.09), Inches(5.85), Inches(0.3))
    _txt(tf, ln, 10.5, BODY)

card(s, MARGIN, Inches(4.75), Inches(6.2), Inches(1.85),
     "Ba mode, và vì sao replay là điều kiện bắt buộc", [
         "cache_only   không gọi network KỂ CẢ khi cache miss. Không cần API key.",
         "record       gọi network, sanitize → relevance → admission RỒI mới commit cache.",
         "live         CONDITIONAL — đúng một câu đã rehearsal.",
         "",
         "Acceptance: replay ×3 phải có provider calls = 0 và Evidence hash/thứ tự",
         "GIỐNG HỆT bản record. Không tái lập được thì không được tính là đã chạy.",
     ], accent=BLUE, body_size=10)

tf = tb(s, Inches(7.05), CONTENT_TOP, Inches(5.68), Inches(0.35))
_txt(tf, "Công thức relevance — có trọng số, có ngưỡng calibrate", 12, INK, bold=True)
mono(s, Inches(7.05), Inches(2.05), Inches(5.68), Inches(1.35), [
    "relevance_score =",
    "    0.55 × tavily_score",
    "  + 0.30 × anchor_coverage",
    "  + 0.15 × lexical_overlap",
], size=10.5)

card(s, Inches(7.05), Inches(3.55), Inches(5.68), Inches(1.5),
     "Ngưỡng phải do người gán nhãn quyết", [
         "Label tối thiểu 30 result THẬT với HAI reviewer.",
         "Chọn threshold trong điều kiện precision ≥ 0,80 và",
         "injection leakage = 0.",
         "Result không đạt bị drop kèm reason code — và nếu không",
         "còn result nào, câu trả lời nội bộ GIỮ NGUYÊN.",
     ], accent=AMBER, body_size=10)

card(s, Inches(7.05), Inches(5.2), Inches(5.68), Inches(1.4),
     "Trạng thái thật hôm nay", [
         "Cờ live search mặc định OFF · E6 PENDING, chưa sign-off",
         "Phase 6 external: 12/12 ở chế độ offline-no-network",
         "Badge bắt buộc trên UI: provider · LIVE|RECORDED REPLAY ·",
         "context only · retrieved_at · domain · content hash",
     ], accent=GREY, body_size=10)

# --- 20 CLAIM BOUNDARY -----------------------------------------------------
s = d.slide("Ranh giới tuyên bố — thứ quyết định độ tin cậy của cả hệ thống",
            "§18 · Được nói gì, và tuyệt đối không được nói gì")

box(s, MARGIN, CONTENT_TOP, Inches(6.1), Inches(3.55), fill=RGBColor(0xEF, 0xF7, 0xF1))
box(s, MARGIN, CONTENT_TOP, Inches(0.05), Inches(3.55), fill=GREEN)
tf = tb(s, MARGIN + Inches(0.28), CONTENT_TOP + Inches(0.18), Inches(5.6), Inches(3.2))
_txt(tf, "✔   ĐƯỢC TUYÊN BỐ", 12.5, GREEN, bold=True, space_after=9)
for ln in [
    "LLM lập kế hoạch trong semantic space ĐÓNG; SQL và composition",
    "thực hiện deterministic.",
    "Topic routing tối ưu context SAU capability admission.",
    "Decomposer hỗ trợ các canonical signature ĐÃ QUA GATE — không",
    "phải truy vấn tự do vô hạn.",
    "Trên benchmark có oracle, mọi câu ALLOW giữ đúng measure,",
    "aggregation, grouping, scope và compound parts.",
    "PAM là phân khúc listing dựa trên proxy.",
    "Price/voucher miner mô tả đồng biến hoặc group difference.",
    "Tavily là external context có provenance, replay bắt buộc.",
]:
    p = tf.add_paragraph()
    _txt(tf, ln, 10.5, BODY, space_after=4, para=p)

box(s, Inches(7.05), CONTENT_TOP, Inches(5.68), Inches(3.55), fill=RGBColor(0xFD, 0xF4, 0xF5))
box(s, Inches(7.05), CONTENT_TOP, Inches(0.05), Inches(3.55), fill=RED)
tf = tb(s, Inches(7.33), CONTENT_TOP + Inches(0.18), Inches(5.2), Inches(3.2))
_txt(tf, "✘   KHÔNG ĐƯỢC TUYÊN BỐ", 12.5, RED, bold=True, space_after=9)
for ln in [
    "“Trả lời được mọi câu hỏi.”",
    "“LLM không thể chọn relation sai trước validator.”",
    "“find_path() hiện tự động dựng mọi join.”",
    "“Context ngắn hơn đồng nghĩa chính xác hơn.”",
    "“subplan_count tự nó là Decomposer.”",
    "“Deterministic đồng nghĩa không thể sai.”",
    "“Dashboard hoặc Tavily đã production-ready.”",
    "Bất kỳ tuyên bố nào về buyer behavior, forecast, profit, ROI",
    "hoặc causal uplift — dataset không có bằng chứng cho chúng.",
]:
    p = tf.add_paragraph()
    _txt(tf, ln, 10.5, BODY, space_after=5, para=p)

box(s, MARGIN, Inches(5.42), W - 2 * MARGIN, Inches(1.18), fill=NAVY)
box(s, MARGIN, Inches(5.42), Inches(0.06), Inches(1.18), fill=TEAL)
tf = tb(s, MARGIN + Inches(0.32), Inches(5.6), W - 2 * MARGIN - Inches(0.7), Inches(0.9))
_txt(tf, "Đang chờ NGƯỜI quyết — không code thay được", 12, RGBColor(0x6F, 0xC7, 0xD1),
     bold=True, space_after=6)
p = tf.add_paragraph()
_txt(tf, "Hai luật chất lượng dữ liệu DR1  ·  PAM golden review  ·  claim-boundary review P13  ·  "
         "fixture gap TC34  ·  policy sentinel giá TC19  ·  6 metric topic-gate ở trạng thái "
         "pending_oracle (cố ý KHÔNG tự chấm)", 11, RGBColor(0xC8, 0xD6, 0xE2), para=p)

# ---------------------------------------------------------------------------
OUT.parent.mkdir(parents=True, exist_ok=True)
d.prs.save(OUT)
print(f"OK  {OUT}  ({len(d.prs.slides.__iter__.__self__._sldIdLst)} slides)")
