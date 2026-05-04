from src.path_utils import join_parts

def test_join_parts():
    assert join_parts('a', 'b') == 'a/b'
