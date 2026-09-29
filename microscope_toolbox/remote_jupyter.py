"""Client for running code on a remote Jupyter Notebook 6 server, such as zeus2."""

import json
import posixpath
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import quote

import nbformat
import requests
import websocket
from nbformat import NotebookNode

HTTP_TIMEOUT_SECONDS = 30
# A cell that sends no output or status for this long is treated as hung.
KERNEL_SILENCE_TIMEOUT_SECONDS = 600
JUPYTER_MESSAGE_PROTOCOL_VERSION = "5.3"
OUTPUT_MESSAGE_TYPES = {"stream", "display_data", "execute_result", "error"}


class JupyterServerError(Exception):
    pass


@dataclass
class CellExecution:
    execution_count: Optional[int] = None
    outputs: List[NotebookNode] = field(default_factory=list)
    error: Optional[str] = None


class RemoteKernel:
    def __init__(self, channels: websocket.WebSocket) -> None:
        self.channels = channels
        self.client_session_id = uuid.uuid4().hex

    def wait_until_ready(self) -> None:
        request_msg_id = self._send_shell_request("kernel_info_request", {})
        while (
            self._next_message_replying_to(request_msg_id)["msg_type"]
            != "kernel_info_reply"
        ):
            pass

    def execute(self, code: str) -> CellExecution:
        request_msg_id = self._send_shell_request(
            "execute_request",
            {
                "code": code,
                "silent": False,
                "store_history": True,
                "user_expressions": {},
                "allow_stdin": False,
                "stop_on_error": True,
            },
        )
        cell_execution = CellExecution()
        clear_before_next_output = False
        execute_reply_received = False
        kernel_idle = False
        # The kernel's reply and its outputs arrive on separate channels in no fixed
        # order; the cell is done once both the reply and the idle status have arrived.
        while True:
            message = self._next_message_replying_to(request_msg_id)
            msg_type = message["msg_type"]
            content: Dict[str, Any] = message["content"]
            if msg_type == "execute_reply":
                execute_reply_received = True
                cell_execution.execution_count = content.get("execution_count")
                if content["status"] != "ok":
                    cell_execution.error = (
                        f"{content.get('ename', 'Error')}: {content.get('evalue', '')}"
                    )
            elif msg_type == "status":
                kernel_idle = content["execution_state"] == "idle"
            elif msg_type == "clear_output":
                if content.get("wait"):
                    clear_before_next_output = True
                else:
                    cell_execution.outputs.clear()
            elif msg_type in OUTPUT_MESSAGE_TYPES:
                if clear_before_next_output:
                    cell_execution.outputs.clear()
                    clear_before_next_output = False
                cell_execution.outputs.append(nbformat.v4.output_from_msg(message))
            if execute_reply_received and kernel_idle:
                return cell_execution

    def _send_shell_request(self, msg_type: str, content: Dict[str, Any]) -> str:
        msg_id = uuid.uuid4().hex
        request = {
            "header": {
                "msg_id": msg_id,
                "msg_type": msg_type,
                "session": self.client_session_id,
                "username": "microscope_toolbox",
                "date": datetime.now(timezone.utc).isoformat(),
                "version": JUPYTER_MESSAGE_PROTOCOL_VERSION,
            },
            "parent_header": {},
            "metadata": {},
            "content": content,
            "channel": "shell",
            "buffers": [],
        }
        self.channels.send(json.dumps(request))
        return msg_id

    def _next_message_replying_to(self, request_msg_id: str) -> Dict[str, Any]:
        while True:
            message: Dict[str, Any] = json.loads(self.channels.recv())
            if message["parent_header"].get("msg_id") == request_msg_id:
                return message


class JupyterServer:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = requests.Session()

    def log_in(self, password: str) -> None:
        self.http.get(
            f"{self.base_url}/login", timeout=HTTP_TIMEOUT_SECONDS
        ).raise_for_status()
        xsrf_token = self.http.cookies.get("_xsrf")
        response = self.http.post(
            f"{self.base_url}/login",
            data={"password": password, "_xsrf": xsrf_token},
            allow_redirects=False,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        # Notebook 6 redirects after a successful login and re-renders the login
        # form after a wrong password.
        if response.status_code != 302:
            raise JupyterServerError(
                f"Login to {self.base_url} failed; check the password"
            )
        if xsrf_token:
            # Notebook 6 rejects cookie-authenticated POST and DELETE requests
            # that don't echo the _xsrf cookie in this header.
            self.http.headers["X-XSRFToken"] = xsrf_token

    def fetch_notebook(self, notebook_path: str) -> NotebookNode:
        response = self.http.get(
            f"{self.base_url}/api/contents/{quote(notebook_path)}",
            params={"type": "notebook", "content": 1},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if response.status_code == 404:
            raise JupyterServerError(
                f"Notebook not found on {self.base_url}: {notebook_path}"
            )
        response.raise_for_status()
        contents_model: Dict[str, Any] = response.json()
        return nbformat.from_dict(contents_model["content"])

    @contextmanager
    def running_kernel(
        self, kernel_cwd: str, kernel_name: Optional[str]
    ) -> Iterator[RemoteKernel]:
        # A session on the notebook's own path would reuse the kernel of anyone who
        # has the notebook open in Jupyter. A unique path in the same folder gives
        # this run its own kernel, with the notebook's folder as working directory.
        session_path = posixpath.join(
            kernel_cwd, f".microscope_toolbox-run-{uuid.uuid4().hex}.ipynb"
        )
        response = self.http.post(
            f"{self.base_url}/api/sessions",
            json={
                "path": session_path,
                "type": "notebook",
                "name": "",
                "kernel": {"name": kernel_name} if kernel_name else {},
            },
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        session: Dict[str, Any] = response.json()
        websocket_base_url = "ws" + self.base_url[len("http") :]
        try:
            channels = websocket.create_connection(
                f"{websocket_base_url}/api/kernels/{session['kernel']['id']}/channels",
                cookie="; ".join(
                    f"{name}={value}" for name, value in self.http.cookies.items()
                ),
                # Notebook 6 refuses websocket connections from a foreign origin.
                origin=self.base_url,
                timeout=KERNEL_SILENCE_TIMEOUT_SECONDS,
            )
            try:
                kernel = RemoteKernel(channels)
                kernel.wait_until_ready()
                yield kernel
            finally:
                channels.close()
        except websocket.WebSocketException as error:
            raise JupyterServerError(
                f"Lost the kernel connection to {self.base_url}: {error!r}"
            ) from error
        finally:
            self.http.delete(
                f"{self.base_url}/api/sessions/{session['id']}",
                timeout=HTTP_TIMEOUT_SECONDS,
            )
