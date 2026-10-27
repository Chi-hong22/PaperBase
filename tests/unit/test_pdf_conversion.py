"""PDF 转换统一结果与本地回退路径测试。"""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pymupdf
import pytest

from paperbase.config.models import PdfConversionConfig
from paperbase.core import pdf_conversion
from paperbase.core.pdf_conversion import (
    AgentActionRequiredOutcome,
    FailedConversionOutcome,
    NeedsConfirmationOutcome,
    PdfConversionError,
    ReadyConversionOutcome,
    progressPdfConversion,
)


@pytest.fixture
def oxr_service():
    """Capture OXR POST requests and reply with a controllable JSON body."""
    state: dict = {"requests": [], "image_requests": [], "response": {}, "status": 200}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            state["requests"].append(
                {
                    "path": self.path,
                    "content_type": self.headers.get("Content-Type", ""),
                    "body": self.rfile.read(length),
                }
            )
            payload = json.dumps(state["response"]).encode("utf-8")
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            state["image_requests"].append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(state["image_bytes"])))
            self.end_headers()
            self.wfile.write(state["image_bytes"])

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state["base_url"] = f"http://127.0.0.1:{server.server_address[1]}/v1"
    state["image_url"] = f"http://127.0.0.1:{server.server_address[1]}/figure.png"
    state["image_bytes"] = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
    )
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class TestPdfConversionRemote:
    """远程解析入口的最小合同测试。"""

    def test_remote_mode_returns_oxr_markdown(self, tmp_path, oxr_service):
        """显式 remote+visual.off 时通过真实适配器请求 OXR 并返回其正文。"""
        source_pdf = tmp_path / "paper.pdf"
        source_pdf.write_bytes(b"%PDF-1.4 remote source")
        remote_markdown = "# Remote candidate\n\nParsed body."
        oxr_service["response"] = {
            "code": 0,
            "message": "任务成功",
            "warnings": [],
            "data": {
                "task_id": "00000000-0000-0000-0000-000000000000",
                "error": None,
                "result": {
                    "file_name": "paper.pdf",
                    "outputs": {
                        "markdown": remote_markdown,
                        "json": {"pages": []},
                    },
                },
                "metadata": {
                    "page_num": 1,
                    "file_type": ".pdf",
                    "processing_time_ms": 5,
                },
            },
        }
        conversion_config = PdfConversionConfig.model_validate(
            {
                "parser": "remote",
                "visual": {"mode": "off"},
                "remote": {
                    "providers": [
                        {
                            "name": "test-oxr",
                            "provider": "oxr",
                            "base_url": oxr_service["base_url"],
                            "api_key": "dummy-test-key",
                            "timeout": 5,
                        }
                    ]
                },
            }
        )

        outcome = progressPdfConversion(source_pdf, conversion_config)

        assert isinstance(outcome, ReadyConversionOutcome)
        assert outcome.markdown == remote_markdown
        assert outcome.assets == ()
        assert outcome.converter == "oxr:test-oxr"
        assert outcome.converter_version == "unknown"
        assert outcome.page_data == {"pages": []}
        assert len(oxr_service["requests"]) == 1
        request = oxr_service["requests"][0]
        assert request["path"] == "/v1/parse/sync"
        assert request["content_type"].startswith("multipart/form-data")
        body = request["body"]
        assert b'name="file"' in body
        assert b'filename="document.pdf"' in body
        assert body.count(b'name="output_formats"') == 2
        assert b"\r\nmarkdown\r\n" in body
        assert b"\r\njson\r\n" in body
        assert b'name="api_key"' in body
        assert b"dummy-test-key" in body

    @pytest.mark.parametrize("image_kind", ["base64", "url", "url_title", "html_url"])
    def test_remote_mode_localizes_oxr_images(self, tmp_path, oxr_service, image_kind):
        """OXR 图片正文引用必须在 Ready 结果中指向可读的本地资产。"""
        source_dir = tmp_path / "paper" / "source"
        source_dir.mkdir(parents=True)
        source_pdf = source_dir / "source.pdf"
        source_pdf.write_bytes(b"%PDF-1.4 remote source")
        image_ref = (
            f"data:image/png;base64,{base64.b64encode(oxr_service['image_bytes']).decode()}"
            if image_kind == "base64"
            else oxr_service["image_url"]
        )
        if image_kind == "html_url":
            remote_markdown = f'<table><img src="{image_ref}"></table>'
        elif image_kind == "url_title":
            remote_markdown = f'# Remote candidate\n\n![figure]({image_ref} "figure title")'
        else:
            remote_markdown = f"# Remote candidate\n\n![figure]({image_ref})"
        oxr_service["response"] = {
            "code": 0,
            "data": {
                "result": {
                    "outputs": {
                        "markdown": remote_markdown,
                        "json": {
                            "pages": [
                                {
                                    "page_num": 0,
                                    "page_size": [100, 200],
                                    "blocks": [
                                        {"type": "Picture", "content": f"![figure]({image_ref})"}
                                    ],
                                }
                            ]
                        },
                    }
                }
            },
        }
        conversion_config = PdfConversionConfig.model_validate(
            {
                "parser": "remote",
                "visual": {"mode": "off"},
                "remote": {
                    "providers": [
                        {
                            "name": "test-oxr",
                            "provider": "oxr",
                            "base_url": oxr_service["base_url"],
                            "api_key": "dummy-test-key",
                            "timeout": 5,
                        }
                    ]
                },
            }
        )

        outcome = progressPdfConversion(source_pdf, conversion_config)

        assert isinstance(outcome, ReadyConversionOutcome)
        assert len(outcome.assets) == 1
        expected_markdown = (
            f'<table><img src="{outcome.assets[0]}"></table>'
            if image_kind == "html_url"
            else (
                f'# Remote candidate\n\n![figure]({outcome.assets[0]} "figure title")'
                if image_kind == "url_title"
                else f"# Remote candidate\n\n![figure]({outcome.assets[0]})"
            )
        )
        assert outcome.markdown == expected_markdown
        asset_path = source_dir.parent / "assets" / outcome.assets[0].removeprefix("./assets/")
        assert asset_path.is_file()
        assert asset_path.read_bytes() == oxr_service["image_bytes"]
        assert oxr_service["image_requests"] == ([] if image_kind == "base64" else ["/figure.png"])
        assert outcome.page_data["pages"][0]["page_num"] == 0
        assert outcome.page_data["pages"][0]["page_size"] == [100, 200]
        assert (
            outcome.page_data["pages"][0]["blocks"][0]["content"]
            == f"![figure]({outcome.assets[0]})"
        )

    def test_remote_mode_hides_service_error_payload(self, tmp_path, oxr_service):
        """远端错误只返回安全分类，不把任意服务响应写入错误消息。"""
        source_pdf = tmp_path / "paper.pdf"
        source_pdf.write_bytes(b"%PDF-1.4 remote source")
        oxr_service["status"] = 200
        oxr_service["response"] = {"code": "secret-key-from-server", "message": "private"}
        conversion_config = PdfConversionConfig.model_validate(
            {
                "parser": "remote",
                "visual": {"mode": "off"},
                "remote": {
                    "providers": [
                        {
                            "name": "test-oxr",
                            "provider": "oxr",
                            "base_url": oxr_service["base_url"],
                            "api_key": "dummy-test-key",
                            "timeout": 5,
                        }
                    ]
                },
            }
        )

        outcome = progressPdfConversion(source_pdf, conversion_config)

        assert isinstance(outcome, FailedConversionOutcome)
        assert "secret-key-from-server" not in outcome.error.message
        assert "private" not in outcome.error.message
        assert "dummy-test-key" not in outcome.error.message

    @pytest.mark.parametrize("image_kind", ["base64", "corrupt_png", "local_path"])
    def test_remote_mode_rejects_unmaterializable_image(
        self, tmp_path, oxr_service, image_kind
    ):
        """无法解码的图片和服务端本机路径不能作为候选稿采用。"""
        source_dir = tmp_path / "paper" / "source"
        source_dir.mkdir(parents=True)
        source_pdf = source_dir / "source.pdf"
        source_pdf.write_bytes(b"%PDF-1.4 remote source")
        if image_kind == "base64":
            image_ref = "data:image/png;base64,not-base64!"
        elif image_kind == "corrupt_png":
            oxr_service["image_bytes"] = b"not a PNG"
            image_ref = oxr_service["image_url"]
        else:
            local_image = tmp_path / "private figure.png"
            local_image.write_bytes(oxr_service["image_bytes"])
            image_ref = f"<{local_image.as_posix()}>"
        oxr_service["response"] = {
            "code": 0,
            "data": {
                "result": {
                    "outputs": {
                        "markdown": f"![figure]({image_ref})",
                        "json": {"pages": []},
                    }
                }
            },
        }
        conversion_config = PdfConversionConfig.model_validate(
            {
                "parser": "remote",
                "visual": {"mode": "off"},
                "remote": {
                    "providers": [
                        {
                            "name": "test-oxr",
                            "provider": "oxr",
                            "base_url": oxr_service["base_url"],
                            "api_key": "dummy-test-key",
                            "timeout": 5,
                        }
                    ]
                },
            }
        )

        outcome = progressPdfConversion(source_pdf, conversion_config)

        assert isinstance(outcome, FailedConversionOutcome)
        assert outcome.error.code == "remote_parsing_failed"
        assert not (source_dir.parent / "assets").exists()
        assert oxr_service["image_requests"] == ([] if image_kind != "corrupt_png" else ["/figure.png"])


