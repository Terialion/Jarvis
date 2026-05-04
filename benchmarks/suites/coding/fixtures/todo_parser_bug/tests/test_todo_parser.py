from src.todo_parser import count_open

def test_count_open():
    lines = ['- [ ] a', '- [x] b', '- [ ] c']
    assert count_open(lines) == 2
