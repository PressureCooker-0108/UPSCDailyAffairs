import logging
import unicodedata
from datetime import datetime, timezone
from fpdf import FPDF
from models.database import get_top_stories, get_market_data, get_source_diversity

logger = logging.getLogger(__name__)

# ── Color Palette ──
DARK_BG = (15, 23, 42)
CARD_BG = (30, 41, 59)
ACCENT = (59, 130, 246)
ACCENT_LIGHT = (96, 165, 250)
POSITIVE = (34, 197, 94)
NEGATIVE = (239, 68, 68)
TEXT_PRIMARY = (241, 245, 249)
TEXT_SECONDARY = (148, 163, 184)
TEXT_MUTED = (100, 116, 139)
BORDER = (51, 65, 85)
WHITE = (255, 255, 255)


def _sanitize(text: str) -> str:
    """Replace common Unicode characters with ASCII equivalents for PDF latin-1 encoding."""
    replacements = {
        "\u2014": "--",   # em dash
        "\u2013": "-",    # en dash
        "\u2018": "'",    # left single quote
        "\u2019": "'",    # right single quote
        "\u201c": '"',    # left double quote
        "\u201d": '"',    # right double quote
        "\u2026": "...",  # ellipsis
        "\u2022": "*",    # bullet
        "\u00b7": "*",    # middle dot
        "\u2032": "'",    # prime
        "\u2033": '"',    # double prime
        "\u20ac": "EUR",  # euro
        "\u00a3": "GBP",  # pound
        "\u00a5": "JPY",  # yen
        "\u2191": "^",    # up arrow
        "\u2193": "v",    # down arrow
        "\u25b2": "^",    # black up-pointing triangle
        "\u25bc": "v",    # black down-pointing triangle
        "\u2603": "*",    # snowman
        "\u2756": "*",    # black diamond
        "\u2b50": "*",    # star
        "\U0001f4b0": "*",# money bag
        "\U0001f4c8": "*",# chart
        "\U0001f4c9": "*",# chart down
        "\U0001f4ca": "*",# bar chart
        "\U0001f4cb": "*",# clipboard
        "\U0001f4cc": "*",# pushpin
        "\U0001f4ac": "*",# speech balloon
        "\U0001f30d": "*",# globe
        "\U0001f30f": "*",# globe asia
        "\U0001f310": "*",# globe meridians
        "\U0001f4e2": "*",# loudspeaker
        "\u26a1": "*",    # high voltage
        "\U0001f4a1": "*",# light bulb
        "\U0001f4a4": "*",# zzz
        "\U0001f525": "*",# fire
        "\U0001f538": "*",# orange diamond
        "\U0001f539": "*",# blue diamond
        "\U0001f53d": "*",# up button
        "\U0001f53c": "*",# down button
        "\U0001f3b1": "*",# 8-ball
        "\U0001f3c6": "*",# trophy
        "\U0001f3f7": "*",# label
        "\U0001f4f0": "*",# newspaper
        "\U0001f4f1": "*",# mobile phone
        "\U0001f4bb": "*",# laptop
        "\U0001f4dc": "*",# scroll
        "\U0001f4dd": "*",# memo
        "\U0001f4de": "*",# telephone
        "\U0001f4e6": "*",# package
        "\U0001f4ea": "*",# mailbox
        "\U0001f4ec": "*",# open mailbox
        "\U0001f4ef": "*",# horn
        "\U0001f50d": "*",# magnifying glass
        "\U0001f50e": "*",# magnifying glass
        "\U0001f516": "*",# bookmark
        "\U0001f517": "*",# link
        "\U0001f51d": "*",# top
        "\U0001f520": "*",# capital ABCD
        "\U0001f521": "*",# ABCD
        "\U0001f4b5": "*",# dollar
        "\u00a9": "(c)",  # copyright
        "\u00ae": "(r)",  # registered
        "\u2122": "TM",   # trademark
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    # Remove any remaining non-latin-1 characters
    result = []
    for ch in text:
        try:
            ch.encode("latin-1")
            result.append(ch)
        except UnicodeEncodeError:
            result.append("?")
    return "".join(result)


class BriefingPDF(FPDF):
    """Custom PDF class for the Operator Brief."""

    def __init__(self):
        super().__init__("P", "mm", "A4")
        self.set_auto_page_break(auto=True, margin=22)

    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 7)
            self.set_text_color(*TEXT_MUTED)
            self.cell(0, 6, _sanitize("Operator Brief"), align="L")
            self.cell(0, 6, f"Page {self.page_no()}/{{nb}}", align="R", new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(*BORDER)
            self.line(18, self.get_y(), 192, self.get_y())
            self.ln(3)

    def footer(self):
        self.set_y(-18)
        self.set_font("Helvetica", "I", 6.5)
        self.set_text_color(*TEXT_MUTED)
        self.set_draw_color(*BORDER)
        self.line(18, self.get_y(), 192, self.get_y())
        self.ln(2)
        now = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
        self.cell(0, 5, _sanitize(f"Generated automatically on {now}"), align="C")

    def section_title(self, title: str):
        self.ln(3)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*ACCENT_LIGHT)
        self.cell(0, 8, _sanitize(title), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*BORDER)
        self.line(18, self.get_y(), 192, self.get_y())
        self.ln(3)

    def sub_title(self, title: str):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*WHITE)
        self.cell(0, 6, _sanitize(title), new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, text: str, size: int = 8):
        self.set_font("Helvetica", "", size)
        self.set_text_color(*TEXT_SECONDARY)
        self.multi_cell(0, 4.5, _sanitize(text))

    def badge(self, text: str):
        self.set_fill_color(*ACCENT)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 6.5)
        w = self.get_string_width(_sanitize(text.upper())) + 5
        self.cell(w, 5, f" {_sanitize(text.upper())} ", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def draw_card(self, x: float, y: float, w: float, h: float):
        """Draw a filled rounded card background."""
        self.set_fill_color(*CARD_BG)
        self.set_draw_color(*BORDER)
        self.rect(x, y, w, h, style="DF")

    def summary_card(self, title: str, articles: int, sectors: str):
        y_start = self.get_y()
        self.draw_card(18, y_start, 174, 18)
        self.badge("Top Story")
        self.set_xy(24, y_start + 6)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*WHITE)
        self.cell(0, 5, _sanitize(title[:85]), new_x="LMARGIN", new_y="NEXT")
        self.set_xy(24, y_start + 13)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*TEXT_SECONDARY)
        self.cell(0, 4, _sanitize(f"* {articles} articles    |  {sectors}"))
        self.set_y(y_start + 24)

    def stats_row(self, stories: int, sources: int, articles: int):
        y_start = self.get_y()
        cols = [
            ("Stories Tracked", str(stories)),
            ("Sources", str(sources)),
            ("Total Articles", str(articles)),
        ]
        card_w = 55
        gap = 4.5
        start_x = 18
        for i, (label, value) in enumerate(cols):
            x = start_x + i * (card_w + gap)
            self.draw_card(x, y_start, card_w, 18)
            self.set_xy(x, y_start + 3)
            self.set_font("Helvetica", "B", 14)
            self.set_text_color(*ACCENT_LIGHT)
            self.cell(card_w, 6, value, align="C", new_x="LMARGIN", new_y="NEXT")
            self.set_xy(x, y_start + 11)
            self.set_font("Helvetica", "", 6.5)
            self.set_text_color(*TEXT_MUTED)
            self.cell(card_w, 4, label.upper(), align="C")
        self.set_y(y_start + 24)


