"""Jcyber -- MCP toolkit for agent-driven pentesting.

The agent harness (Claude Code, or any MCP-capable LLM) is the reasoning
loop. Jcyber provides scope-gated scanning tools, an evidence graph, a
finding lifecycle, and long-term memory. Safety is enforced in code: the
scope gate runs before every tool call, exploit actions require operator
confirmation, and all evidence is normalized into the engagement graph.
"""

__version__ = "0.0.0"
