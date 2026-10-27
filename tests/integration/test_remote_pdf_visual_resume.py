import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pymupdf
from click.testing import CliRunner

import paperbase.cli.commands.ingest as ingest_command
from paperbase.cli.main import main
from paperbase.config.models import PdfConversionConfig
from paperbase.core.identity import generate_storage_id, normalize_paper_id
from paperbase.core.manifest import load_manifest
from paperbase.core.paths import PaperPaths
from paperbase.core.pdf_conversion import (
    AgentActionRequiredOutcome,
    FailedConversionOutcome,
    ReadyConversionOutcome,
    progressPdfConversion,
)
from paperbase.schemas.manifest import PaperState

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
)
PAPER_DOI = "10.1234/remote-visual-resume"


def _write_pdf(path: Path, text: str = "Synthetic source page") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open()
    try:
        page = document.new_page(width=600, height=800)
        page.insert_text((72, 100), text)
        document.save(path)
    finally:
        document.close()


def _provider(
    base_url: str, name: str = "primary", api_key: str = "test-secret", **overrides
):
    return {
        "name": name,
        "provider": "oxr",
        "base_url": base_url,
        "api_key": api_key,
        "timeout": 5,
        **overrides,
    }


def _config(base_url: str, mode: str, providers=None, model: str = "host-model"):
    return PdfConversionConfig.model_validate(
        {
            "parser": "remote",
            "visual": {"mode": mode, "model": model, "chunk_pages": 2, "retry": 0},
            "remote": {
                "providers": providers or [_provider(base_url)],
            },
        }
    )


def _response() -> dict[str, object]:
    image_ref = f"data:image/png;base64,{base64.b64encode(PNG_BYTES).decode('ascii')}"
    markdown = "# Remote visual candidate\n\n" + ("Parsed body content. " * 50)
    markdown += f"\n\n![figure]({image_ref})"
    return {
        "code": 0,
        "data": {
            "result": {
                "outputs": {
                    "markdown": markdown,
                    "json": {"pages": [{"page_num": 1, "blocks": []}]},
                }
            }
        },
    }


