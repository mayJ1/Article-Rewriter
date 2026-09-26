#!/usr/bin/env python3
"""Portable async article rewrite client using only the Python standard library."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


DEFAULT_BASE_URL = "https://www.qqat.cn/api/v1/open"
TERMINAL_STATUSES = {"succeeded", "failed", "recoverable_failed", "cancelled"}
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ERROR_MESSAGES = {
    "INVALID_API_KEY": "API Key 无效、已过期或已被轮换，请重新配置。",
    "INSUFFICIENT_API_BALANCE": "API 余额不足，请充值后重试。",
    "INSUFFICIENT_API_CREDIT": "API 字符额度不足，请购买新的套餐。",
    "API_CREDIT_EXPIRED": "API 套餐已过期，请购买新套餐后重试。",
    "API_REQUEST_TOO_LARGE": "文章超过当前套餐的单次改写字数上限。",
    "API_ACCOUNT_DISABLED": "API 账号已停用，请联系服务方处理。",
    "API_ACCESS_BLOCKED": "API 访问被限制，请联系服务方处理。",
    "API_IP_FORBIDDEN": "当前公网 IP 不在 API 白名单中。",
    "API_SCOPE_FORBIDDEN": "当前 API Key 没有改写接口权限。",
    "API_TASK_NOT_FOUND": "没有找到对应的改写任务，请检查任务 ID 和 API Key。",
    "API_DAILY_LIMITED": "今日改写任务次数已用完，请稍后再试或升级套餐。",
    "API_CONCURRENCY_LIMITED": "已有改写任务正在处理，请等待其完成后再试。",
    "API_RATE_LIMITED": "请求过于频繁，请稍后重试。",
    "API_OPERATION_RATE_LIMITED": "状态查询过于频繁，请稍后重试。",
    "SOURCE_TEXT_REQUIRED": "没有可提交的文章正文。",
    "INVALID_REQUEST": "改写请求参数不符合接口要求。",
    "NETWORK_ERROR": "无法连接改写服务，请检查网络后重试。",
    "INVALID_RESPONSE": "改写服务返回了无法识别的数据。",
    "POLL_TIMEOUT": "等待改写结果超时，可使用任务 ID 继续查询。",
}


@dataclass
class RewriteError(Exception):
    code: str
    message: str
    http_status: int = 0
    request_id: str = ""
    retryable: bool = False
    task_id: str = ""

    def localized_message(self) -> str:
        return ERROR_MESSAGES.get(self.code, self.message or "改写请求失败。")

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.localized_message(),
                "http_status": self.http_status,
                "request_id": self.request_id,
                "retryable": self.retryable,
                "task_id": self.task_id,
            },
        }


def _config_dir() -> Path:
    override = os.environ.get("ARTICLE_REWRITER_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(root) / "article-rewriter"
    root = os.environ.get("XDG_CONFIG_HOME", "").strip()
    return (Path(root).expanduser() if root else Path.home() / ".config") / "article-rewriter"


def _config_path() -> Path:
    return _config_dir() / "config.yaml"


def ensure_config_file() -> Path:
    path = _config_path()
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# 文章改写 Skill 配置\n"
        "# 将购买到的 API Key 填写在下面的双引号内，然后保存文件。\n"
        'api_key: ""\n',
        encoding="utf-8",
    )
    if os.name != "nt":
        path.chmod(0o600)
    return path


def _parse_yaml_scalar(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except ValueError as exc:
            raise RewriteError("CONFIG_INVALID", "config.yaml 中的双引号格式不正确。") from exc
        return str(parsed)
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    return value.split(" #", 1)[0].strip()


def _parse_simple_yaml(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise RewriteError("CONFIG_INVALID", f"config.yaml 第 {line_number} 行缺少冒号。")
        key, value = line.split(":", 1)
        key = key.strip()
        if key != "api_key":
            continue
        data[key] = _parse_yaml_scalar(value)
    return data


def load_config() -> dict[str, Any]:
    path = ensure_config_file()
    try:
        data = _parse_simple_yaml(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise RewriteError("CONFIG_INVALID", f"无法读取本地配置：{exc}") from exc
    return data


def resolved_settings() -> tuple[str, str, str]:
    config = load_config()
    api_key = str(config.get("api_key") or "").strip()
    source = "config" if api_key else "missing"
    return api_key, DEFAULT_BASE_URL, source


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}…{key[-4:]}"


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise RewriteError("FILE_ENCODING_UNSUPPORTED", "无法识别文本文件编码，请转换为 UTF-8 后重试。")


def read_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as package:
            document = package.read("word/document.xml")
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise RewriteError("DOCX_INVALID", "无法读取 DOCX 文件，请确认文件没有损坏。") from exc
    try:
        root = ET.fromstring(document)
    except ET.ParseError as exc:
        raise RewriteError("DOCX_INVALID", "DOCX 正文结构无效。") from exc
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{{{WORD_NS}}}p"):
        pieces: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{{{WORD_NS}}}t" and node.text:
                pieces.append(node.text)
            elif node.tag == f"{{{WORD_NS}}}tab":
                pieces.append("\t")
            elif node.tag == f"{{{WORD_NS}}}br":
                pieces.append("\n")
        paragraphs.append("".join(pieces))
    return "\n".join(paragraphs).strip()


def read_source(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise RewriteError("FILE_NOT_FOUND", f"找不到输入文件：{path}")
    suffix = path.suffix.lower()
    if suffix == ".docx":
        text = read_docx(path)
    elif suffix in {".txt", ".md", ".markdown"}:
        text = read_text_file(path)
    else:
        raise RewriteError("FILE_TYPE_UNSUPPORTED", "仅支持 TXT、Markdown 和 DOCX 文件。")
    if not text.strip():
        raise RewriteError("SOURCE_TEXT_REQUIRED", "输入文件没有可改写的正文。")
    return text


def write_docx(path: Path, text: str) -> None:
    ET.register_namespace("w", WORD_NS)
    document = ET.Element(f"{{{WORD_NS}}}document")
    body = ET.SubElement(document, f"{{{WORD_NS}}}body")
    for line in text.splitlines() or [text]:
        paragraph = ET.SubElement(body, f"{{{WORD_NS}}}p")
        run = ET.SubElement(paragraph, f"{{{WORD_NS}}}r")
        text_node = ET.SubElement(run, f"{{{WORD_NS}}}t")
        if line[:1].isspace() or line[-1:].isspace():
            text_node.set(f"{{{XML_NS}}}space", "preserve")
        text_node.text = line
    section = ET.SubElement(body, f"{{{WORD_NS}}}sectPr")
    ET.SubElement(section, f"{{{WORD_NS}}}pgSz", {f"{{{WORD_NS}}}w": "11906", f"{{{WORD_NS}}}h": "16838"})
    ET.SubElement(
        section,
        f"{{{WORD_NS}}}pgMar",
        {
            f"{{{WORD_NS}}}top": "1440",
            f"{{{WORD_NS}}}right": "1440",
            f"{{{WORD_NS}}}bottom": "1440",
            f"{{{WORD_NS}}}left": "1440",
            f"{{{WORD_NS}}}header": "708",
            f"{{{WORD_NS}}}footer": "708",
            f"{{{WORD_NS}}}gutter": "0",
        },
    )
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("_rels/.rels", relationships)
        package.writestr("word/document.xml", ET.tostring(document, encoding="utf-8", xml_declaration=True))


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for number in range(2, 1000):
        candidate = path.with_name(f"{path.stem}-{number}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RewriteError("OUTPUT_EXISTS", "无法生成不重名的输出文件。")


def default_output_path(source: Path) -> Path:
    suffix = source.suffix.lower()
    if suffix not in {".docx", ".txt", ".md", ".markdown"}:
        suffix = ".txt"
    return unique_path(source.with_name(f"{source.stem}-改写{suffix}"))


def write_result(path: Path, text: str) -> Path:
    path = unique_path(path.expanduser().resolve())
    if path.suffix.lower() == ".docx":
        write_docx(path, text)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return path


class RewriteClient:
    def __init__(self, api_key: str, base_url: str, timeout: int = 30, max_retries: int = 3) -> None:
        if not api_key:
            raise RewriteError("API_KEY_REQUIRED", "尚未配置 API Key。")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = max(5, timeout)
        self.max_retries = max(1, max_retries)

    def create_task(self, source_text: str, intensity: int, idempotency_key: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/rewrite/tasks",
            body={"source_text": source_text, "intensity": intensity},
            extra_headers={"Idempotency-Key": idempotency_key},
        )

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/rewrite/tasks/{task_id}")

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        return self._request("POST", f"/rewrite/tasks/{task_id}/cancel")

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "ArticleRewriterSkill/1.0",
        }
        headers.update(extra_headers or {})
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            request = Request(self.base_url + path, data=encoded, headers=headers, method=method)
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = self._decode_response(response.read(), response.status, response.headers.get("X-Request-ID", ""))
                    return self._extract_data(payload, response.status, response.headers.get("X-Request-ID", ""))
            except HTTPError as exc:
                request_id = exc.headers.get("X-Request-ID", "") if exc.headers else ""
                raw = exc.read()
                try:
                    payload = json.loads(raw.decode("utf-8")) if raw else {}
                except (UnicodeDecodeError, ValueError):
                    payload = {}
                error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
                code = str(error.get("code") or f"HTTP_{exc.code}")
                message = str(error.get("message") or payload.get("message") or exc.reason or "请求失败。")
                retryable = exc.code >= 500 or code in {
                    "API_RATE_LIMITED",
                    "API_CONCURRENCY_LIMITED",
                    "API_OPERATION_RATE_LIMITED",
                    "INTERNAL_ERROR",
                }
                if retryable and attempt + 1 < self.max_retries:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    self._wait_before_retry(attempt, retry_after)
                    continue
                raise RewriteError(
                    code,
                    message,
                    exc.code,
                    str(payload.get("request_id") or request_id),
                    retryable,
                ) from exc
            except (URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt + 1 < self.max_retries:
                    self._wait_before_retry(attempt, None)
                    continue
                raise RewriteError("NETWORK_ERROR", str(exc), retryable=True) from exc
        raise RewriteError("NETWORK_ERROR", str(last_error or "请求失败。"), retryable=True)

    @staticmethod
    def _decode_response(raw: bytes, status: int, request_id: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise RewriteError("INVALID_RESPONSE", "响应不是有效 JSON。", status, request_id) from exc
        if not isinstance(payload, dict):
            raise RewriteError("INVALID_RESPONSE", "响应根节点不是对象。", status, request_id)
        return payload

    @staticmethod
    def _extract_data(payload: dict[str, Any], status: int, request_id: str) -> dict[str, Any]:
        if not payload.get("ok", True):
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            raise RewriteError(
                str(error.get("code") or f"HTTP_{status}"),
                str(error.get("message") or payload.get("message") or "请求失败。"),
                status,
                str(payload.get("request_id") or request_id),
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RewriteError("INVALID_RESPONSE", "响应缺少 data。", status, request_id)
        result = dict(data)
        result["request_id"] = str(payload.get("request_id") or request_id)
        return result

    @staticmethod
    def _wait_before_retry(attempt: int, retry_after: str | None) -> None:
        if retry_after:
            try:
                time.sleep(max(0.5, min(30.0, float(retry_after))))
                return
            except ValueError:
                pass
        time.sleep(min(8.0, (2**attempt) + random.random() * 0.5))


def validate_intensity(value: int) -> int:
    if value < 0 or value > 9:
        raise RewriteError("INVALID_INTENSITY", "改写强度必须是 0–9 的整数。")
    return value


def poll_task(client: RewriteClient, task_id: str, interval: float, timeout: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        task = client.get_task(task_id)
        status = str(task.get("status") or "")
        if status in TERMINAL_STATUSES:
            if status == "succeeded":
                return task
            usage = task.get("usage") if isinstance(task.get("usage"), dict) else {}
            code = str(usage.get("error_code") or status.upper())
            message = str(usage.get("error_message") or f"任务状态：{status}")
            raise RewriteError(code, message, request_id=str(task.get("request_id") or ""), task_id=task_id)
        if time.monotonic() >= deadline:
            raise RewriteError("POLL_TIMEOUT", "等待改写结果超时。", retryable=True, task_id=task_id)
        time.sleep(max(2.0, min(5.0, interval)))


def result_payload(task: dict[str, Any], output_path: Path | None, include_text: bool) -> dict[str, Any]:
    usage = task.get("usage") if isinstance(task.get("usage"), dict) else {}
    result_text = str(task.get("result_text") or "")
    payload: dict[str, Any] = {
        "ok": True,
        "task_id": str(task.get("task_id") or ""),
        "status": str(task.get("status") or "succeeded"),
        "intensity": task.get("intensity"),
        "input_chars": int(usage.get("input_chars") or task.get("source_chars") or 0),
        "output_chars": int(usage.get("output_chars") or task.get("result_chars") or 0),
        "actual_fee": str(usage.get("total_amount") or "0.000000"),
        "currency": str(usage.get("currency") or "CNY"),
        "request_id": str(task.get("request_id") or ""),
        "quality_issues": detect_quality_issues(result_text),
    }
    if output_path is not None:
        payload["output_path"] = str(output_path)
    if include_text:
        payload["result_text"] = result_text
    return payload


def detect_quality_issues(text: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    replacement_count = text.count("\ufffd")
    if replacement_count:
        issues.append(
            {
                "code": "UNICODE_REPLACEMENT_CHARACTER",
                "count": replacement_count,
                "message": "上游结果包含乱码替换字符，需要在交付前做最小范围修复。",
            }
        )
    if text.count("**") % 2:
        issues.append(
            {
                "code": "UNPAIRED_MARKDOWN_BOLD",
                "count": 1,
                "message": "上游结果包含不配对的 Markdown 粗体标记。",
            }
        )
    return issues


def command_config_status(_args: argparse.Namespace) -> dict[str, Any]:
    api_key, _base_url, source = resolved_settings()
    path = _config_path()
    return {
        "ok": True,
        "configured": bool(api_key),
        "key_source": source,
        "masked_key": mask_key(api_key),
        "config_path": str(path),
        "config_directory": str(path.parent),
        "action_required": "" if api_key else "请打开 config.yaml，将 API Key 填入 api_key 后保存。",
    }


def create_client() -> RewriteClient:
    api_key, base_url, _source = resolved_settings()
    if not api_key:
        raise RewriteError(
            "API_KEY_REQUIRED",
            f"尚未配置 API Key。请打开 {_config_path()}，将 Key 填入 api_key 后保存。",
        )
    return RewriteClient(api_key, base_url)


def command_rewrite(args: argparse.Namespace) -> dict[str, Any]:
    intensity = validate_intensity(args.intensity)
    source_path: Path | None = None
    if args.file:
        source_path = Path(args.file).expanduser().resolve()
        source_text = read_source(source_path)
    elif args.stdin:
        source_text = sys.stdin.read()
    else:
        source_text = args.text or ""
    if not source_text.strip():
        raise RewriteError("SOURCE_TEXT_REQUIRED", "没有可提交的文章正文。")
    client = create_client()
    created = client.create_task(source_text, intensity, str(uuid.uuid4()))
    task_id = str(created.get("task_id") or "")
    if not task_id:
        raise RewriteError("INVALID_RESPONSE", "创建任务响应缺少 task_id。")
    try:
        task = poll_task(client, task_id, args.poll_interval, args.poll_timeout)
    except KeyboardInterrupt as exc:
        raise RewriteError(
            "INTERRUPTED",
            "等待已中断，可使用任务 ID 继续查询。",
            retryable=True,
            task_id=task_id,
        ) from exc
    result_text = str(task.get("result_text") or "")
    if not result_text:
        raise RewriteError("INVALID_RESPONSE", "任务成功但没有返回改写结果。", task_id=task_id)
    output_path: Path | None = None
    if args.output:
        output_path = write_result(Path(args.output), result_text)
    elif source_path is not None:
        output_path = write_result(default_output_path(source_path), result_text)
    return result_payload(task, output_path, include_text=output_path is None or args.include_text)


def command_resume(args: argparse.Namespace) -> dict[str, Any]:
    client = create_client()
    task = poll_task(client, args.task_id, args.poll_interval, args.poll_timeout)
    result_text = str(task.get("result_text") or "")
    output_path = write_result(Path(args.output), result_text) if args.output else None
    return result_payload(task, output_path, include_text=output_path is None or args.include_text)


def command_cancel(args: argparse.Namespace) -> dict[str, Any]:
    task = create_client().cancel_task(args.task_id)
    return {
        "ok": True,
        "task_id": str(task.get("task_id") or args.task_id),
        "status": str(task.get("status") or "cancel_requested"),
        "request_id": str(task.get("request_id") or ""),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Portable article rewrite API client")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("config-status", help="create/check config.yaml without exposing the key")
    status.set_defaults(handler=command_config_status)

    rewrite = subparsers.add_parser("rewrite", help="submit and wait for one complete article")
    source_group = rewrite.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--file", help="TXT, Markdown, or DOCX source path")
    source_group.add_argument("--stdin", action="store_true", help="read source text from standard input")
    source_group.add_argument("--text", help="source text; prefer --stdin for long or sensitive text")
    rewrite.add_argument("--intensity", type=int, default=5)
    rewrite.add_argument("--output", help="optional TXT, Markdown, or DOCX output path")
    rewrite.add_argument("--include-text", action="store_true", help="include result text in JSON even when saved")
    rewrite.add_argument("--poll-interval", type=float, default=3.0)
    rewrite.add_argument("--poll-timeout", type=int, default=1800)
    rewrite.set_defaults(handler=command_rewrite)

    resume = subparsers.add_parser("resume", help="resume polling an existing task")
    resume.add_argument("--task-id", required=True)
    resume.add_argument("--output")
    resume.add_argument("--include-text", action="store_true")
    resume.add_argument("--poll-interval", type=float, default=3.0)
    resume.add_argument("--poll-timeout", type=int, default=1800)
    resume.set_defaults(handler=command_resume)

    cancel = subparsers.add_parser("cancel", help="cancel an unfinished task")
    cancel.add_argument("--task-id", required=True)
    cancel.set_defaults(handler=command_cancel)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = args.handler(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except RewriteError as exc:
        print(json.dumps(exc.as_dict(), ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