def generate_pdf_briefing() -> bytes:
    """Generate a formatted PDF briefing from current data."""
    stories = get_top_stories(limit=10)
    market = get_market_data()
    diversity = get_source_diversity()

    pdf = BriefingPDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    # ── Report Header ──
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*ACCENT_LIGHT)
    pdf.cell(0, 10, _sanitize("OPERATOR BRIEF"), align="C", new_x="LMARGIN", new_y="NEXT")
    now = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*TEXT_SECONDARY)
    pdf.cell(0, 6, _sanitize(now), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*ACCENT)
    pdf.line(18, pdf.get_y() + 2, 192, pdf.get_y() + 2)
    pdf.ln(6)

    # ── Executive Summary ──
    pdf.section_title("Executive Summary")
    if stories:
        top = stories[0]
        srcs = ", ".join(top.get("source", [])[:3])
        sects = ", ".join(top.get("sectors", []))
        pdf.summary_card(top["title"], top["article_count"], sects)
        pdf.ln(2)

        total_articles = sum(s.get("article_count", 1) for s in stories[:5])
        pdf.stats_row(len(stories), len(diversity), total_articles)
    pdf.ln(4)

    # ── Market Dashboard ──
    if market:
        pdf.section_title("Market Dashboard")

        indices = [m for m in market if m.get("sector") == "Index"]
        gainers = [m for m in market if m["change_pct"] >= 1.5 and m.get("sector") != "Index"]
        losers = [m for m in market if m["change_pct"] <= -1.5 and m.get("sector") != "Index"]

        col_w = 85
        margin = 18
        gap = 4

        # Left column - Indices
        left_x = margin
        y0 = pdf.get_y()

        idx_h = 8 + 5 * len(indices[:5]) + 2
        pdf.draw_card(left_x, y0, col_w, idx_h)
        pdf.set_xy(left_x + 4, y0 + 2)
        pdf.sub_title("Indices")

        pdf.set_xy(left_x + 4, pdf.get_y())
        pdf.set_font("Helvetica", "B", 6.5)
        pdf.set_text_color(*TEXT_MUTED)
        headers = [("Ticker", 22), ("Price", 18), ("Chg", 18), ("%", 18)]
        for hdr, w in headers:
            pdf.cell(w, 4, _sanitize(hdr), align="L" if hdr == "Ticker" else "R")
        pdf.ln(4)
        pdf.set_draw_color(*BORDER)
        pdf.line(left_x + 4, pdf.get_y(), left_x + col_w - 4, pdf.get_y())
        pdf.ln(1)

        for m in indices[:5]:
            clr = POSITIVE if m["change_pct"] >= 0 else NEGATIVE
            arrow = "^" if m["change_pct"] >= 0 else "v"
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(*WHITE)
            pdf.cell(22, 4, _sanitize(m["ticker"]))
            pdf.set_text_color(*TEXT_SECONDARY)
            pdf.cell(18, 4, f"${m['price']:.2f}", align="R")
            pdf.set_text_color(*clr)
            pdf.cell(18, 4, f"{m['change']:+.2f}", align="R")
            pdf.cell(18, 4, f"{arrow} {m['change_pct']:+.2f}%", align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.set_y(y0 + idx_h + 4)

        # Right column - Movers
        right_x = left_x + col_w + gap
        y1 = y0
        max_rows = max(len(gainers[:5]), len(losers[:5]), 1)
        mover_h = 8 + 4 * max_rows + 4 + 8 + 4 * max_rows + 4 + 2
        pdf.draw_card(right_x, y1, col_w, mover_h)
        pdf.set_xy(right_x + 4, y1 + 2)
        pdf.sub_title("Movers")

        current_y = pdf.get_y()
        pdf.set_xy(right_x + 4, current_y)

        # Gainers
        pdf.set_text_color(*POSITIVE)
        pdf.set_font("Helvetica", "B", 7)
        pdf.cell(0, 4, _sanitize("Gainers"), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        if gainers:
            for m in gainers[:5]:
                pdf.set_font("Helvetica", "", 7)
                pdf.set_text_color(*WHITE)
                name = m["name"][:20]
                pdf.cell(50, 4, _sanitize(f"{name} ({m['ticker']})"))
                pdf.set_text_color(*POSITIVE)
                pdf.cell(25, 4, f"+{m['change_pct']:.2f}%", align="R", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_text_color(*TEXT_MUTED)
            pdf.set_font("Helvetica", "I", 7)
            pdf.cell(0, 4, _sanitize("No significant gainers"), new_x="LMARGIN", new_y="NEXT")

        pdf.ln(2)
        # Losers
        pdf.set_text_color(*NEGATIVE)
        pdf.set_font("Helvetica", "B", 7)
        pdf.cell(0, 4, _sanitize("Losers"), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        if losers:
            for m in losers[:5]:
                pdf.set_font("Helvetica", "", 7)
                pdf.set_text_color(*WHITE)
                name = m["name"][:20]
                pdf.cell(50, 4, _sanitize(f"{name} ({m['ticker']})"))
                pdf.set_text_color(*NEGATIVE)
                pdf.cell(25, 4, f"{m['change_pct']:+.2f}%", align="R", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_text_color(*TEXT_MUTED)
            pdf.set_font("Helvetica", "I", 7)
            pdf.cell(0, 4, _sanitize("No significant losers"), new_x="LMARGIN", new_y="NEXT")

        y_bottom = max(y0 + max(idx_h, mover_h) + 4, pdf.get_y())
        pdf.set_y(y_bottom + 2)

    # ── Top Stories ──
    pdf.section_title("Top Stories")
    if stories:
        for i, story in enumerate(stories, 1):
            srcs = ", ".join(story.get("source", [])[:3])
            sects = ", ".join(story.get("sectors", []))
            summary = story.get("summary", "") or ""
            implications = story.get("why_it_matters", "") or ""

            if pdf.get_y() > 240:
                pdf.add_page()

            y_story = pdf.get_y()
            pdf.set_draw_color(*BORDER)
            pdf.line(18, y_story, 192, y_story)
            pdf.ln(2)

            # Number indicator
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_text_color(*ACCENT)
            pdf.cell(10, 6, f"{i:02d}")
            pdf.set_text_color(*ACCENT_LIGHT)

            # Title
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*WHITE)
            pdf.cell(0, 5, _sanitize(story["title"]), new_x="LMARGIN", new_y="NEXT")

            # Meta row
            pdf.set_font("Helvetica", "", 6.5)
            pdf.set_text_color(*ACCENT_LIGHT)
            pdf.cell(18, 4, f"Score: {story['score']:.1f}")
            pdf.set_text_color(*TEXT_SECONDARY)
            pdf.cell(0, 4, _sanitize(f"Sources: {srcs}   |   {sects}"), new_x="LMARGIN", new_y="NEXT")

            if summary:
                pdf.ln(1)
                pdf.set_font("Helvetica", "", 7.5)
                pdf.set_text_color(*TEXT_SECONDARY)
                pdf.multi_cell(0, 3.8, _sanitize(summary))

            if implications:
                pdf.ln(0.5)
                pdf.set_font("Helvetica", "B", 7)
                pdf.set_text_color(*TEXT_SECONDARY)
                pdf.cell(0, 4, _sanitize(f"Implications: {implications}"), new_x="LMARGIN", new_y="NEXT")

            pdf.ln(3)

    # ── Source Landscape ──
    if diversity:
        if pdf.get_y() > 230:
            pdf.add_page()

        pdf.section_title("Source Landscape")

        y_src = pdf.get_y()
        src_h = 8 + 6 * len(diversity[:10]) + 2
        pdf.draw_card(18, y_src, 174, src_h)
        pdf.set_xy(22, y_src + 2)

        # Header
        pdf.set_font("Helvetica", "B", 6.5)
        pdf.set_text_color(*TEXT_MUTED)
        pdf.cell(50, 4, _sanitize("SOURCE"))
        pdf.cell(20, 4, _sanitize("ARTICLES"), align="R")
        pdf.cell(70, 4, "")
        pdf.cell(20, 4, _sanitize("SHARE"), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*BORDER)
        pdf.line(22, pdf.get_y() + 1, 188, pdf.get_y() + 1)
        pdf.ln(3)

        for d in diversity[:10]:
            pct = d["pct"]
            bar_w = int(pct * 0.65)
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(*WHITE)
            pdf.cell(50, 4.5, _sanitize(d["source"]))
            pdf.set_text_color(*TEXT_SECONDARY)
            pdf.cell(20, 4.5, str(d["count"]), align="R")
            # Progress bar
            pdf.set_fill_color(*ACCENT)
            pdf.set_draw_color(*ACCENT)
            pdf.rect(pdf.get_x() + 2, pdf.get_y() + 1.5, min(bar_w, 68), 3, style="DF")
            pdf.set_xy(pdf.get_x() + 72, pdf.get_y())
            pdf.set_text_color(*TEXT_SECONDARY)
            pdf.cell(20, 4.5, f"{pct}%", align="R", new_x="LMARGIN", new_y="NEXT")

    # ── Output ──
    pdf_bytes = bytes(pdf.output(dest="S"))
    logger.info(f"Generated PDF briefing: {len(pdf_bytes)} bytes")
    return pdf_bytes
