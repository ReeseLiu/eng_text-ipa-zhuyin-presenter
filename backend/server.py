"""Static file server and JSON API for the presenter MVP."""

from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote

try:
    from .pipeline import pipeline
except ImportError:  # pragma: no cover - supports direct script execution
    from pipeline import pipeline  # type: ignore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"


class PresenterHandler(BaseHTTPRequestHandler):
    server_version = "TextIpaZhuyinPresenter/0.1"

    def do_GET(self) -> None:
        api_path = self.path.split("?", 1)[0]
        if api_path == "/api/display_table":
            self._send_json({"display_table": pipeline.get_display_table()})
            return
        if self.path.startswith("/api/"):
            self._send_json({"error": {"code": "not_found", "message": "Unknown API endpoint"}}, status=404)
            return
        self._serve_static()

    def do_POST(self) -> None:
        routes = {
            "/api/process_text": self._api_process_text,
            "/api/reprocess_sentence": self._api_reprocess_sentence,
            "/api/reprocess_word": self._api_reprocess_word,
            "/api/display_for_ipa": self._api_display_for_ipa,
            "/api/export_json": self._api_export_json,
        }
        handler = routes.get(self.path.split("?", 1)[0])
        if handler is None:
            self._send_json({"error": {"code": "not_found", "message": "Unknown API endpoint"}}, status=404)
            return
        try:
            handler(self._read_json())
        except ValueError as exc:
            self._send_json({"error": {"code": "bad_request", "message": str(exc)}}, status=400)
        except Exception as exc:  # pragma: no cover - defensive API boundary
            self._send_json({"error": {"code": "internal_error", "message": str(exc)}}, status=500)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _api_process_text(self, payload: dict[str, Any]) -> None:
        text = str(payload.get("text", ""))
        source = payload.get("source")
        if not text.strip():
            raise ValueError("text is required")
        self._send_json(pipeline.process_text(text, str(source) if source else None))

    def _api_reprocess_sentence(self, payload: dict[str, Any]) -> None:
        text = str(payload.get("text", ""))
        if not text.strip():
            raise ValueError("text is required")
        sentence_id = payload.get("sentence_id", "1")
        self._send_json({"sentence": pipeline.process_sentence(text, sentence_id)})

    def _api_reprocess_word(self, payload: dict[str, Any]) -> None:
        word = str(payload.get("word", ""))
        if not word.strip():
            raise ValueError("word is required")
        context = payload.get("context") if isinstance(payload.get("context"), dict) else None
        self._send_json({"word": pipeline.process_word(word, context=context)})

    def _api_display_for_ipa(self, payload: dict[str, Any]) -> None:
        ipa = payload.get("ipa", [])
        word = payload.get("word")
        stress = payload.get("stress_levels", [])
        self._send_json(pipeline.display_for_ipa(ipa, word_text=str(word) if word else None, stress_levels=stress if isinstance(stress, list) else None))

    def _api_export_json(self, payload: dict[str, Any]) -> None:
        body = payload.get("payload", payload)
        if not isinstance(body, dict):
            raise ValueError("payload must be an object")
        self._send_json(pipeline.export_json(body))

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            parsed = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("JSON body must be an object")
        return parsed

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self) -> None:
        raw_path = unquote(self.path.split("?", 1)[0])
        rel_path = raw_path.lstrip("/") or "index.html"
        target = (APP_DIR / rel_path).resolve()
        if APP_DIR.resolve() not in target.parents and target != APP_DIR.resolve():
            self.send_error(403)
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    httpd = ThreadingHTTPServer((host, port), PresenterHandler)
    print(f"Serving Text IPA Zhuyin Presenter at http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    run()
