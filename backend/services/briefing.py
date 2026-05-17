import logging
from datetime import datetime, timezone
from models.database import get_top_stories, save_briefing, get_latest_briefing, get_market_data, get_source_diversity

logger = logging.getLogger(__name__)


def generate_briefing() -> str:
    """Generate an executive-markdown briefing from the current top stories."""
    stories = get_top_stories(limit=10)
    market = get_market_data()
    diversity = get_source_diversity()

    now = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

    lines = []
    lines.append(f"# OPERATOR BRIEF — {now}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Executive Summary
    lines.append("## Executive Summary")
    lines.append("")
    if stories:
        top = stories[0]
        lines.append(f"**Top Story:** {top['title']}")
        lines.append(f"**Coverage:** {top['article_count']} articles from {', '.join(top.get('source', [])[:3])}")
        lines.append(f"**Sectors:** {', '.join(top.get('sectors', []))}")
    lines.append("")
    lines.append(f"**Total tracked stories:** {len(stories)}")
    lines.append(f"**Sources monitoring:** {len(diversity)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Market Dashboard
    if market:
        lines.append("## Market Dashboard")
        lines.append("")
        # Indices
        indices = [m for m in market if m.get("sector") == "Index"]
        if indices:
            lines.append("### Indices")
            lines.append("| Ticker | Price | Change | % Change |")
            lines.append("|--------|-------|--------|----------|")
            for m in indices[:5]:
                arrow = "📈" if m["change_pct"] >= 0 else "📉"
                lines.append(f"| {m['ticker']} | ${m['price']:.2f} | {m['change']:+.2f} | {arrow} {m['change_pct']:+.2f}% |")
            lines.append("")

        # Significant Movers
        gainers = [m for m in market if m["change_pct"] >= 1.5 and m.get("sector") != "Index"]
        losers = [m for m in market if m["change_pct"] <= -1.5 and m.get("sector") != "Index"]

        if gainers:
            lines.append("### 📈 Notable Gainers")
            for m in gainers[:5]:
                lines.append(f"- **{m['name']}** ({m['ticker']}): ${m['price']:.2f} ({m['change_pct']:+.2f}%)")
            lines.append("")

        if losers:
            lines.append("### 📉 Notable Losers")
            for m in losers[:5]:
                lines.append(f"- **{m['name']}** ({m['ticker']}): ${m['price']:.2f} ({m['change_pct']:+.2f}%)")
            lines.append("")

        lines.append("---")
        lines.append("")

    # Top Stories
    lines.append("## Top Stories")
    lines.append("")
    for i, story in enumerate(stories, 1):
        lines.append(f"### {i}. {story['title']}")
        lines.append("")
        lines.append(f"**Score:** {story['score']:.1f} | **Sources:** {', '.join(story.get('source', [])[:3])} | **Sectors:** {', '.join(story.get('sectors', []))}")
        lines.append("")
        if story.get("summary"):
            lines.append(f"> {story['summary']}")
            lines.append("")
        if story.get("why_it_matters"):
            lines.append(f"**⚡ Implications:** {story['why_it_matters']}")
            lines.append("")
        if story.get("url"):
            lines.append(f"🔗 [Read more]({story['url']})")
            lines.append("")
        if i < len(stories):
            lines.append("---")
            lines.append("")

    # Source Diversity
    if diversity:
        lines.append("## Source Landscape")
        lines.append("")
        lines.append("| Source | Articles | Share |")
        lines.append("|--------|----------|-------|")
        for d in diversity[:10]:
            bars = "█" * max(1, int(d["pct"] / 5))
            lines.append(f"| {d['source']} | {d['count']} | {d['pct']}% {bars} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Generated automatically by the Serious Operator News Dashboard*")

    content = "\n".join(lines)
    try:
        save_briefing(content)
    except Exception as e:
        logger.error(f"Failed to save briefing: {e}")

    return content


def get_briefing() -> dict | None:
    """Get the latest stored briefing."""
    return get_latest_briefing()
