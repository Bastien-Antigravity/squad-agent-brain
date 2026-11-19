#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit tests for RAGMemoryStore remote REST client queries and DocIndexerAgent multi-brain tools.

DATA FLOW:
Tests network-based REST RAG retrieval, graceful fallback on network partitions,
and DocIndexerAgent tools for remote indexing, unmerging, and local vault scanning.

KEY PARAMETERS:
- None (Test suite).
"""

import io
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

import sys
_self_dir = Path(__file__).resolve().parent.parent
if str(_self_dir) not in sys.path:
    sys.path.insert(0, str(_self_dir))

import src.bootstrap as bootstrap
from src.lib.memory import RAGMemoryStore
from src.agents.docindexer import DocIndexerAgent


@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.data = {
        "capabilities": {
            "rag_engine": {"ip": "127.0.0.1", "rest_port": 8093}
        }
    }
    cfg.get_rest_addr.side_effect = lambda cap: "127.0.0.1:8093" if cap == "rag_engine" else None
    cfg.get_capability.side_effect = lambda cap: cfg.data.get("capabilities", {}).get(cap, {})
    return cfg


@pytest.fixture
def mock_logger():
    logger = MagicMock()
    return logger


def test_rag_memory_store_rest_retrieve(mock_config, mock_logger):
    """Verifies RAGMemoryStore successfully queries RAG Engine over REST API."""
    store = RAGMemoryStore(config=mock_config, logger=mock_logger, tenant="test-brain")

    mock_resp_data = {
        "success": True,
        "results": [
            {
                "id": "test-brain:chunk_1",
                "content": "Core architecture guidelines",
                "metadata": {"source_path": "01-Architecture/specs.md"}
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        turns = store.retrieve("architecture guidelines", limit=3)
        assert len(turns) == 1
        assert turns[0]["role"] == "context"
        assert "Core architecture guidelines" in turns[0]["content"]
        assert "[Semantic Context from 01-Architecture/specs.md]" in turns[0]["content"]
        assert "UNTRUSTED_RAG_DATA" in turns[0]["content"]
        assert turns[0]["metadata"]["trust_level"] == "untrusted_rag_data"
        assert turns[0]["metadata"]["brain_id"] == "test-brain"
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://127.0.0.1:8093/api/v1/query"
        body = json.loads(req.data.decode("utf-8"))
        assert body["query"] == "architecture guidelines"
        assert body["brain_id"] == "test-brain"
        assert body["limit"] == 3


def test_rag_memory_store_https_and_response_size_guard(mock_config, mock_logger):
    """Verifies RAGMemoryStore honors TLS configuration and rejects oversized responses."""
    mock_config.data["capabilities"]["rag_engine"]["tls_enabled"] = True
    store = RAGMemoryStore(config=mock_config, logger=mock_logger, tenant="test-brain")
    assert store._build_rag_query_url("127.0.0.1:8093") == "https://127.0.0.1:8093/api/v1/query"

    oversized_resp = MagicMock()
    oversized_resp.status = 200
    oversized_resp.read.return_value = b"x" * (RAGMemoryStore.MAX_RAG_RESPONSE_BYTES + 1)
    oversized_resp.__enter__.return_value = oversized_resp

    with patch("urllib.request.urlopen", return_value=oversized_resp):
        assert store.retrieve("oversized query", limit=2) == []


def test_short_term_memory_strict_session_isolation(mock_config, mock_logger):
    """Verifies ShortTermMemory isolates sessions on add, retrieve, and clear."""
    from src.lib.memory import ShortTermMemory
    mem = ShortTermMemory(config=mock_config, logger=mock_logger, max_size=5)
    mem.add({"role": "user", "content": "Telegram secret"}, session_id="telegram_1")
    mem.add({"role": "user", "content": "Discord message"}, session_id="discord_2")

    tg_turns = mem.retrieve("", session_id="telegram_1")
    dc_turns = mem.retrieve("", session_id="discord_2")
    assert len(tg_turns) == 1 and tg_turns[0]["content"] == "Telegram secret"
    assert len(dc_turns) == 1 and dc_turns[0]["content"] == "Discord message"

    # Clearing telegram_1 must not affect discord_2
    mem.clear(session_id="telegram_1")
    assert mem.retrieve("", session_id="telegram_1") == []
    assert len(mem.retrieve("", session_id="discord_2")) == 1


def test_postgres_memory_store_strict_tenant_isolation(mock_config, mock_logger):
    """Verifies PostgresMemoryStore enforces strict brain_id filtering on retrieve and clear."""
    from src.lib.memory import PostgresMemoryStore
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []

    store = PostgresMemoryStore(
        config=mock_config,
        logger=mock_logger,
        pg_pool=mock_pool,
        schema="08-Squad-Agent",
        brain_id="trading-brain"
    )
    mock_cursor.reset_mock()
    store.retrieve("query", session_id="sess_1", limit=5)
    select_calls = [c[0] for c in mock_cursor.execute.call_args_list if "SELECT" in c[0][0]]
    assert len(select_calls) == 1
    assert "brain_id IS NULL" not in select_calls[0][0]
    assert "WHERE session_id = %s AND brain_id = %s" in select_calls[0][0]
    assert select_calls[0][1] == ("sess_1", "trading-brain", 5)

    mock_cursor.reset_mock()
    store.clear(session_id="sess_1")
    delete_calls = [c[0] for c in mock_cursor.execute.call_args_list if "DELETE" in c[0][0]]
    assert len(delete_calls) == 1
    assert "WHERE session_id = %s AND brain_id = %s" in delete_calls[0][0]
    assert delete_calls[0][1] == ("sess_1", "trading-brain")


def test_rag_memory_store_fallback_on_network_error(mock_config, mock_logger):
    """Verifies RAGMemoryStore gracefully degrades without crashing on network partition."""
    store = RAGMemoryStore(config=mock_config, logger=mock_logger, tenant="test-brain")

    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        # When REST fails and no client/facade is available, returns []
        turns = store.retrieve("unreachable query", limit=3)
        assert turns == []


def test_docindexer_tools_registration(mock_config, mock_logger):
    """Verifies DocIndexerAgent registers remote indexing and purge tools."""
    mock_bus = MagicMock()
    agent = DocIndexerAgent(config=mock_config, logger=mock_logger, pg_pool=MagicMock(), event_bus=mock_bus)

    tool_names = [t.__name__ for t in agent.tools]
    assert "index_brain_document" in tool_names
    assert "purge_brain_index" in tool_names
    assert "scan_and_index_local_vault" in tool_names


def test_docindexer_remote_index_execution(mock_config, mock_logger):
    """Verifies DocIndexerAgent execute_tool dispatches index_brain_document."""
    import asyncio
    mock_bus = MagicMock()
    agent = DocIndexerAgent(config=mock_config, logger=mock_logger, pg_pool=MagicMock(), event_bus=mock_bus)

    mock_resp_data = {"success": True, "chunks_indexed": 2}
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        res = asyncio.run(agent.execute_tool("index_brain_document", {
            "brain_id": "satellite-alpha",
            "rel_path": "specs.md",
            "content": "# Test\nContent",
            "title": "Test"
        }))
        assert "Successfully indexed 'specs.md' into brain 'satellite-alpha'" in res
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://127.0.0.1:8093/api/v1/index/document"


def test_docindexer_remote_purge_execution(mock_config, mock_logger):
    """Verifies DocIndexerAgent execute_tool dispatches purge_brain_index."""
    import asyncio
    mock_bus = MagicMock()
    agent = DocIndexerAgent(config=mock_config, logger=mock_logger, pg_pool=MagicMock(), event_bus=mock_bus)

    mock_resp_data = {"success": True, "deleted_count": 10}
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        res = asyncio.run(agent.execute_tool("purge_brain_index", {
            "brain_id": "satellite-beta"
        }))
        assert "Successfully unmerged/purged brain partition 'satellite-beta' (10 records deleted)" in res
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://127.0.0.1:8093/api/v1/vault/purge"


def test_docindexer_scan_local_vault(mock_config, mock_logger):
    """Verifies DocIndexerAgent scans local directory and indexes markdown files."""
    import asyncio
    mock_bus = MagicMock()
    agent = DocIndexerAgent(config=mock_config, logger=mock_logger, pg_pool=MagicMock(), event_bus=mock_bus)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "note1.md").write_text("# Note 1\nContent 1", encoding="utf-8")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "note2.md").write_text("# Note 2\nContent 2", encoding="utf-8")

        mock_resp_data = {"success": True, "chunks_indexed": 1}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            res = asyncio.run(agent.execute_tool("scan_and_index_local_vault", {
                "brain_id": "satellite-gamma",
                "local_vault_dir": str(tmp_path)
            }))
            assert "Scanned" in res
            assert "indexed 2 markdown file(s) into brain partition 'satellite-gamma'" in res
            assert mock_urlopen.call_count == 2


def test_docindexer_prevent_accidental_root_purge(mock_config, mock_logger):
    """Verifies DocIndexerAgent blocks attempts to purge root obsidian-brain."""
    import asyncio
    mock_bus = MagicMock()
    agent = DocIndexerAgent(config=mock_config, logger=mock_logger, pg_pool=MagicMock(), event_bus=mock_bus)

    res = asyncio.run(agent.execute_tool("purge_brain_index", {"brain_id": "obsidian-brain"}))
    assert "restricted to prevent ecosystem data loss" in res


def test_docindexer_missing_brain_id_fails_fast(mock_logger):
    """Verifies DocIndexerAgent fails fast when no brain_id is provided or configured."""
    import asyncio
    mock_bus = MagicMock()
    empty_cfg = MagicMock()
    empty_cfg.data = {}
    with patch.dict("os.environ", {}, clear=True):
        agent = DocIndexerAgent(config=empty_cfg, logger=mock_logger, pg_pool=MagicMock(), event_bus=mock_bus)
        res = asyncio.run(agent.execute_tool("index_brain_document", {"rel_path": "a.md", "content": "text"}))
        assert "Missing required 'brain_id' parameter" in res


def test_zero_silent_fallback_when_rag_unresolvable(mock_logger):
    """Verifies Zero Silent Fallback: raises ValueError when rag_engine capability is missing."""
    mock_bus = MagicMock()
    broken_cfg = MagicMock()
    broken_cfg.data = {}
    broken_cfg.get_rest_addr.side_effect = ValueError("Capability not found")
    agent = DocIndexerAgent(config=broken_cfg, logger=mock_logger, pg_pool=MagicMock(), event_bus=mock_bus)
    with pytest.raises(ValueError):
        agent._resolve_rag_rest_url()


def test_qa_docmaintainer_and_codeindexer_tool_integrations(mock_config, mock_logger):
    """Verifies QAAgent retains base tools and DocMaintainer/CodeIndexer dispatch specialized RAG REST tools."""
    import asyncio
    from src.agents.qa import QAAgent
    from src.agents.docmaintainer import DocMaintainerAgent
    from src.agents.codeindexer import CodeIndexerAgent

    mock_bus = MagicMock()

    # 1. QAAgent retains BaseAgent file/RAG tools alongside run_squad_tests
    qa_agent = QAAgent(config=mock_config, logger=mock_logger, pg_pool=MagicMock(), event_bus=mock_bus)
    qa_tools = [t.__name__ for t in qa_agent.tools]
    assert "query_rag_engine" in qa_tools
    assert "read_workspace_file" in qa_tools
    assert "write_workspace_file" in qa_tools
    assert "run_squad_tests" in qa_tools

    # 2. DocMaintainerAgent drift & doc-sync tools
    doc_maint = DocMaintainerAgent(config=mock_config, logger=mock_logger, pg_pool=MagicMock(), event_bus=mock_bus)
    dm_tools = [t.__name__ for t in doc_maint.tools]
    assert "check_documentation_drift" in dm_tools
    assert "sync_code_documentation" in dm_tools

    mock_drift_resp = MagicMock()
    mock_drift_resp.read.return_value = json.dumps({"success": True, "drifted": [{"code_id": "a.go", "doc_id": "b.md"}]}).encode("utf-8")
    mock_drift_resp.__enter__.return_value = mock_drift_resp

    with patch("src.agents.docmaintainer.urllibUrlopen", return_value=mock_drift_resp):
        drift_out = asyncio.run(doc_maint.execute_tool("check_documentation_drift", {"workspace": "config-server"}))
        assert "Detected 1 drifted documentation link(s)" in drift_out

    # 3. CodeIndexerAgent symbol search & dependency graph tools
    code_idx = CodeIndexerAgent(config=mock_config, logger=mock_logger, pg_pool=MagicMock(), event_bus=mock_bus)
    ci_tools = [t.__name__ for t in code_idx.tools]
    assert "search_code_symbols" in ci_tools
    assert "get_file_dependency_graph" in ci_tools

    mock_sym_resp = MagicMock()
    mock_sym_resp.read.return_value = json.dumps({"success": True, "symbols": [{"label": "BootstrapService"}]}).encode("utf-8")
    mock_sym_resp.__enter__.return_value = mock_sym_resp

    with patch("src.agents.codeindexer.urllibUrlopen", return_value=mock_sym_resp):
        sym_out = asyncio.run(code_idx.execute_tool("search_code_symbols", {"symbol_query": "Bootstrap"}))
        assert "Found 1 AST symbol(s)" in sym_out
        assert "BootstrapService" in sym_out


