"""PDF 转换的统一结果契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeAlias
from urllib.parse import urlparse

from paperbase.adapters.oxr_parser import OxrCandidateError, parseWithOxr
from paperbase.adapters.pdf_converter import convert_pdf_to_markdown
from paperbase.config.models import PdfConversionConfig
from paperbase.core.pdf_auto_audit import prepareOrProgressPdfAutoAudit
from paperbase.core.visual_progress import prepareOrProgressVisualConversion

if TYPE_CHECKING:
    from paperbase.config.models import RemotePdfProviderConfig, VisualPdfConfig


def _validate_asset_path(asset_path: str) -> None:
    """确保转换结果只引用 Canonical 允许的相对资产路径。"""
    if not isinstance(asset_path, str):
        raise ValueError("资产路径必须是字符串")
    if not asset_path.startswith("./assets/") or "\\" in asset_path:
        raise ValueError("资产路径必须使用 ./assets/... 相对路径")

    relative_parts = asset_path[2:].split("/")
    if len(relative_parts) < 2 or any(part in {"", ".", ".."} for part in relative_parts):
        raise ValueError("资产路径必须使用 ./assets/... 相对路径")


@dataclass(frozen=True)
class PdfConversionError:
    """可由 ingest 状态机映射的转换错误。"""

    code: str
    message: str


@dataclass(frozen=True)
class ReadyConversionOutcome:
    """转换已完成，可由 ingest 采用。"""

    markdown: str
    assets: tuple[str, ...] = ()
    converter: str | None = None
    converter_version: str | None = None
    page_data: dict[str, object] | None = None
    kind: Literal["ready"] = field(default="ready", init=False)

    def __post_init__(self) -> None:
        normalized_assets = tuple(self.assets)
        for asset_path in normalized_assets:
            _validate_asset_path(asset_path)
        object.__setattr__(self, "assets", normalized_assets)


@dataclass(frozen=True)
class AgentActionRequiredOutcome:
    """PaperBase 已准备任务，等待 Agent Host 接手。"""

    task_package: Path
    kind: Literal["agent_action_required"] = field(
        default="agent_action_required",
        init=False,
    )


@dataclass(frozen=True)
class NeedsConfirmationOutcome:
    """转换完成，但仍需用户确认警告。"""

    warnings: tuple[str, ...]
    kind: Literal["needs_confirmation"] = field(
        default="needs_confirmation",
        init=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "warnings", tuple(self.warnings))


@dataclass(frozen=True)
class FailedConversionOutcome:
    """转换未完成，携带可分类错误。"""

    error: PdfConversionError
    kind: Literal["failed"] = field(default="failed", init=False)


PdfConversionOutcome: TypeAlias = (
    ReadyConversionOutcome
    | AgentActionRequiredOutcome
    | NeedsConfirmationOutcome
    | FailedConversionOutcome
)


def progressPdfConversion(  # noqa: N802
    source_pdf: Path,
    conversion_config: PdfConversionConfig,
    *,
    accept_visual_warnings: bool = False,
    re_review: bool = False,
) -> PdfConversionOutcome:
    """推进一次 PDF 转换，而不绑定具体 Agent Host。"""
    if conversion_config.parser == "remote":
        return _progressRemoteConversion(source_pdf, conversion_config)

    visual_config = conversion_config.visual

    if visual_config.mode != "off":
        if not visual_config.model.strip():
            return FailedConversionOutcome(
                error=PdfConversionError(
                    code="visual_model_required",
                    message="visual mode requires conversion.pdf.visual.model",
                )
            )
        try:
            candidate_markdown = convert_pdf_to_markdown(source_pdf)
        except Exception:
            return FailedConversionOutcome(
                error=PdfConversionError(
                    code="visual_candidate_conversion_failed",
                    message="could not prepare deterministic visual conversion candidate",
                )
            )

        if visual_config.mode == "auto":
            try:
                if re_review:
                    auto_outcome = prepareOrProgressPdfAutoAudit(
                        source_pdf,
                        candidate_markdown,
                        visual_config,
                        accept_visual_warnings=accept_visual_warnings,
                        re_review=True,
                    )
                elif accept_visual_warnings:
                    auto_outcome = prepareOrProgressPdfAutoAudit(
                        source_pdf,
                        candidate_markdown,
                        visual_config,
                        accept_visual_warnings=True,
                    )
                else:
                    auto_outcome = prepareOrProgressPdfAutoAudit(
                        source_pdf,
                        candidate_markdown,
                        visual_config,
                    )
                return auto_outcome
            except Exception:
                return FailedConversionOutcome(
                    error=PdfConversionError(
                        code="visual_auto_audit_preparation_failed",
                        message="could not prepare automatic PDF layout audit task package",
                    )
                )

        return _progressVisualConversion(
            source_pdf,
            candidate_markdown,
            visual_config,
            accept_visual_warnings,
            re_review,
        )

    try:
        markdown = convert_pdf_to_markdown(source_pdf)
    except Exception as exc:
        return FailedConversionOutcome(
            error=PdfConversionError(
                code="deterministic_conversion_failed",
                message=str(exc),
            )
        )

    return ReadyConversionOutcome(markdown=markdown)


def _progressRemoteConversion(  # noqa: N802
    source_pdf: Path,
    conversion_config: PdfConversionConfig,
) -> PdfConversionOutcome:
    """在 visual 关闭时用单条 OXR 配置取得远程解析候选。"""
    if conversion_config.visual.mode != "off":
        return FailedConversionOutcome(
            error=PdfConversionError(
                code="remote_visual_unsupported",
                message="remote PDF parsing does not support visual review yet",
            )
        )

    providers = conversion_config.remote.providers
    if not providers:
        return FailedConversionOutcome(
            error=PdfConversionError(
                code="remote_config_invalid",
                message="remote PDF parsing requires conversion.pdf.remote.providers",
            )
        )
    provider_names: set[str] = set()
    for provider in providers:
        problem = _remoteProviderProblem(provider)
        if problem is not None:
            return FailedConversionOutcome(
                error=PdfConversionError(code="remote_config_invalid", message=problem)
            )
        name = provider.name.strip()
        if name in provider_names:
            return FailedConversionOutcome(
                error=PdfConversionError(
                    code="remote_config_invalid",
                    message=f"remote provider name must be unique: {name}",
                )
            )
        provider_names.add(name)

    failures: list[str] = []
    has_transient_failure = False
    for provider in providers:
        try:
            candidate = parseWithOxr(source_pdf, provider)
        except OxrCandidateError as exc:
            failures.append(f"{provider.name.strip()}: {exc}")
            has_transient_failure |= exc.transient
            continue

        return ReadyConversionOutcome(
            markdown=candidate.markdown,
            assets=candidate.assets,
            converter=f"oxr:{provider.name.strip()}",
            converter_version="unknown",
            page_data=candidate.page_data,
        )

    return FailedConversionOutcome(
        error=PdfConversionError(
            code=(
                "remote_transient_failure"
                if has_transient_failure
                else "remote_all_profiles_failed"
            ),
            message="all remote parsing profiles failed: " + "; ".join(failures),
        )
    )


def _remoteProviderProblem(provider: RemotePdfProviderConfig) -> str | None:  # noqa: N802
    """返回远程配置问题；消息只含配置名与字段，不含密钥。"""
    name = provider.name.strip()
    if not name:
        return "remote provider requires a name"
    if provider.provider != "oxr":
        return f"remote provider {name} is not supported"
    try:
        parsed_url = urlparse(provider.base_url)
        valid_url = (
            parsed_url.scheme in {"http", "https"}
            and parsed_url.hostname is not None
            and not any(char.isspace() for char in provider.base_url)
        )
        parsed_url.port
    except ValueError:
        valid_url = False
    if not valid_url:
        return f"remote provider {name} requires an http(s) base_url"
    if provider.timeout is None or not isfinite(provider.timeout) or provider.timeout <= 0:
        return f"remote provider {name} requires a positive timeout"
    if not provider.api_key.strip():
        return f"remote provider {name} requires an api_key environment reference"
    return None


def _progressVisualConversion(  # noqa: N802
    source_pdf: Path,
    candidate_markdown: str,
    visual_config: VisualPdfConfig,
    accept_visual_warnings: bool,
    re_review: bool = False,
) -> PdfConversionOutcome:
    # 默认路径保持既有调用形状不变；只有显式 re_review 才透传新关键字。
    if re_review:
        return prepareOrProgressVisualConversion(
            source_pdf,
            candidate_markdown,
            visual_config,
            accept_visual_warnings=accept_visual_warnings,
            re_review=True,
        )
    if accept_visual_warnings:
        return prepareOrProgressVisualConversion(
            source_pdf,
            candidate_markdown,
            visual_config,
            accept_visual_warnings=True,
        )
    return prepareOrProgressVisualConversion(
        source_pdf,
        candidate_markdown,
        visual_config,
    )
