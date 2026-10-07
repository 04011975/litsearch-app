from app.main import APP_VERSION, app


def test_application_version_matches_release():
    assert APP_VERSION == "0.6.0"
    assert app.version == APP_VERSION
