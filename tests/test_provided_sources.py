import pytest
from ollama_deep_researcher.utils import fetch_provided_sources

@pytest.mark.parametrize('url',['file:///C:/private.txt','http://localhost:1235','https://127.0.0.1/private'])
def test_source_mode_rejects_local_or_non_https_inputs(url):
    with pytest.raises(ValueError):fetch_provided_sources([url])
