"""来源策略：在进入研究图之前，先对用户给的 source_urls 做一轮过滤。

为什么要这一层：
- 同一站点塞 5 条会把报告的来源结构变成“单一来源”，看起来引用了很多，其实是同一家在说；
- 重复链接会让总结节点重复阅读同一段内容，浪费上下文；
- 黑名单用于排除已知不可靠或内部地址。

规则按顺序执行，被丢弃的链接都带原因，方便在接口返回里解释。
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

ALLOWED_SCHEMES = ("http", "https")


@dataclass(frozen=True)
class SourcePolicy:
    per_domain_limit: int = 2
    max_sources: int = 5
    allowed_domains: tuple[str, ...] = ()
    blocked_domains: tuple[str, ...] = ()


DEFAULT_POLICY = SourcePolicy()


@dataclass(frozen=True)
class DroppedSource:
    url: str
    reason: str


def _host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _normalize(url: str) -> str:
    """去掉协议大小写差异、fragment 和结尾斜杠，用于判重。"""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{scheme}://{host}{path}{query}"


def _matches(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def apply_source_policy(
    urls: list[str] | None,
    policy: SourcePolicy = DEFAULT_POLICY,
) -> tuple[list[str], list[DroppedSource]]:
    """返回 (保留的链接, 被丢弃的链接及原因)。保留顺序与输入一致。"""
    kept: list[str] = []
    dropped: list[DroppedSource] = []
    seen: set[str] = set()
    per_domain: dict[str, int] = {}

    for raw in urls or []:
        url = (raw or "").strip()
        if not url:
            continue

        parsed = urlparse(url)
        if parsed.scheme.lower() not in ALLOWED_SCHEMES:
            dropped.append(DroppedSource(url, "只允许 http/https 链接"))
            continue

        host = _host(url)
        if not host:
            dropped.append(DroppedSource(url, "无法解析域名"))
            continue

        if policy.blocked_domains and _matches(host, policy.blocked_domains):
            dropped.append(DroppedSource(url, "域名在黑名单内"))
            continue

        if policy.allowed_domains and not _matches(host, policy.allowed_domains):
            dropped.append(DroppedSource(url, "域名不在白名单内"))
            continue

        key = _normalize(url)
        if key in seen:
            dropped.append(DroppedSource(url, "重复链接"))
            continue

        used = per_domain.get(host, 0)
        if used >= policy.per_domain_limit:
            dropped.append(
                DroppedSource(url, f"同一域名最多 {policy.per_domain_limit} 条")
            )
            continue

        if len(kept) >= policy.max_sources:
            dropped.append(DroppedSource(url, f"超过总数上限 {policy.max_sources} 条"))
            continue

        seen.add(key)
        per_domain[host] = used + 1
        kept.append(url)

    return kept, dropped


def explain(dropped: list[DroppedSource]) -> str:
    """把丢弃原因拼成一句可直接放进错误信息的话。"""
    return "；".join(f"{d.url}（{d.reason}）" for d in dropped)
