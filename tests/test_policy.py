"""来源策略的单元测试：纯函数，不起服务、不连模型。"""
from __future__ import annotations

from local_app.policy import (
    DEFAULT_POLICY,
    SourcePolicy,
    apply_source_policy,
    explain,
)


def _reasons(dropped):
    return [d.reason for d in dropped]


def test_keeps_order_and_accepts_https():
    kept, dropped = apply_source_policy(["https://a.com/x", "http://b.com/y"])
    assert kept == ["https://a.com/x", "http://b.com/y"]
    assert dropped == []


def test_third_url_on_same_domain_is_dropped():
    urls = ["https://a.com/1", "https://a.com/2", "https://a.com/3"]
    kept, dropped = apply_source_policy(urls)
    assert kept == ["https://a.com/1", "https://a.com/2"]
    assert _reasons(dropped) == ["同一域名最多 2 条"]


def test_www_and_bare_domain_count_as_same():
    urls = ["https://www.a.com/1", "https://a.com/2", "https://www.a.com/3"]
    kept, _ = apply_source_policy(urls)
    assert kept == ["https://www.a.com/1", "https://a.com/2"]


def test_duplicate_url_is_dropped():
    kept, dropped = apply_source_policy(["https://a.com/x", "https://A.com/x#frag"])
    assert kept == ["https://a.com/x"]
    assert _reasons(dropped) == ["重复链接"]


def test_trailing_slash_is_duplicate():
    kept, dropped = apply_source_policy(["https://a.com/x", "https://a.com/x/"])
    assert len(kept) == 1
    assert _reasons(dropped) == ["重复链接"]


def test_non_http_scheme_rejected():
    kept, dropped = apply_source_policy(["ftp://a.com/x", "file:///etc/passwd"])
    assert kept == []
    assert _reasons(dropped) == ["只允许 http/https 链接"] * 2


def test_blocked_domain():
    policy = SourcePolicy(blocked_domains=("evil.com",))
    kept, dropped = apply_source_policy(["https://evil.com/x", "https://a.com/y"], policy)
    assert kept == ["https://a.com/y"]
    assert _reasons(dropped) == ["域名在黑名单内"]


def test_blocked_subdomain_also_matches():
    policy = SourcePolicy(blocked_domains=("evil.com",))
    _, dropped = apply_source_policy(["https://cdn.evil.com/x"], policy)
    assert _reasons(dropped) == ["域名在黑名单内"]


def test_allowlist_only_keeps_listed_domains():
    policy = SourcePolicy(allowed_domains=("docs.python.org",))
    kept, dropped = apply_source_policy(
        ["https://docs.python.org/3/", "https://example.com/x"], policy
    )
    assert kept == ["https://docs.python.org/3/"]
    assert _reasons(dropped) == ["域名不在白名单内"]


def test_max_sources_cap():
    policy = SourcePolicy(max_sources=2, per_domain_limit=5)
    urls = ["https://a.com/1", "https://b.com/2", "https://c.com/3"]
    kept, dropped = apply_source_policy(urls, policy)
    assert kept == ["https://a.com/1", "https://b.com/2"]
    assert _reasons(dropped) == ["超过总数上限 2 条"]


def test_empty_and_none_input():
    assert apply_source_policy(None) == ([], [])
    assert apply_source_policy([]) == ([], [])
    assert apply_source_policy(["", "   "]) == ([], [])


def test_default_policy_values():
    assert DEFAULT_POLICY.per_domain_limit == 2
    assert DEFAULT_POLICY.max_sources == 5


def test_explain_joins_url_and_reason():
    _, dropped = apply_source_policy(["ftp://a.com/x"])
    text = explain(dropped)
    assert "ftp://a.com/x" in text and "只允许" in text
