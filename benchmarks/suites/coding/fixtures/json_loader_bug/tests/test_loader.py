from src.loader import load_value

def test_load_value():
    assert load_value('{"a": 1}', 'a') == 1
