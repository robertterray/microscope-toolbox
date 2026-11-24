"""Tests for the remote Jupyter kernel client."""

import json
from typing import Any, Dict, List, Optional

from microscope_toolbox.remote_jupyter import RemoteKernel


class FakeKernelChannels:
    """Answers each request with scripted messages, parented to that request."""

    def __init__(self, scripted_messages: List[Dict[str, Any]]) -> None:
        self.scripted_messages = scripted_messages
        self.sent_requests: List[Dict[str, Any]] = []

    def send(self, request_json: str) -> None:
        self.sent_requests.append(json.loads(request_json))

    def recv(self) -> str:
        message = self.scripted_messages.pop(0)
        if "parent_header" not in message:
            message["parent_header"] = self.sent_requests[-1]["header"]
        return json.dumps(message)


def kernel_message(
    msg_type: str, content: Dict[str, Any], parent_msg_id: Optional[str] = None
) -> Dict[str, Any]:
    message: Dict[str, Any] = {
        "header": {"msg_type": msg_type},
        "msg_type": msg_type,
        "content": content,
        "metadata": {},
    }
    if parent_msg_id is not None:
        message["parent_header"] = {"msg_id": parent_msg_id}
    return message


def stdout(text: str) -> Dict[str, Any]:
    return kernel_message("stream", {"name": "stdout", "text": text})


def busy() -> Dict[str, Any]:
    return kernel_message("status", {"execution_state": "busy"})


def idle() -> Dict[str, Any]:
    return kernel_message("status", {"execution_state": "idle"})


def execute_reply(status: str = "ok", **content: Any) -> Dict[str, Any]:
    return kernel_message(
        "execute_reply", {"status": status, "execution_count": 7, **content}
    )


def test_execute_collects_outputs_until_reply_and_idle() -> None:
    channels = FakeKernelChannels(
        [
            busy(),
            stdout("384 wells\n"),
            kernel_message("stream", {"name": "stdout", "text": "other"}, "other-id"),
            idle(),
            execute_reply(),
        ]
    )
    cell_execution = RemoteKernel(channels).execute("print('384 wells')")  # type: ignore[arg-type]
    assert cell_execution.error is None
    assert cell_execution.execution_count == 7
    assert [output.text for output in cell_execution.outputs] == ["384 wells\n"]
    assert channels.sent_requests[0]["content"]["code"] == "print('384 wells')"


def test_execute_applies_clear_output_wait_at_next_output() -> None:
    channels = FakeKernelChannels(
        [
            stdout("50%\n"),
            kernel_message("clear_output", {"wait": True}),
            stdout("100%\n"),
            execute_reply(),
            idle(),
        ]
    )
    cell_execution = RemoteKernel(channels).execute("progress()")  # type: ignore[arg-type]
    assert [output.text for output in cell_execution.outputs] == ["100%\n"]


def test_execute_reports_cell_error() -> None:
    channels = FakeKernelChannels(
        [
            kernel_message(
                "error",
                {
                    "ename": "ZeroDivisionError",
                    "evalue": "division by zero",
                    "traceback": [],
                },
            ),
            execute_reply(
                status="error", ename="ZeroDivisionError", evalue="division by zero"
            ),
            idle(),
        ]
    )
    cell_execution = RemoteKernel(channels).execute("1 / 0")  # type: ignore[arg-type]
    assert cell_execution.error == "ZeroDivisionError: division by zero"
    assert cell_execution.outputs[0].output_type == "error"
