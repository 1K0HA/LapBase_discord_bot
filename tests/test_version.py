from app.version import get_version


def test_version_comes_from_pyproject():
    assert get_version() == "1.0.28"
