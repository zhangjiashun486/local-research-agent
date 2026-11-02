import os
import httpx
import requests
from typing import Dict, Any, List, Union, Optional

from markdownify import markdownify
from langsmith import traceable
from tavily import TavilyClient
from ddgs import DDGS

from langchain_community.utilities import SearxSearchWrapper

# Constants
CHARS_PER_TOKEN = 4


def get_config_value(value: Any) -> str:
    """
    Convert configuration values to string format, handling both string and enum types.

    Args:
        value (Any): The configuration value to process. Can be a string or an Enum.

    Returns:
        str: The string representation of the value.

    Examples:
        >>> get_config_value("tavily")
        'tavily'
        >>> get_config_value(SearchAPI.TAVILY)
        'tavily'
    """
    return value if isinstance(value, str) else value.value


def strip_thinking_tokens(text: str) -> str:
    """
    Remove <think> and </think> tags and their content from the text.

    Iteratively removes all occurrences of content enclosed in thinking tokens.

    Args:
        text (str): The text to process

    Returns:
        str: The text with thinking tokens and their content removed
    """
    while "<think>" in text and "</think>" in text:
        start = text.find("<think>")
        end = text.find("</think>") + len("</think>")
        text = text[:start] + text[end:]
    return text


def deduplicate_and_format_sources(
    search_response: Union[Dict[str, Any], List[Dict[str, Any]]],
    max_tokens_per_source: int,
    fetch_full_page: bool = False,
    max_total_chars: int = 20_000,
) -> str:
    """Format one copy per URL with per-source and combined character limits.

    The legacy token hint is converted to a character budget, not an exact
    tokenizer count. Both snippet and full-page modes obey the same limits.
    """
    if max_tokens_per_source < 1 or max_total_chars < 1:
        raise ValueError("Source context budgets must be positive")
    if isinstance(search_response, dict):
        rows = search_response["results"]
    elif isinstance(search_response, list):
        rows = []
        for item in search_response:
            rows.extend(item["results"] if isinstance(item, dict) and "results" in item else [item])
    else:
        raise ValueError("Input must be a dict with results or a list of sources")
    unique = {}
    for row in rows:
        unique.setdefault(row["url"], row)
    if not unique:
        return "Sources:"[:max_total_chars]
    prefix = "Sources:\n\n"
    headers = [f"Source: {str(row.get('title') or '')[:200]}\nURL: {row['url']}\nContent:\n" for row in unique.values()]
    remaining = max_total_chars - len(prefix) - sum(map(len, headers)) - 2 * len(headers)
    if remaining < len(headers):
        raise ValueError("Source metadata exceeds the context budget")
    allowance = min(max_tokens_per_source * CHARS_PER_TOKEN, remaining // len(headers))
    sections = []
    for header, row in zip(headers, unique.values()):
        content = (row.get("raw_content") if fetch_full_page else None) or row.get("content") or ""
        content = str(content)
        if len(content) > allowance:
            marker = "… [truncated]"
            content = content[:max(0, allowance - len(marker))] + marker[:allowance]
        sections.append(header + content)
    return prefix + "\n\n".join(sections)


def format_sources(search_results: Dict[str, Any]) -> str:
    """
    Format search results into a bullet-point list of sources with URLs.

    Creates a simple bulleted list of search results with title and URL for each source.

    Args:
        search_results (Dict[str, Any]): Search response containing a 'results' key with
                                        a list of search result objects

    Returns:
        str: Formatted string with sources as bullet points in the format "* title : url"
    """
    lines=[]
    for source in search_results["results"]:
        label=f"[{source['source_id']}] " if source.get('source_id') else ''
        lines.append(f"* {label}{source['title']} : {source['url']}")
    return "\n".join(lines)


def fetch_raw_content(url: str) -> Optional[str]:
    """
    Fetch HTML content from a URL and convert it to markdown format.

    Uses a 10-second timeout to avoid hanging on slow sites or large pages.

    Args:
        url (str): The URL to fetch content from

    Returns:
        Optional[str]: The fetched content converted to markdown if successful,
                      None if any error occurs during fetching or conversion
    """
    try:
        # Create a client with reasonable timeout
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)
            response.raise_for_status()
            return markdownify(response.text)
    except Exception as e:
        print(f"Warning: Failed to fetch full page content for {url}: {str(e)}")
        return None


def fetch_provided_sources(urls: list[str]) -> dict:
    """Read bounded public static documents using the shared project reader."""
    from .webpage import read_webpage
    results=[]
    for url in dict.fromkeys(urls):
        row=read_webpage(url)
        if row['content']:
            results.append(row)
    return {'results':results}