class TestPdfConversionOutcomes:
    """统一转换结果必须可由 ingest 在不读取运行目录时判别。"""

    @pytest.mark.parametrize(
        ("outcome", "kind", "payload_name", "payload"),
        [
            (
                ReadyConversionOutcome("# candidate", ("./assets/fig-001.png",)),
                "ready",
                "markdown",
                "# candidate",
            ),
            (
                AgentActionRequiredOutcome(Path("task-package")),
                "agent_action_required",
                "task_package",
                Path("task-package"),
            ),
            (
                NeedsConfirmationOutcome(("figure crop requires review",)),
                "needs_confirmation",
                "warnings",
                ("figure crop requires review",),
            ),
            (
                FailedConversionOutcome(
                    PdfConversionError(
                        code="visual_model_required", message="visual model is required"
                    )
                ),
                "failed",
                "error",
                PdfConversionError(
                    code="visual_model_required", message="visual model is required"
                ),
            ),
        ],
    )
    def test_outcome_kind_and_payload_are_stable(self, outcome, kind, payload_name, payload):
        """四类结果均有固定 kind 与规定的载荷字段。"""
        assert outcome.kind == kind
        assert getattr(outcome, payload_name) == payload

    def test_ready_outcome_preserves_relative_assets(self):
        """准备就绪结果仅保留 Canonical 可引用的相对资产路径。"""
        outcome = ReadyConversionOutcome(
            "# candidate", ("./assets/fig-001.png", "./assets/table-002.png")
        )

        assert outcome.assets == ("./assets/fig-001.png", "./assets/table-002.png")

    @pytest.mark.parametrize(
        "asset_path",
        [
            "",
            "/tmp/fig-001.png",
            "C:/temp/fig-001.png",
            r"C:\temp\fig-001.png",
            r"\\server\share\fig-001.png",
            "./assets/",
            "./assets/subdir/",
            "./assets/../source.pdf",
            "../assets/fig-001.png",
            "./assets\\fig-001.png",
        ],
    )
    def test_ready_outcome_rejects_noncanonical_asset_paths(self, asset_path):
        """绝对、越界和 Windows 分隔符资产路径均不得进入结果。"""
        with pytest.raises(ValueError):
            ReadyConversionOutcome("# candidate", (asset_path,))


