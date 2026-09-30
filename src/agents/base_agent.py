#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Autonomous Agent Base Class and Tool Execution Engine for the AI Squad.
Provides unified LLM prompt compilation, tool calling, memory history retrieval,
and reactive event bus message processing for all persona roles.

DATA FLOW:
1. Loads role instructions from Role-Prompts markdown specifications.
2. Listens for incoming chat messages via SquadEventBus (NATS or Local).
3. Compiles active prompt with session context, RAG augmentations, and conversation history.
4. Invokes LLM via Gemini SDK and executes autonomous agent tool calls.
5. Publishes synthesized thoughts and responses back to the event bus and memory store.

KEY PARAMETERS:
- role_name: Persona identifier matching Role-Prompts folder.
- prompt_file: Path to Markdown role prompt specification.
- event_bus: SquadEventBus instance for pub/sub message transit.
- pg_pool: Shared database connection pool for memory persistence.
"""

import os
import sys
import json
import asyncio
from typing import Dict, Any, List, Optional
from src.interfaces import SquadEventBus
from google import genai
from google.genai import types

# -----------------------------------------------------------------------------

def query_rag_engine(query: str) -> str:
    """
    Queries the central RAG engine to retrieve architectural guidelines,
    codebase design patterns, or strategic decision history.
    
    Args:
        query: The semantic search query (e.g. 'REST API design standard').
    """
    return ""

def read_workspace_file(path: str, fold_bodies: bool = True) -> str:
    """
    Reads the contents of a file in the workspace directory.
    
    Args:
        path: Relative path to the file from workspace root (e.g. 'src/core/controller.py').
        fold_bodies: Whether to collapse large function and class bodies to save tokens (default True).
    """
    return ""

def write_workspace_file(path: str, content: str) -> str:
    """
    Writes or edits the contents of a file in the workspace directory.
    
    Args:
        path: Relative path to the file from workspace root.
        content: Complete contents to write to the file.
    """
    return ""

def execute_shell_command(command: str) -> str:
    """
    Executes a shell command in the workspace directory (e.g. compiling or linting).
    
    Args:
        command: The command line string to run.
    """
    return ""
def _fold_python_code(content: str) -> str:
    """Folds python function/class bodies to show only signatures and docstrings."""
    import ast
    try:
        tree = ast.parse(content)
        lines = content.splitlines()
        folded_intervals = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno
                end = node.end_lineno
                if end and end - start > 5:
                    sig_line = lines[start - 1]
                    indent = len(sig_line) - len(sig_line.lstrip())
                    folded_intervals.append((start + 1, end, indent + 4))
                    
        folded_intervals.sort(key=lambda x: x[0], reverse=True)
        for f_start, f_end, f_indent in folded_intervals:
            indent_str = " " * f_indent
            lines[f_start - 1 : f_end] = [f"{indent_str}# ... folded ..."]
            
        return "\n".join(lines)
    except Exception:
        return content


def _fold_generic_code(content: str) -> str:
    """Folds braced language function bodies (JS/TS/Go/Rust/C++)."""
    lines = content.splitlines()
    folded_lines = []
    brace_count = 0
    in_fold = False
    fold_start_indent = 0
    
    for line in lines:
        stripped = line.strip()
        if in_fold:
            brace_count += stripped.count('{')
            brace_count -= stripped.count('}')
            if brace_count <= 0:
                in_fold = False
                indent = " " * fold_start_indent
                folded_lines.append(f"{indent}}} // ... folded ...")
            continue
            
        if '{' in line and any(keyword in line for keyword in ("function", "class", "impl", "fn", "struct", "interface", "public", "private")):
            brace_count = line.count('{') - line.count('}')
            if brace_count > 0:
                in_fold = True
                fold_start_indent = len(line) - len(line.lstrip())
                folded_lines.append(line.split('{')[0] + "{")
                folded_lines.append(" " * (fold_start_indent + 4) + "// ... folded ...")
                continue
                
        folded_lines.append(line)
        
    return "\n".join(folded_lines)


# -----------------------------------------------------------------------------

class BaseAgent:
    """
    Base squad agent client handling SquadEventBus routing, PostgreSQL log indexing,
    and role-specific Google GenAI SDK model generation.
    """
    def __init__(self, *, role_name: str, prompt_file: str, config: Any, logger: Any, pg_pool: Any, event_bus: SquadEventBus):
        self.role_name = role_name
        self.prompt_file = prompt_file
        self.config = config
        self.logger = logger
        self.pool = pg_pool
        self.event_bus = event_bus
        self.loop = None
        self.running = False
        
        # Load LLM configuration from environment variables or configuration profile
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.model_name = os.environ.get("GEMINI_MODEL")
        
        if self.config and hasattr(self.config, "data") and isinstance(self.config.data, dict):
            cap = self.config.data.get("capabilities", {}).get("base_scripts", {})
            if not self.api_key:
                raw_key = cap.get("gemini_api_key")
                if raw_key:
                    try:
                        self.api_key = self.config.decrypt_secret(raw_key)
                    except Exception as e:
                        self.logger.error(f"Agent {self.role_name}: Failed to decrypt gemini_api_key from config: {e}")
            if not self.model_name:
                self.model_name = cap.get("gemini_model")
                
        if not self.model_name:
            self.model_name = "gemini-3.5-flash"
        
        # Load system instruction
        self.system_instruction = self._load_system_prompt()
        
        # Instantiate Google GenAI Client strictly if explicit API Key is present
        self.client = None
        if hasattr(self.config, "data") and isinstance(self.config.data, dict) and self.config.data.get("genai_client"):
            self.client = self.config.data["genai_client"]
            self.logger.info(f"Agent {self.role_name}: Re-using shared Gemini Client from config.")
        elif self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
                self.logger.info(f"Agent {self.role_name}: Initialised Gemini Client using GEMINI_API_KEY.")
                if hasattr(self.config, "data") and isinstance(self.config.data, dict):
                    self.config.data["genai_client"] = self.client
            except Exception as e:
                self.logger.error(f"Agent {self.role_name}: Failed to initialise Gemini Client: {e}")
        else:
            self.logger.warning(f"Agent {self.role_name}: GEMINI_API_KEY is missing from environment. Mock responses will be used.")
        
        # Subclass overrides or appends to tools
        self.tools = [query_rag_engine, read_workspace_file, write_workspace_file, execute_shell_command]

    def _load_system_prompt(self) -> str:
        """Reads the agent role's system instruction from KMS files."""
        from pathlib import Path
        obsidian_dir = Path(__file__).resolve().parent.parent.parent.parent
        prompt_path = obsidian_dir / "07-Core-KMS" / "Role-Prompts" / self.prompt_file
        if prompt_path.exists():
            try:
                return prompt_path.read_text(encoding="utf-8")
            except Exception as e:
                self.logger.error(f"Agent {self.role_name}: Failed to read prompt file {self.prompt_file}: {e}")
        return f"You are the {self.role_name} AI squad agent."

    async def start(self):
        """Registers the agent message consumer loop."""
        self.running = True
        self.loop = asyncio.get_running_loop()
        
        async def msg_cb(payload):
            try:
                await self.on_chat_message(payload)
            except Exception as e:
                self.logger.error(f"Agent {self.role_name} failed to handle incoming message: {e}")
        
        await self.event_bus.subscribe("antigravity.squad.chat", callback=msg_cb, role=self.role_name)
        self.logger.info(f"Agent {self.role_name} listening on event_bus channels for role '{self.role_name}'")

    async def stop(self):
        """Clean shut down."""
        self.running = False

    async def on_chat_message(self, payload: Dict[str, Any]):
        """Callback invoked when a new message arrives in the room."""
        sender = payload.get("sender")
        session_id = payload.get("session_id")
        content = payload.get("content")
        
        if not session_id or not content or sender == self.role_name:
            return

        # Safeguard: Orchestrator only coordinates on user input to prevent loops
        if self.role_name == "orchestrator" and sender != "user":
            return

        # Determine if this message is addressing us or if we are the Orchestrator
        is_orchestrator = (self.role_name == "orchestrator")
        is_addressed = f"@{self.role_name}" in content.lower()
        
        if not is_orchestrator and not is_addressed:
            return

        self.logger.info(f"Agent {self.role_name} processing message from {sender} in session {session_id}")
        await self.think_and_respond(session_id)

    async def think_and_respond(self, session_id: str):
        """Queries Gemini using conversation logs database history and broadcasts response."""
        if not self.client:
            self.logger.info(f"Agent {self.role_name} using mock offline response (Gemini API key is missing).")
            await self._run_mock_think_and_respond(session_id)
            return

        # 1. Fetch chat history from postgres
        history = await self._fetch_history(session_id)
        
        # 2. Convert to Gemini Content types
        contents = []
        for log in history:
            role = "user" if log["sender"] == "user" else "model"
            content_text = log["content"]
            if role == "model":
                content_text = f"[{log['sender']}]: {log['content']}"
            contents.append(
                types.Content(role=role, parts=[types.Part.from_text(text=content_text)])
            )

        # 3. Call generation
        try:
            self.logger.info(f"Agent {self.role_name} invoking model generate_content...")
            
            # Map tools dynamically if subclass has defined self.tools
            config_params = {
                "system_instruction": self.system_instruction,
            }
            if self.tools:
                config_params["tools"] = self.tools

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(**config_params)
            )
            
            answer_text = response.text or ""
            tool_calls_data = []
            
            # Turn budget loop for parallel tool calls and multi-turn execution
            loop_turn = 0
            MAX_TOOL_TURNS = 5
            current_response = response
            
            while loop_turn < MAX_TOOL_TURNS:
                function_calls = []
                if current_response.candidates and current_response.candidates[0].content.parts:
                    for part in current_response.candidates[0].content.parts:
                        if part.function_call:
                            function_calls.append(part)
                
                if not function_calls:
                    break
                
                loop_turn += 1
                self.logger.info(f"Agent {self.role_name} processing {len(function_calls)} parallel tool calls (turn {loop_turn}/{MAX_TOOL_TURNS})")
                user_parts = []
                for part in function_calls:
                    call = part.function_call
                    self.logger.info(f"Agent {self.role_name} executing tool call: {call.name}")
                    tool_result = await self.execute_tool(call.name, dict(call.args))
                    
                    tool_calls_data.append({
                        "name": call.name,
                        "args": dict(call.args),
                        "result": tool_result
                    })
                    
                    user_parts.append(types.Part(
                        function_response=types.FunctionResponse(
                            name=call.name,
                            response={"result": tool_result}
                        ),
                        thought_signature=part.thought_signature
                    ))
                
                # Append original model response (including thoughts, text, and signatures) and user responses
                contents.append(current_response.candidates[0].content)
                contents.append(types.Content(role="user", parts=user_parts))
                
                # Re-query the model with the execution results using the complete configuration parameters
                current_response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(**config_params)
                )
                answer_text = current_response.text or ""
            else:
                self.logger.warning(f"Agent {self.role_name} exceeded MAX_TOOL_TURNS limit of {MAX_TOOL_TURNS}")
                answer_text = f"⚠️ [System Alert]: Agent exceeded maximum tool execution turns ({MAX_TOOL_TURNS}). Execution halted."

            if answer_text:
                # 4. Save response to Postgres
                await self._save_log(session_id, answer_text, tool_calls_data)
                
                payload_data = {
                    "sender": self.role_name,
                    "session_id": session_id,
                    "content": answer_text,
                    "tool_calls": tool_calls_data
                }
                
                # 5. Broadcast to SquadEventBus
                await self.event_bus.publish("antigravity.squad.chat", payload_data)
        except Exception as e:
            self.logger.error(f"Agent {self.role_name} failed during LLM generation loop: {e}")
            err_msg = f"⚠️ [System Alert]: Agent '{self.role_name}' failed during generation loop: {e}"
            payload_data = {
                "sender": self.role_name,
                "session_id": session_id,
                "content": err_msg,
                "tool_calls": []
            }
            try:
                await self.event_bus.publish("antigravity.squad.chat", payload_data)
            except Exception as publish_err:
                self.logger.error(f"Failed to publish error alert for {self.role_name}: {publish_err}")

    async def execute_tool(self, name: str, args: Dict[str, Any]) -> str:
        """Dynamic tool execution handler."""
        if name == "query_rag_engine":
            query_arg = args.get("query", "")
            from lib.memory import RAGMemoryStore
            rag_store = RAGMemoryStore(
                config=self.config,
                logger=self.logger,
                tenant="08-Base-Scripts",
                client=self.config.data.get("rag_client")
            )
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                None,
                lambda: rag_store.retrieve(query_arg, limit=5)
            )
            if not results:
                return "No architectural context found in RAG engine."
            formatted = []
            for doc in results:
                formatted.append(f"Context turn:\n{doc.get('content', '')}")
            return "\n\n---\n\n".join(formatted)

        elif name == "read_workspace_file":
            path_arg = args.get("path", "")
            fold_bodies_arg = args.get("fold_bodies", True)
            from pathlib import Path
            workspace_root = Path(__file__).resolve().parent.parent.parent.parent.parent
            file_path = (workspace_root / path_arg).resolve()
            
            # Path Traversal Guard
            try:
                file_path.relative_to(workspace_root)
            except ValueError:
                return f"Error: Access denied. Path {path_arg} is outside the workspace root."
                
            try:
                content = file_path.read_text(encoding="utf-8")
                if fold_bodies_arg:
                    ext = file_path.suffix.lower().lstrip('.')
                    if ext == "py":
                        content = _fold_python_code(content)
                    elif ext in ("js", "ts", "go", "rs", "cpp", "h", "hpp", "cc"):
                        content = _fold_generic_code(content)
                return content
            except Exception as e:
                return f"Error reading file {path_arg}: {e}"

        elif name == "write_workspace_file":
            path_arg = args.get("path", "")
            content_arg = args.get("content", "")
            from pathlib import Path
            workspace_root = Path(__file__).resolve().parent.parent.parent.parent.parent
            file_path = (workspace_root / path_arg).resolve()
            
            # Path Traversal Guard
            try:
                file_path.relative_to(workspace_root)
            except ValueError:
                return f"Error: Access denied. Path {path_arg} is outside the workspace root."
                
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content_arg, encoding="utf-8")
                return f"Success writing to file {path_arg}"
            except Exception as e:
                return f"Error writing file {path_arg}: {e}"

        elif name == "execute_shell_command":
            cmd_arg = args.get("command", "")
            
            # Sandbox / Shell Injection Blocklist Guard
            blocked_keywords = [
                "rm ", "rmdir", "chmod", "chown", "sudo", "su ", "curl", "wget",
                "scp", "ssh", "sftp", "ftp", "/etc/", "/var/", "mv ", "dd ",
                "mkfs", "tftp"
            ]
            
            # Normalise command strings to prevent evasion techniques (e.g. quotes or escaped chars)
            cleaned_cmd = cmd_arg.lower().replace("'", "").replace('"', "").replace("\\", "")
            
            # Split commands by common operators to check sub-commands separately
            import re
            cmd_parts = re.split(r'[;&|`\n\r]', cleaned_cmd)
            for part in cmd_parts:
                part_strip = part.strip()
                for kw in blocked_keywords:
                    kw_clean = kw.strip()
                    if part_strip == kw_clean or part_strip.startswith(kw_clean + " ") or part_strip.startswith(kw_clean + "\t"):
                        return f"Error: Command execution blocked for safety. Keyword '{kw_clean}' is prohibited."
                    if kw in part:
                        return f"Error: Command execution blocked for safety. Keyword '{kw}' is prohibited."
            
            import subprocess
            from pathlib import Path
            workspace_root = Path(__file__).resolve().parent.parent.parent.parent.parent
            try:
                proc = subprocess.run(
                    cmd_arg,
                    shell=True,
                    capture_output=True,
                    text=True,
                    cwd=str(workspace_root),
                    timeout=30
                )
                return f"Stdout:\n{proc.stdout}\nStderr:\n{proc.stderr}\nExit Code: {proc.returncode}"
            except subprocess.TimeoutExpired:
                return "Error: Command execution timed out after 30 seconds."
            except Exception as e:
                return f"Error executing command: {e}"

        return f"Tool {name} not implemented."

    async def _run_mock_think_and_respond(self, session_id: str):
        """Generates a simulated role-specific mock response for testing offline."""
        history = await self._fetch_history(session_id)
        last_msg = ""
        if history:
            last_msg = history[-1]["content"]

        answer_text = ""
        tool_calls_data = []

        if self.role_name == "orchestrator":
            if "status" in last_msg.lower() or "check" in last_msg.lower():
                answer_text = "🤖 **[Orchestrator]** Hello! I have initiated a status check across all base scripts services. The system is healthy and responsive. Let me loop in the developer and QA agents to verify details. @developer @qa"
            else:
                answer_text = f"🤖 **[Orchestrator]** Understood. I am coordinating the squad to address your request: '{last_msg}'. @developer, please review the workspace files. @qa, prepare the verification tests."
        elif self.role_name == "developer":
            answer_text = "🛠️ **[Developer]** Developer here. I have scanned the repository workspace. All python and Go codebase files conform to standard architecture layout guidelines. I stand ready to apply edits as requested."
            tool_calls_data.append({
                "name": "read_workspace_file",
                "args": {"path": "src/agents/developer.py"},
                "result": "Success: Read 107 lines of code."
            })
        elif self.role_name == "qa":
            answer_text = "🧪 **[QA]** Greetings, this is QA. I have executed the syntax verification suite. Codebase integrity is verified: all tests pass successfully, and no config drift was detected."
        elif self.role_name == "architect":
            answer_text = "📐 **[Architect]** Hello! Architect here. The current system architecture conforms to our standard multi-agent decoupled layout. The dual-layer memory persistence and event routing schemes are fully aligned with the design manual."

        if answer_text:
            await asyncio.sleep(1.0)
            await self._save_log(session_id, answer_text, tool_calls_data)
            
            payload_data = {
                "sender": self.role_name,
                "session_id": session_id,
                "content": answer_text,
                "tool_calls": tool_calls_data
            }
            
            await self.event_bus.publish("antigravity.squad.chat", payload_data)

    async def _fetch_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Queries postgres squad_chat_logs for history turns."""
        if not self.pool:
            return []
        
        loop = asyncio.get_event_loop()
        def db_query():
            conn = self.pool.getconn()
            try:
                with conn.cursor() as cursor:
                    cursor.execute('SET search_path TO "08-Base-Scripts", public')
                    # Apply chronological sliding window: fetch last 15 messages and reverse order
                    cursor.execute(
                        "SELECT sender, content, tool_calls FROM squad_chat_logs WHERE session_id = %s ORDER BY created_at DESC LIMIT 15",
                        (session_id,)
                    )
                    rows = cursor.fetchall()
                    return [
                        {"sender": r[0], "content": r[1], "tool_calls": r[2]}
                        for r in reversed(rows)
                    ]
            except Exception as e:
                self.logger.error(f"Failed to query squad_chat_logs: {e}")
                return []
            finally:
                self.pool.putconn(conn)
                
        return await loop.run_in_executor(None, db_query)

    async def _save_log(self, session_id: str, content: str, tool_calls: List[Dict[str, Any]] = None):
        """Saves a conversation turn to squad_chat_logs."""
        if not self.pool:
            return
            
        loop = asyncio.get_event_loop()
        def db_insert():
            conn = self.pool.getconn()
            try:
                with conn.cursor() as cursor:
                    cursor.execute('SET search_path TO "08-Base-Scripts", public')
                    cursor.execute(
                        "INSERT INTO squad_chat_logs (session_id, sender, content, tool_calls) VALUES (%s, %s, %s, %s)",
                        (session_id, self.role_name, content, json.dumps(tool_calls or []))
                    )
                conn.commit()
            except Exception as e:
                self.logger.error(f"Failed to insert squad_chat_logs: {e}")
            finally:
                self.pool.putconn(conn)
                
        await loop.run_in_executor(None, db_insert)
