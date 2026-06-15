import os


DEFAULT_TEST_DATABASE_URL = 'sqlite:///:memory:'


def test_database_url():
    explicit = os.environ.get('TEST_DATABASE_URL')
    if explicit:
        return explicit
    if os.environ.get('APP_ENV') == 'test' and os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    return (
        DEFAULT_TEST_DATABASE_URL
    )


def configure_test_database(app):
    app.config['SQLALCHEMY_DATABASE_URI'] = test_database_url()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    return app
