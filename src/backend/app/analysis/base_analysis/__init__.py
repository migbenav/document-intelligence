"""Base analysis module — produces the Document Card from the IR.

Combines deterministic local processing (title, statistics, organization type,
index detection, file metadata) with a single LLM call for summary and
classification. See ADR-007 Nivel 1.
"""