class TestPdfConversionProgress:
    """转换推进边界的最小行为测试。"""

    def test_off_mode_uses_only_deterministic_converter(self, monkeypatch):
        """关闭视觉模式时不触碰真实 PDF，也不调用 Agent 路径。"""
        source_pdf = Path("paper.pdf")
        converted_markdown = "# Deterministic candidate"
        calls = []

        def fake_converter(pdf_path):
            calls.append(pdf_path)
            return converted_markdown

        monkeypatch.setattr(pdf_conversion, "convert_pdf_to_markdown", fake_converter)

        outcome = progressPdfConversion(source_pdf, PdfConversionConfig())

        assert calls == [source_pdf]
        assert isinstance(outcome, ReadyConversionOutcome)
        assert outcome.kind == "ready"
        assert outcome.markdown == converted_markdown
        assert outcome.assets == ()

    def test_off_mode_classifies_deterministic_converter_failure(self, monkeypatch):
        """确定性转换异常必须归类为 failed，而不能泄露到调用者。"""
        source_pdf = Path("paper.pdf")

        def failing_converter(pdf_path):
            raise RuntimeError("conversion failed")

        monkeypatch.setattr(pdf_conversion, "convert_pdf_to_markdown", failing_converter)

        outcome = progressPdfConversion(source_pdf, PdfConversionConfig())

        assert isinstance(outcome, FailedConversionOutcome)
        assert outcome.kind == "failed"
        assert outcome.error.code == "deterministic_conversion_failed"
        assert outcome.error.message

    @pytest.mark.parametrize("mode", ["auto", "always"])
    def test_visual_mode_without_model_returns_classified_failure(self, mode):
        """未配置模型必须返回可分类失败，而非透出宿主平台异常。"""
        conversion_config = PdfConversionConfig.model_validate(
            {"visual": {"mode": mode, "model": ""}}
        )

        outcome = progressPdfConversion(Path("paper.pdf"), conversion_config)

        assert isinstance(outcome, FailedConversionOutcome)
        assert outcome.kind == "failed"
        assert outcome.error.code == "visual_model_required"
        assert outcome.error.message

    def test_auto_mode_routes_deterministic_candidate_to_auto_audit(self, monkeypatch):
        """auto 先产出 Candidate，再由审计边界决定下一步，不能直接建视觉运行。"""
        source_pdf = Path("paper.pdf")
        candidate_markdown = "# Deterministic candidate"
        visual_config = PdfConversionConfig.model_validate(
            {"visual": {"mode": "auto", "model": "host-model"}}
        ).visual
        expected_outcome = AgentActionRequiredOutcome(Path("audit-task-package"))
        calls = []

        monkeypatch.setattr(pdf_conversion, "convert_pdf_to_markdown", lambda _: candidate_markdown)

        def fake_auto_audit(actual_source_pdf, actual_candidate, actual_visual_config):
            calls.append((actual_source_pdf, actual_candidate, actual_visual_config))
            return expected_outcome

        monkeypatch.setattr(pdf_conversion, "prepareOrProgressPdfAutoAudit", fake_auto_audit)

        outcome = progressPdfConversion(
            source_pdf,
            PdfConversionConfig.model_validate({"visual": {"mode": "auto", "model": "host-model"}}),
        )

        assert outcome is expected_outcome
        assert calls == [(source_pdf, candidate_markdown, visual_config)]

    def test_visual_warning_flag_only_forwards_when_explicitly_requested(self, monkeypatch):
        """默认调用保持旧三参数 seam；显式 flag 才向 visual progression 透传。"""
        source_pdf = Path("paper.pdf")
        candidate_markdown = "# Candidate"
        visual_config = PdfConversionConfig.model_validate(
            {"visual": {"mode": "always", "model": "host-model"}}
        )
        expected_outcome = AgentActionRequiredOutcome(Path("visual-run"))
        forwarded: list[bool] = []

        monkeypatch.setattr(pdf_conversion, "convert_pdf_to_markdown", lambda _: candidate_markdown)

        def legacy_progress(actual_source, actual_candidate, actual_config):
            assert (actual_source, actual_candidate, actual_config) == (
                source_pdf,
                candidate_markdown,
                visual_config.visual,
            )
            return expected_outcome

        monkeypatch.setattr(pdf_conversion, "prepareOrProgressVisualConversion", legacy_progress)
        assert progressPdfConversion(source_pdf, visual_config) is expected_outcome

        def accepting_progress(
            actual_source,
            actual_candidate,
            actual_config,
            *,
            accept_visual_warnings=False,
        ):
            assert (actual_source, actual_candidate, actual_config) == (
                source_pdf,
                candidate_markdown,
                visual_config.visual,
            )
            forwarded.append(accept_visual_warnings)
            return expected_outcome

        monkeypatch.setattr(pdf_conversion, "prepareOrProgressVisualConversion", accepting_progress)
        assert (
            progressPdfConversion(
                source_pdf,
                visual_config,
                accept_visual_warnings=True,
            )
            is expected_outcome
        )
        assert forwarded == [True]

    def test_auto_visual_warning_acceptance_progresses_and_adopts_real_run(
        self, tmp_path, monkeypatch
    ):
        """auto 的 visual_required 审计可在后续显式确认时走真实进度并采用资产。"""
        source_pdf = tmp_path / "paper" / "source" / "source.pdf"
        source_pdf.parent.mkdir(parents=True)
        document = pymupdf.open()
        try:
            for page_number in range(1, 4):
                page = document.new_page()
                page.insert_text((72, 72), f"Visual auto source page {page_number}")
            document.save(source_pdf)
        finally:
            document.close()

        candidate_markdown = "# Auto Candidate\n"
        conversion_config = PdfConversionConfig.model_validate(
            {
                "visual": {
                    "mode": "auto",
                    "model": "host-model",
                    "chunk_pages": 2,
                    "retry": 0,
                }
            }
        )
        monkeypatch.setattr(pdf_conversion, "convert_pdf_to_markdown", lambda _: candidate_markdown)

        audit_outcome = progressPdfConversion(source_pdf, conversion_config)
        assert isinstance(audit_outcome, AgentActionRequiredOutcome)
        audit_task = json.loads(
            (audit_outcome.task_package / "task.json").read_text(encoding="utf-8")
        )
        audit_inputs = audit_task["inputs"]
        audit_schema = audit_task["worker_output"]["schema"]
        (audit_outcome.task_package / "result.json").write_text(
            json.dumps(
                {
                    "kind": audit_schema["kind"],
                    "version": audit_schema["version"],
                    "source_pdf_sha256": audit_inputs["source_pdf"]["sha256"],
                    "candidate_sha256": audit_inputs["candidate"]["sha256"],
                    "decision": "visual_required",
                    "layout": "multi_column",
                    "flagged_pages": [1],
                    "reasons": ["Reading order needs visual review."],
                }
            ),
            encoding="utf-8",
        )

        run_outcome = progressPdfConversion(source_pdf, conversion_config)
        assert isinstance(run_outcome, AgentActionRequiredOutcome)
        run_dir = run_outcome.task_package
        assert run_dir.parent.name == ".visual-runs"
        for index, task_dir in enumerate(sorted((run_dir / "tasks").iterdir())):
            task = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
            run = task["run"]
            chunk = task["chunk"]
            core_pages = chunk["core_pages"]
            crop_requests = []
            warnings = []
            if index == 0:
                crop_requests = [
                    {
                        "page": core_pages[0],
                        "bbox": [0.1, 0.2, 0.8, 0.9],
                        "kind": "formula",
                    }
                ]
                warnings = ["Formula crop requires user confirmation."]
            result = {
                "schema_version": "visual-chunk-result-v1",
                "run_id": run["run_id"],
                "candidate_sha256": run["candidate_sha256"],
                "chunk_id": chunk["chunk_id"],
                "core_pages": core_pages,
                "status": "completed",
                "covered_pages": core_pages,
                "warnings": warnings,
                "unresolved_issues": [],
                "failure_code": None,
                "crop_requests": crop_requests,
            }
            markdown = "".join(
                f"<!-- paperbase:visual-page-start page={page_number} -->\n"
                f"Visual page {page_number}.\n"
                f"<!-- paperbase:visual-page-end page={page_number} -->\n"
                for page_number in core_pages
            )
            (task_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
            (task_dir / "result.md").write_text(markdown, encoding="utf-8")

        boundary_outcome = progressPdfConversion(source_pdf, conversion_config)
        assert isinstance(boundary_outcome, AgentActionRequiredOutcome)
        boundary_task = json.loads(
            (boundary_outcome.task_package / "task.json").read_text(encoding="utf-8")
        )
        boundary_run = boundary_task["run"]
        (boundary_outcome.task_package / "result.json").write_text(
            json.dumps(
                {
                    "schema_version": "visual-boundary-review-result-v1",
                    "run_id": boundary_run["run_id"],
                    "candidate_sha256": boundary_run["candidate_sha256"],
                    "decision": "pass",
                    "checked_item_ids": [item["item_id"] for item in boundary_task["items"]],
                    "affected_chunk_ids": [],
                    "unresolved_issues": [],
                    "warnings": [],
                }
            ),
            encoding="utf-8",
        )

        ready_outcome = progressPdfConversion(
            source_pdf,
            conversion_config,
            accept_visual_warnings=True,
        )
        repeated_outcome = progressPdfConversion(
            source_pdf,
            conversion_config,
            accept_visual_warnings=True,
        )

        expected_asset = "./assets/visual-page-0001-formula-01.png"
        assert isinstance(ready_outcome, ReadyConversionOutcome)
        assert ready_outcome.assets == (expected_asset,)
        assert expected_asset in ready_outcome.markdown
        assert (
            source_pdf.parent.parent / "assets" / expected_asset.removeprefix("./assets/")
        ).is_file()
        assert repeated_outcome == ready_outcome