class _OxrService:
    def __init__(self):
        self.requests: list[dict[str, object]] = []
        self.response = _response()

        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                service.requests.append(
                    {"path": self.path, "body": self.rfile.read(length)}
                )
                body = json.dumps(service.response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format, *_args):
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_worker_result(
    task_dir: Path,
    *,
    warnings: list[str] | None = None,
    crop_requests: list[dict[str, object]] | None = None,
    blocked: bool = False,
    candidate_images: str = "",
) -> None:
    task = _read_json(task_dir / "task.json")
    run = task["run"]
    chunk = task["chunk"]
    assert isinstance(run, dict)
    assert isinstance(chunk, dict)
    core_pages = chunk["core_pages"]
    assert isinstance(core_pages, list)
    result = {
        "schema_version": "visual-chunk-result-v1",
        "run_id": run["run_id"],
        "candidate_sha256": run["candidate_sha256"],
        "chunk_id": chunk["chunk_id"],
        "core_pages": core_pages,
        "status": "blocked" if blocked else "completed",
        "covered_pages": [] if blocked else core_pages,
        "warnings": warnings or [],
        "unresolved_issues": ["Needs another review."] if blocked else [],
        "failure_code": None,
        "crop_requests": crop_requests or [],
    }
    markdown = "" if blocked else "".join(
        f"<!-- paperbase:visual-page-start page={number} -->\n"
        f"Page {number} corrected content. "
        + ("Verified visual evidence. " * 24)
        + candidate_images
        + "\n"
        f"<!-- paperbase:visual-page-end page={number} -->\n"
        for number in core_pages
    )
    (task_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (task_dir / "result.md").write_text(markdown, encoding="utf-8")


def _write_all_worker_results(
    run_dir: Path,
    *,
    warning: bool = False,
    blocked: bool = False,
) -> None:
    task_dirs = sorted((run_dir / "tasks").iterdir())
    assert task_dirs
    candidate_images = "\n".join(
        line
        for line in (run_dir / "candidate.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("![")
    )
    for index, task_dir in enumerate(task_dirs):
        if blocked:
            _write_worker_result(task_dir, blocked=True)
        elif warning and index == 0:
            _write_worker_result(
                task_dir,
                warnings=["Formula requires explicit confirmation."],
                crop_requests=[
                    {"page": 1, "bbox": [0.1, 0.2, 0.8, 0.9], "kind": "formula"}
                ],
                candidate_images=candidate_images,
            )
        else:
            _write_worker_result(task_dir, candidate_images=candidate_images)


def _write_boundary_result(task_package: Path) -> None:
    task = _read_json(task_package / "task.json")
    run = task["run"]
    items = task["items"]
    assert isinstance(run, dict)
    assert isinstance(items, list)
    result = {
        "schema_version": "visual-boundary-review-result-v1",
        "run_id": run["run_id"],
        "candidate_sha256": run["candidate_sha256"],
        "decision": "pass",
        "checked_item_ids": [item["item_id"] for item in items],
        "affected_chunk_ids": [],
        "unresolved_issues": [],
        "warnings": [],
    }
    (task_package / "result.json").write_text(json.dumps(result), encoding="utf-8")


def test_remote_auto_resume_uses_rotated_key_and_keeps_oxr_result(tmp_path):
    service = _OxrService()
    try:
        source_pdf = tmp_path / "paper" / "source" / "source.pdf"
        _write_pdf(source_pdf)
        config = _config(service.base_url, "auto")

        handoff = progressPdfConversion(source_pdf, config)
        assert isinstance(handoff, AgentActionRequiredOutcome)
        assert handoff.task_package.parent.name == ".visual-auto-audit"
        candidate_markdown = (handoff.task_package / "candidate.md").read_text(encoding="utf-8")
        task = _read_json(handoff.task_package / "task.json")
        schema = task["worker_output"]["schema"]
        (handoff.task_package / "result.json").write_text(
            json.dumps(
                {
                    "kind": schema["kind"],
                    "version": schema["version"],
                    "source_pdf_sha256": schema["source_pdf_sha256"],
                    "candidate_sha256": schema["candidate_sha256"],
                    "decision": "pass",
                    "layout": "single_column",
                    "flagged_pages": [],
                    "reasons": ["Single-column reading order verified."],
                }
            ),
            encoding="utf-8",
        )
        rotated_config = _config(
            service.base_url,
            "auto",
            [_provider(service.base_url, api_key="rotated-secret")],
        )

        ready = progressPdfConversion(source_pdf, rotated_config)

        assert isinstance(ready, ReadyConversionOutcome)
        assert ready.markdown == candidate_markdown
        assert ready.converter == "oxr:primary"
        assert ready.converter_version == "unknown"
        assert ready.page_data == {"pages": [{"page_num": 1, "blocks": []}]}
        assert len(ready.assets) == 1
        assert len(service.requests) == 1
        cache_text = (source_pdf.parent.parent / ".remote-candidate.json").read_text(
            encoding="utf-8"
        )
        assert "test-secret" not in cache_text
        assert "rotated-secret" not in cache_text
    finally:
        service.close()


def test_remote_profile_identity_invalidates_cache_without_deleting_old_assets(tmp_path):
    service = _OxrService()
    try:
        source_pdf = tmp_path / "paper" / "source" / "source.pdf"
        _write_pdf(source_pdf)
        primary = _provider(service.base_url, "primary")
        config = _config(service.base_url, "always", [primary])

        first = progressPdfConversion(source_pdf, config)
        assert isinstance(first, AgentActionRequiredOutcome)
        first_assets = list((source_pdf.parent.parent / "assets").glob("oxr-*.png"))
        assert len(first_assets) == 1
        rotated_key = _config(
            service.base_url,
            "always",
            [_provider(service.base_url, "primary", api_key="rotated-secret")],
        )
        same_candidate = progressPdfConversion(source_pdf, rotated_key)
        assert isinstance(same_candidate, AgentActionRequiredOutcome)
        assert same_candidate.task_package == first.task_package
        assert len(service.requests) == 1

        changed_endpoint = _config(
            service.base_url,
            "always",
            [_provider(service.base_url + "/alternate", "primary")],
        )
        endpoint_candidate = progressPdfConversion(source_pdf, changed_endpoint)
        assert isinstance(endpoint_candidate, AgentActionRequiredOutcome)
        assert len(service.requests) == 2
        assert service.requests[-1]["path"] == "/v1/alternate/parse/sync"
        assert first_assets[0].is_file()

        changed_timeout = _config(
            service.base_url,
            "always",
            [_provider(service.base_url + "/alternate", "primary", timeout=10)],
        )
        timeout_candidate = progressPdfConversion(source_pdf, changed_timeout)
        assert isinstance(timeout_candidate, AgentActionRequiredOutcome)
        assert len(service.requests) == 3

        reordered = _config(
            service.base_url,
            "always",
            [
                _provider(service.base_url, "secondary"),
                _provider(service.base_url, "primary"),
            ],
        )
        ordered_candidate = progressPdfConversion(source_pdf, reordered)
        assert isinstance(ordered_candidate, AgentActionRequiredOutcome)
        assert len(service.requests) == 4
        stored_candidate = _read_json(source_pdf.parent.parent / ".remote-candidate.json")
        assert stored_candidate["converter"] == "oxr:secondary"
        assert first_assets[0].is_file()

        _write_pdf(source_pdf, text="Changed source bytes")
        changed_source = progressPdfConversion(source_pdf, reordered)
        assert isinstance(changed_source, AgentActionRequiredOutcome)
        assert len(service.requests) == 5
        assert first_assets[0].is_file()
    finally:
        service.close()


def test_remote_visual_quality_failure_does_not_call_next_profile(tmp_path):
    service = _OxrService()
    try:
        source_pdf = tmp_path / "paper" / "source" / "source.pdf"
        _write_pdf(source_pdf)
        config = _config(
            service.base_url,
            "always",
            [
                _provider(service.base_url, "primary"),
                _provider(service.base_url, "fallback"),
            ],
        )

        handoff = progressPdfConversion(source_pdf, config)
        assert isinstance(handoff, AgentActionRequiredOutcome)
        _write_all_worker_results(handoff.task_package, blocked=True)

        failed = progressPdfConversion(source_pdf, config)

        assert isinstance(failed, FailedConversionOutcome)
        assert failed.error.code == "visual_quality_blocked"
        assert len(service.requests) == 1
        cached = _read_json(source_pdf.parent.parent / ".remote-candidate.json")
        assert cached["converter"] == "oxr:primary"
    finally:
        service.close()


def test_remote_visual_warning_rereview_adopts_without_reupload_and_cleans_cache(
    monkeypatch, tmp_path
):
    service = _OxrService()
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
      mode: always
      model: host-model
      chunk_pages: 2
      retry: 0
    remote:
      providers:
        - name: primary
          provider: oxr
          base_url: {service.base_url}
          api_key: test-secret
          timeout: 5
""",
            encoding="utf-8",
        )
        input_pdf = tmp_path / "input.pdf"
        _write_pdf(input_pdf)
        monkeypatch.setattr(
            ingest_command,
            "extract_pdf_metadata",
            lambda _path: {
                "title": "Remote visual resume",
                "authors": ["Ada Lovelace"],
                "year": 2026,
                "doi": PAPER_DOI,
                "abstract": "Synthetic metadata for visual resume.",
            },
        )
        paper_paths = PaperPaths(
            storage_id=generate_storage_id(normalize_paper_id(PAPER_DOI)),
            base_dir=base_dir,
        )

        def invoke(*args: str):
            return CliRunner().invoke(
                main,
                ["--base-dir", str(base_dir), "ingest", "--file", str(input_pdf), *args],
            )

        first = invoke("--no-graph")
        assert first.exit_code == 0, first.output
        assert len(service.requests) == 1
        cache_path = paper_paths.paper_dir / ".remote-candidate.json"
        assert cache_path.is_file()
        run_dir = next(
            path
            for path in (paper_paths.paper_dir / ".visual-runs").iterdir()
            if (path / "run.json").is_file()
        )
        _write_all_worker_results(
            run_dir,
            warning=True,
        )

        boundary_handoff = invoke("--no-graph")
        assert boundary_handoff.exit_code == 0, boundary_handoff.output
        assert len(service.requests) == 1
        boundary_dir = run_dir / "boundary-review"
        assert boundary_dir.is_dir()
        _write_boundary_result(boundary_dir)

        warning_result = invoke("--no-graph")
        assert warning_result.exit_code == 0, warning_result.output
        assert "待确认警告" in warning_result.output
        assert cache_path.is_file()
        assert len(service.requests) == 1

        rereview = invoke("--re-review", "--no-graph")
        assert rereview.exit_code == 0, rereview.output
        assert "boundary-review" in rereview.output
        assert cache_path.is_file()
        assert len(service.requests) == 1
        _write_boundary_result(boundary_dir)

        adopted = invoke("--accept-visual-warnings", "--no-graph")

        assert adopted.exit_code == 0, adopted.output
        assert len(service.requests) == 1
        assert not cache_path.exists(), adopted.output
        manifest = load_manifest(paper_paths.manifest_json)
        assert manifest.state == PaperState.NORMALIZED
        assert manifest.pipeline.converter == "oxr:primary"
        assert manifest.pipeline.converter_version == "unknown"
        canonical = paper_paths.paper_md.read_text(encoding="utf-8")
        remote_asset = next((paper_paths.paper_dir / "assets").glob("oxr-*.png"))
        assert f"./assets/{remote_asset.name}" in canonical
        assert pymupdf.Pixmap(str(remote_asset)).width == 1
        assert any((paper_paths.paper_dir / "assets").glob("visual-page-*.png"))
        assert not list((paper_paths.paper_dir / ".visual-runs").glob("*/run.json"))
    finally:
        service.close()
