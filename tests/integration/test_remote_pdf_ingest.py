import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pymupdf
from click.testing import CliRunner

import paperbase.cli.commands.ingest as ingest_command
from paperbase.adapters.paper_fetch_adapter import FetchedPaper
from paperbase.cli.main import main
from paperbase.config.loader import load_config
from paperbase.core.identity import generate_storage_id, normalize_paper_id
from paperbase.core.manifest import load_manifest
from paperbase.core.paths import PaperPaths
from paperbase.utils.markdown import parse_frontmatter

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
)


def test_local_ingest_uses_remote_config_and_preserves_local_and_online_routes(monkeypatch, tmp_path):
    state = {"requests": [], "response": {}}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            state["requests"].append(
                {"path": self.path, "body": self.rfile.read(length)}
            )
            body = json.dumps(state["response"]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        base_dir = tmp_path / "library"
        config_dir = base_dir / "config"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "paperbase.yaml"
        config_path.write_text(
            f"""conversion:
  pdf:
    parser: remote
    visual:
      mode: "off"
    remote:
      providers:
        - name: primary
          provider: oxr
          base_url: http://127.0.0.1:{server.server_address[1]}/v1
          api_key: dummy-test-key
          timeout: 5
""",
            encoding="utf-8",
        )

        image_ref = f"data:image/png;base64,{base64.b64encode(PNG_BYTES).decode()}"
        remote_markdown = (
            "# OXR parsed paper\n\n"
            + ("Remote body content. " * 60)
            + f"\n\n![figure]({image_ref})"
        )
        state["response"] = {
            "code": 0,
            "data": {
                "result": {
                    "outputs": {
                        "markdown": remote_markdown,
                        "json": {
                            "pages": [
                                {
                                    "page_num": 1,
                                    "blocks": [{"type": "Picture", "content": f"![figure]({image_ref})"}],
                                }
                            ]
                        },
                    }
                }
            },
        }

        def metadata_for_pdf(path: Path):
            return {
                "title": f"Title from {path.stem}",
                "authors": ["Ada Lovelace"],
                "year": 2026,
                "doi": f"10.1234/{path.stem}",
                "abstract": "Source metadata remains authoritative.",
            }

        monkeypatch.setattr(ingest_command, "extract_pdf_metadata", metadata_for_pdf)
        remote_pdf = tmp_path / "remote-paper.pdf"
        remote_pdf.write_bytes(b"%PDF-1.4 synthetic remote source")

        remote_result = CliRunner().invoke(
            main,
            ["--base-dir", str(base_dir), "ingest", "--file", str(remote_pdf), "--no-graph"],
        )

        assert remote_result.exit_code == 0, remote_result.output
        assert len(state["requests"]) == 1, remote_result.output
        assert state["requests"][0]["path"] == "/v1/parse/sync"
        assert b"%PDF-1.4 synthetic remote source" in state["requests"][0]["body"]
        assert b"dummy-test-key" in state["requests"][0]["body"]

        remote_paper_id = normalize_paper_id("10.1234/remote-paper")
        remote_paths = PaperPaths(
            storage_id=generate_storage_id(remote_paper_id), base_dir=base_dir
        )
        remote_manifest = load_manifest(remote_paths.manifest_json)
        canonical = remote_paths.paper_md.read_text(encoding="utf-8")
        frontmatter, _ = parse_frontmatter(canonical)
        assert "Title from remote-paper" in canonical
        assert "doi:10.1234/remote-paper" in canonical
        assert frontmatter["provenance"]["converter"] == {
            "name": "oxr:primary",
            "version": "unknown",
        }
        assert remote_manifest.pipeline.converter == "oxr:primary"
        assert remote_manifest.pipeline.converter_version == "unknown"
        asset_path = next((remote_paths.paper_dir / "assets").glob("oxr-*.png"))
        assert f"./assets/{asset_path.name}" in canonical
        assert pymupdf.Pixmap(str(asset_path)).width == 1

        local_calls = []
        local_markdown = "# Local conversion\n\n" + ("Local body content. " * 60)

        def local_converter(source_pdf):
            local_calls.append(source_pdf)
            return local_markdown

        monkeypatch.setattr(
            "paperbase.core.pdf_conversion.convert_pdf_to_markdown", local_converter
        )
        local_pdf = tmp_path / "local-override.pdf"
        local_pdf.write_bytes(b"%PDF-1.4 synthetic local source")
        local_result = CliRunner().invoke(
            main,
            [
                "--base-dir",
                str(base_dir),
                "ingest",
                "--file",
                str(local_pdf),
                "--pdf-parser",
                "local",
                "--no-graph",
            ],
        )

        assert local_result.exit_code == 0, local_result.output
        assert len(local_calls) == 1
        assert len(state["requests"]) == 1
        assert load_config(config_path).conversion.pdf.parser == "remote"

        online_paper = FetchedPaper(
            query="10.1234/online-markdown",
            title="Online Markdown paper",
            authors=["Grace Hopper"],
            year=2025,
            markdown="# Already parsed online\n\n" + ("Fetched body. " * 60),
            doi="10.1234/online-markdown",
            has_fulltext=True,
        )

        class FakePaperFetchAdapter:
            def fetch(self, query):
                assert query == online_paper.doi
                return online_paper

        monkeypatch.setattr(ingest_command, "PaperFetchAdapter", FakePaperFetchAdapter)
        online_result = CliRunner().invoke(
            main,
            [
                "--base-dir",
                str(base_dir),
                "ingest",
                "10.1234/online-markdown",
                "--pdf-parser",
                "remote",
                "--no-graph",
            ],
        )

        assert online_result.exit_code == 0, online_result.output
        assert len(state["requests"]) == 1
        online_paper_id = normalize_paper_id(online_paper.doi)
        online_paths = PaperPaths(
            storage_id=generate_storage_id(online_paper_id), base_dir=base_dir
        )
        assert "Already parsed online" in online_paths.paper_md.read_text(encoding="utf-8")
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join()
