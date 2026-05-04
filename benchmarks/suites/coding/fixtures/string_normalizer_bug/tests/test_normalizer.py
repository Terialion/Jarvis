from src.normalizer import normalize

def test_normalize():
    assert normalize("  HeLLo  ") == "hello"
