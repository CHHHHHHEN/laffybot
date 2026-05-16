"""Extraction prompt for memory generation."""

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
