---
type: note
description: Analyze and build knowledge graph links in Obsidian vault. Find orphan notes, suggest connections, add backlinks, visualize link structure. Triggers on /graph, "analyze links", "find orphans", "suggest connections".
last_accessed: 2026-02-25
relevance: 0.69
tier: warm
name: graph-builder
---

# Graph Builder

Analyze vault link structure and build meaningful connections between notes.

## Use Cases

1. **Analyze** — Statistics and insights about vault graph
2. **Find Orphans** — Notes without incoming/outgoing links
3. **Suggest Links** — AI-powered connection recommendations
4. **Add Links** — Batch link creation based on content analysis
5. **Visualize** — Export graph data for visualization

## Quick Commands

| Command | Action |
|---------|--------|
| `/graph analyze` | Full vault analysis with stats |
| `/graph orphans` | List unconnected notes |
| `/graph suggest` | Get link suggestions |
| `/graph add` | Apply suggested links |

## Analysis Output

```
📊 Vault Graph Analysis

Total notes: 247
Total links: 892
Orphan notes: 12
Most connected: [[MEMORY]] (47 links)
Weakest domain: learnings/ (avg 1.2 links/note)

🔗 Suggested connections:
• [[Project A]] ↔ [[Client X]] (mentioned 5x)
• [[Idea B]] → [[MOC/Ideas]] (category match)
```

## Domain Configuration

Domains are configured in `references/domains.md`. Default structure:

- **daily/** — Daily journal entries
- **thoughts/** — Processed ideas, reflections, learnings
- **goals/** — Goal cascade files
- **MOC/** — Maps of Content (index pages)
- **projects/** — Project notes

## Link Building Strategy

1. **Entity extraction** — Find mentions of existing notes
2. **Category mapping** — Connect notes to relevant MOCs
3. **Temporal links** — Link daily entries to related thoughts
4. **Cross-domain** — Bridge domains (project ↔ goal ↔ daily)

## Scripts

- `scripts/analyze.py` — Graph statistics and orphan detection
- `scripts/add_links.py` — Batch link insertion

## References

- `references/domains.md` — Domain definitions and rules
- `references/frontmatter.md` — Frontmatter schema for notes

## Output Format

Reports use plain markdown (for vault notes) or HTML (for Telegram).

For vault: Standard markdown with [[wiki-links]]
For Telegram: HTML tags (b, i, code only)
