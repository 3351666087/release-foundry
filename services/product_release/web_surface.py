"""Fail-closed static gate for the production Web surface.

This verifier belongs to the ReleaseFoundry Product Release.  It does not evaluate a
customer Agent and it cannot approve a Customer Agent Release.

The gate intentionally checks source rather than a generated ``.next`` tree so
that its result is reproducible and reviewable:

* every production Web source file must be strict UTF-8;
* replacement/private-use characters and common mojibake sequences are blocked;
* production runtime source cannot expose mock, fixture, demo-only, read-only
  preview, or "not implemented" behavior;
* CSS must meet the minimum typography and control-size contract used by the
  enterprise control panel.

Browser E2E remains a separate Product Release requirement.  Passing this
static gate never substitutes for registration/login, SDK quickstart, report,
or review E2E receipts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import platform
import re
from typing import Iterable


WEB_SURFACE_VERIFICATION_SCHEMA = "releasefoundry.web_surface_verification.v1"
WEB_SURFACE_POLICY_ID = "releasefoundry.web.production_surface.v1"
WEB_SURFACE_RECEIPT_ID = "web.production_surface"

_SOURCE_SUFFIXES = {
    ".css",
    ".js",
    ".jsx",
    ".json",
    ".mdx",
    ".ts",
    ".tsx",
}
_IGNORED_PATH_PARTS = {
    ".next",
    "__fixtures__",
    "__mocks__",
    "__snapshots__",
    "__tests__",
    "coverage",
    "fixtures",
    "mocks",
    "node_modules",
    "playwright-report",
    "test-results",
    "tests",
}
_IGNORED_FILE_MARKERS = (
    ".spec.",
    ".stories.",
    ".story.",
    ".test.",
)

_CSS_RULE_RE = re.compile(r"(?s)([^{}]+)\{([^{}]*)\}")
_CSS_DECLARATION_RE = re.compile(
    r"(?im)(?P<property>font-size|min-height|height)\s*:\s*"
    r"(?P<value>-?(?:\d+(?:\.\d+)?|\.\d+))px\b"
)
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

_BODY_TEXT_TARGETS = re.compile(
    r"(?:^|[-_.#])(?:body|copy|description|paragraph|prose|lede|lead|"
    r"bodycopy|body-copy|longform|long-form)(?:$|[-_.:#\[])"
)
_METADATA_TARGETS = re.compile(
    r"(?:^|[-_.#])(?:meta|metadata|eyebrow|caption|kicker|overline|"
    r"badge|tag|timestamp|status)(?:$|[-_.:#\[])"
)
_PAGE_TITLE_TARGETS = re.compile(
    r"(?:^|[-_.#])(?:page-title|pagetitle|hero-title|herotitle|"
    r"display-title|displaytitle)(?:$|[-_.:#\[])"
)
_INTERACTIVE_CLASS_TARGETS = re.compile(
    r"(?:^|[-_.#])(?:button|btn|control|input|select|toggle|switch|"
    r"trigger|action|submit|cancel|tab|link)(?:$|[-_.:#\[])"
)
_TABLE_OR_NAV_TARGETS = re.compile(
    r"(?:^|[-_.#])(?:nav|navigation|menu|table|thead|tbody|row|cell|"
    r"column)(?:$|[-_.:#\[])"
)

_FORBIDDEN_RUNTIME_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "production_mock",
        re.compile(r"(?i)(?:\bapi[-_ ]?mock\b|\bmock(?:ed|ing|s)?\b)"),
        "production Web source must not ship mock behavior or data",
    ),
    (
        "production_fixture",
        re.compile(
            r"(?i)(?<![A-Za-z0-9])fixture(?:s|d|[-_ ]?backed)?"
            r"(?![A-Za-z0-9])"
        ),
        "production Web source must not ship fixture behavior or data",
    ),
    (
        "not_implemented",
        re.compile(
            r"(?i)(?:not[ -]?implemented|coming[ -]?soon|"
            r"暂未实现|尚未实现|即将推出|即将上线)"
        ),
        "user-visible or runtime 'not implemented' behavior is forbidden",
    ),
    (
        "read_only_preview",
        re.compile(
            r"(?i)(?:read[ -]?only[ -]?preview|preview[ -]?identity|"
            r"只读预览|预览身份)"
        ),
        "production access cannot fall back to a read-only preview identity",
    ),
    (
        "demo_only",
        re.compile(
            r"(?i)(?:demo[ -]?only|preview[ -]?only|demo[ -]?data|"
            r"演示模式|演示数据|仅供演示)"
        ),
        "demo-only behavior cannot satisfy the production Web contract",
    ),
)

_LATIN_MOJIBAKE_RE = re.compile(
    r"(?:Ã[\x80-\xBF]|Â[\x80-\xBF]|â(?:€|™|œ|ž|“|”|‘|’)|ï¿½)"
)
_CJK_MOJIBAKE_RE = re.compile(
    r"(?:鐨勀?|涓€|涓婃|涓嬫|浣跨敤|璇锋|鏆傛湭|鍙戝竷|"
    r"璁剧疆|鐧诲綍|娉ㄥ唽|鎴愬姛|澶辫触|瀵嗙爜|"
    r"鐢ㄦ埛|璇勬祴|鎶ュ憡)"
)
_CJK_REPLACEMENT_QUESTION_RE = re.compile(
    r"(?<=[\u3400-\u9fff])\?(?=[A-Za-z\u3400-\u9fff])"
)
_PRIVATE_USE_RE = re.compile(r"[\ue000-\uf8ff]")


@dataclass(frozen=True)
class WebSurfaceIssue:
    code: str
    path: str
    line: int
    column: int
    message: str


def _line_and_column(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    previous_newline = text.rfind("\n", 0, offset)
    column = offset + 1 if previous_newline < 0 else offset - previous_newline
    return line, column


def _iter_source_files(web_root: Path) -> Iterable[Path]:
    for path in sorted(web_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(web_root)
        lowered_parts = {part.lower() for part in relative.parts}
        if lowered_parts & _IGNORED_PATH_PARTS:
            continue
        lowered_name = path.name.lower()
        if any(marker in lowered_name for marker in _IGNORED_FILE_MARKERS):
            continue
        yield path


def _rightmost_selector_target(selector: str) -> str:
    selector = selector.strip()
    if not selector:
        return ""
    # Attribute selectors used by this project do not contain combinators, so a
    # compact split is sufficient and avoids treating child SVG/span dimensions
    # as the dimensions of their parent button.
    parts = re.split(r"\s+|[>+~]", selector)
    return next((part for part in reversed(parts) if part), "")


def _selector_targets(selector_group: str) -> list[str]:
    return [
        _rightmost_selector_target(selector)
        for selector in selector_group.split(",")
        if selector.strip()
    ]


def _is_interactive_target(target: str) -> bool:
    lowered = target.lower()
    if "::before" in lowered or "::after" in lowered:
        return False
    if re.match(r"^(?:button|input|select|textarea|summary)(?:$|[:.\[#])", lowered):
        return True
    if "[role=\"button\"]" in lowered or "[role='button']" in lowered:
        return True
    return bool(_INTERACTIVE_CLASS_TARGETS.search(lowered))


def _font_floor(targets: list[str]) -> tuple[float, str]:
    lowered = " ".join(target.lower() for target in targets)
    if any(
        re.match(r"^h[12](?:$|[:.\[#])", target.lower())
        for target in targets
    ) or _PAGE_TITLE_TARGETS.search(lowered):
        return 28.0, "page and hero titles must be at least 28px"
    if (
        re.match(r"^(?:body|p)(?:$|[:.\[#])", lowered)
        or _BODY_TEXT_TARGETS.search(lowered)
    ):
        return 16.0, "body copy must be at least 16px"
    if (
        any(_is_interactive_target(target) for target in targets)
        or any(
            re.match(r"^(?:nav|table|thead|tbody|tr|th|td)(?:$|[:.\[#])", target.lower())
            for target in targets
        )
        or _TABLE_OR_NAV_TARGETS.search(lowered)
    ):
        return 14.0, "navigation, tables, and controls must be at least 14px"
    if _METADATA_TARGETS.search(lowered):
        return 12.0, "metadata and eyebrow text must be at least 12px"
    return 12.0, "all visible text must be at least 12px"


def _scan_css(relative_path: str, text: str) -> list[WebSurfaceIssue]:
    issues: list[WebSurfaceIssue] = []
    text_without_comments = _CSS_COMMENT_RE.sub(
        lambda match: "\n" * match.group(0).count("\n"),
        text,
    )
    for rule_match in _CSS_RULE_RE.finditer(text_without_comments):
        selector_group = rule_match.group(1).strip()
        declarations = rule_match.group(2)
        targets = _selector_targets(selector_group)
        if not targets:
            continue
        for declaration in _CSS_DECLARATION_RE.finditer(declarations):
            property_name = declaration.group("property").lower()
            value = float(declaration.group("value"))
            absolute_offset = rule_match.start(2) + declaration.start("value")
            line, column = _line_and_column(text_without_comments, absolute_offset)
            if property_name == "font-size":
                floor, requirement = _font_floor(targets)
                if value < floor:
                    issues.append(
                        WebSurfaceIssue(
                            code="font_size_below_policy",
                            path=relative_path,
                            line=line,
                            column=column,
                            message=(
                                f"{selector_group!r} uses {value:g}px; "
                                f"{requirement}"
                            ),
                        )
                    )
                continue
            if not any(_is_interactive_target(target) for target in targets):
                continue
            if value < 40:
                issues.append(
                    WebSurfaceIssue(
                        code="control_height_below_policy",
                        path=relative_path,
                        line=line,
                        column=column,
                        message=(
                            f"{selector_group!r} uses {property_name} {value:g}px; "
                            "interactive controls must be at least 40px high"
                        ),
                    )
                )
            elif property_name == "height" and value > 48:
                issues.append(
                    WebSurfaceIssue(
                        code="fixed_control_height_above_policy",
                        path=relative_path,
                        line=line,
                        column=column,
                        message=(
                            f"{selector_group!r} fixes height at {value:g}px; "
                            "fixed control heights must stay within 40–48px"
                        ),
                    )
                )
    return issues


def _scan_text(
    relative_path: str,
    text: str,
    *,
    scan_runtime_terms: bool,
) -> list[WebSurfaceIssue]:
    issues: list[WebSurfaceIssue] = []
    character_patterns = (
        (
            "unicode_replacement_character",
            re.compile("\ufffd"),
            "contains the Unicode replacement character",
        ),
        (
            "private_use_character",
            _PRIVATE_USE_RE,
            "contains a private-use character and cannot be trusted as source text",
        ),
        (
            "suspected_latin_mojibake",
            _LATIN_MOJIBAKE_RE,
            "contains a common UTF-8/Latin-1 mojibake sequence",
        ),
        (
            "suspected_cjk_mojibake",
            _CJK_MOJIBAKE_RE,
            "contains a common UTF-8/GBK mojibake sequence",
        ),
        (
            "suspected_lossy_cjk_decode",
            _CJK_REPLACEMENT_QUESTION_RE,
            "contains a question-mark replacement inside CJK text",
        ),
    )
    for code, pattern, message in character_patterns:
        for match in pattern.finditer(text):
            line, column = _line_and_column(text, match.start())
            issues.append(
                WebSurfaceIssue(
                    code=code,
                    path=relative_path,
                    line=line,
                    column=column,
                    message=message,
                )
            )
    if scan_runtime_terms:
        for code, pattern, message in _FORBIDDEN_RUNTIME_PATTERNS:
            for match in pattern.finditer(text):
                line, column = _line_and_column(text, match.start())
                issues.append(
                    WebSurfaceIssue(
                        code=code,
                        path=relative_path,
                        line=line,
                        column=column,
                        message=message,
                    )
                )
    return issues


def verify_web_production_surface(
    web_root: str | Path,
    *,
    repo_root: str | Path | None = None,
) -> dict[str, object]:
    """Inspect the production Web source and return a fail-closed decision."""

    root = Path(web_root)
    repository = Path(repo_root).resolve() if repo_root is not None else root.resolve().parent
    resolved_root = root.resolve()
    issues: list[WebSurfaceIssue] = []
    scanned_files: list[str] = []

    if not resolved_root.is_dir():
        issues.append(
            WebSurfaceIssue(
                code="missing_web_root",
                path=str(root),
                line=1,
                column=1,
                message="the production Web source directory does not exist",
            )
        )
    else:
        for path in _iter_source_files(resolved_root):
            try:
                relative_path = path.resolve().relative_to(repository).as_posix()
            except ValueError:
                relative_path = path.relative_to(resolved_root).as_posix()
            scanned_files.append(relative_path)
            try:
                raw = path.read_bytes()
            except OSError as exc:
                issues.append(
                    WebSurfaceIssue(
                        code="web_source_read_failed",
                        path=relative_path,
                        line=1,
                        column=1,
                        message=str(exc),
                    )
                )
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                prefix = raw[: exc.start].decode("utf-8", errors="ignore")
                line, column = _line_and_column(prefix, len(prefix))
                issues.append(
                    WebSurfaceIssue(
                        code="invalid_utf8",
                        path=relative_path,
                        line=line,
                        column=column,
                        message=str(exc),
                    )
                )
                continue
            issues.extend(
                _scan_text(
                    relative_path,
                    text,
                    scan_runtime_terms=path.suffix.lower() != ".css",
                )
            )
            if path.suffix.lower() == ".css":
                issues.extend(_scan_css(relative_path, text))

    issues = sorted(
        set(issues),
        key=lambda issue: (issue.path, issue.line, issue.column, issue.code),
    )
    approved = not issues and bool(scanned_files)
    if not scanned_files and not any(issue.code == "missing_web_root" for issue in issues):
        issues.append(
            WebSurfaceIssue(
                code="empty_web_surface",
                path=str(root),
                line=1,
                column=1,
                message="no production Web source files were found",
            )
        )
        approved = False

    return {
        "schema_version": WEB_SURFACE_VERIFICATION_SCHEMA,
        "policy_id": WEB_SURFACE_POLICY_ID,
        "decision": "approve_web_surface" if approved else "block_web_surface",
        "scanned_file_count": len(scanned_files),
        "scanned_files": scanned_files,
        "issue_count": len(issues),
        "blocking_reasons": sorted({issue.code for issue in issues}),
        "issues": [asdict(issue) for issue in issues],
        "environment": {
            "os": platform.system().lower(),
            "arch": platform.machine().lower(),
        },
    }
