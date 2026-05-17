"""Prompt templates for memory generation and consolidation."""

EXTRACT_MEMORY_PROMPT = """Analyze the following conversation and extract reusable cross-session knowledge that would help an AI assistant in future conversations.

Focus on extracting:
1. **User preferences and communication style** — How does the user like to receive information? Any specific format preferences?
2. **Project conventions and decisions** — Naming conventions, architectural choices, technology preferences.
3. **Tool usage patterns** — How does the user prefer to use file operations, search, and other tools?
4. **Domain-specific knowledge** — Facts about the user's projects, environment, or workflow that persist across sessions.

Output a structured list of memory items. Each item should be:
- A concise, self-contained statement (1-2 sentences)
- Specific enough to be actionable
- General enough to be reusable across sessions

If the conversation contains no reusable cross-session knowledge, respond with exactly: NO_MEMORY

Conversation:
{conversation}

Memory items:"""


CONSOLIDATE_MEMORY_PROMPT = """You are a memory consolidation agent. Your task is to merge raw memories and an existing consolidated memory into a single, deduplicated, consolidated memory document.

The consolidated memory will be injected into an AI assistant's system prompt at the start of every session. It must be:

1. **Compact and actionable** — Every bullet should help the assistant understand the user better or work more effectively.
2. **Deduplicated** — If multiple memories express the same or similar knowledge, keep one best phrasing.
3. **Well-organized** — Group related information under clear headings. Prefer many narrow, actionable bullets over a few broad umbrella bullets.
4. **Incremental** — Preserve valuable content from the existing consolidated memory. Integrate new raw memories into it rather than replacing it entirely.

## Deduplication Rules

- **Merge duplicates aggressively**: If several sources say nearly the same thing, merge by keeping one of the original phrasings.
- **Do not cluster on keyword overlap alone**: Group by task intent and context, not just shared keywords.
- **Keep original wording by default**: Only paraphrase when needed to merge duplicates or improve clarity.
- **Prefer many narrow actionable bullets over a few broad umbrella bullets.**
- **Different preferences affecting different defaults should remain separate.**
- **When in doubt, preserve boundaries** — keep separate entries rather than over-merging.

## Output Format

Return only the consolidated memory content in Markdown format. No preamble, no explanation, no code fences.

Existing consolidated memory:
{existing_memory}

Raw memories to consolidate:
{raw_memories}

Consolidated memory:"""