@traceable
def duckduckgo_search(
    query: str, max_results: int = 3, fetch_full_page: bool = False
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search the web using DuckDuckGo and return formatted results.

    Uses the DDGS library to perform web searches through DuckDuckGo.

    Args:
        query (str): The search query to execute
        max_results (int, optional): Maximum number of results to return. Defaults to 3.
        fetch_full_page (bool, optional): Whether to fetch full page content from result URLs.
                                         Defaults to False.
    Returns:
        Dict[str, List[Dict[str, Any]]]: Search response containing:
            - results (list): List of search result dictionaries, each containing:
                - title (str): Title of the search result
                - url (str): URL of the search result
                - content (str): Snippet/summary of the content
                - raw_content (str or None): Full page content if fetch_full_page is True,
                                            otherwise same as content
    """
    try:
        from urllib.request import getproxies
        with DDGS(proxy=getproxies().get("https"), timeout=15) as ddgs:
            results = []
            search_results = list(ddgs.text(query, max_results=max_results, backend="duckduckgo,brave"))

            for r in search_results:
                url = r.get("href")
                title = r.get("title")
                content = r.get("body")

                if not all([url, title, content]):
                    print(f"Warning: Incomplete result from DuckDuckGo: {r}")
                    continue

                raw_content = content
                if fetch_full_page:
                    raw_content = fetch_raw_content(url)

                # Add result to list
                result = {
                    "title": title,
                    "url": url,
                    "content": content,
                    "raw_content": raw_content,
                }
                results.append(result)

            return {"results": results}
    except Exception as e:
        print(f"Error in DuckDuckGo search: {str(e)}")
        print(f"Full error details: {type(e).__name__}")
        return {"results": [], "error": f"{type(e).__name__}: {e}"}


@traceable
def searxng_search(
    query: str, max_results: int = 3, fetch_full_page: bool = False
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search the web using SearXNG and return formatted results.

    Uses the SearxSearchWrapper to perform searches through a SearXNG instance.
    The SearXNG host URL is read from the SEARXNG_URL environment variable
    or defaults to http://localhost:8888.

    Args:
        query (str): The search query to execute
        max_results (int, optional): Maximum number of results to return. Defaults to 3.
        fetch_full_page (bool, optional): Whether to fetch full page content from result URLs.
                                         Defaults to False.

    Returns:
        Dict[str, List[Dict[str, Any]]]: Search response containing:
            - results (list): List of search result dictionaries, each containing:
                - title (str): Title of the search result
                - url (str): URL of the search result
                - content (str): Snippet/summary of the content
                - raw_content (str or None): Full page content if fetch_full_page is True,
                                           otherwise same as content
    """
    host = os.environ.get("SEARXNG_URL", "http://localhost:8888")
    s = SearxSearchWrapper(searx_host=host)

    results = []
    search_results = s.results(query, num_results=max_results)
    for r in search_results:
        url = r.get("link")
        title = r.get("title")
        content = r.get("snippet")

        if not all([url, title, content]):
            print(f"Warning: Incomplete result from SearXNG: {r}")
            continue

        raw_content = content
        if fetch_full_page:
            raw_content = fetch_raw_content(url)

        # Add result to list
        result = {
            "title": title,
            "url": url,
            "content": content,
            "raw_content": raw_content,
        }
        results.append(result)
    return {"results": results}


@traceable
def tavily_search(
    query: str, fetch_full_page: bool = True, max_results: int = 3
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search the web using the Tavily API and return formatted results.

    Uses the TavilyClient to perform searches. Tavily API key must be configured
    in the environment.

    Args:
        query (str): The search query to execute
        fetch_full_page (bool, optional): Whether to include raw content from sources.
                                         Defaults to True.
        max_results (int, optional): Maximum number of results to return. Defaults to 3.

    Returns:
        Dict[str, List[Dict[str, Any]]]: Search response containing:
            - results (list): List of search result dictionaries, each containing:
                - title (str): Title of the search result
                - url (str): URL of the search result
                - content (str): Snippet/summary of the content
                - raw_content (str or None): Full content of the page if available and
                                            fetch_full_page is True
    """

    tavily_client = TavilyClient()
    return tavily_client.search(
        query, max_results=max_results, include_raw_content=fetch_full_page
    )


@traceable
def perplexity_search(
    query: str, perplexity_search_loop_count: int = 0
) -> Dict[str, Any]:
    """
    Search the web using the Perplexity API and return formatted results.

    Uses the Perplexity API to perform searches with the 'sonar-pro' model.
    Requires a PERPLEXITY_API_KEY environment variable to be set.

    Args:
        query (str): The search query to execute
        perplexity_search_loop_count (int, optional): The loop step for perplexity search
                                                     (used for source labeling). Defaults to 0.

    Returns:
        Dict[str, Any]: Search response containing:
            - results (list): List of search result dictionaries, each containing:
                - title (str): Title of the search result (includes search counter)
                - url (str): URL of the citation source
                - content (str): Content of the response or reference to main content
                - raw_content (str or None): Full content for the first source, None for additional
                                            citation sources

    Raises:
        requests.exceptions.HTTPError: If the API request fails
    """

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "Authorization": f"Bearer {os.getenv('PERPLEXITY_API_KEY')}",
    }

    payload = {
        "model": "sonar-pro",
        "messages": [
            {
                "role": "system",
                "content": "Search the web and provide factual information with sources.",
            },
            {"role": "user", "content": query},
        ],
    }

    response = requests.post(
        "https://api.perplexity.ai/chat/completions", headers=headers, json=payload
    )
    response.raise_for_status()  # Raise exception for bad status codes

    # Parse the response
    data = response.json()
    content = data["choices"][0]["message"]["content"]

    # Perplexity returns a list of citations for a single search result
    citations = data.get("citations", ["https://perplexity.ai"])

    # Return first citation with full content, others just as references
    results = [
        {
            "title": f"Perplexity Search {perplexity_search_loop_count + 1}, Source 1",
            "url": citations[0],
            "content": content,
            "raw_content": content,
        }
    ]

    # Add additional citations without duplicating content
    for i, citation in enumerate(citations[1:], start=2):
        results.append(
            {
                "title": f"Perplexity Search {perplexity_search_loop_count + 1}, Source {i}",
                "url": citation,
                "content": "See above for full content",
                "raw_content": None,
            }
        )

    return {"results": results}
