"""conftest - loaded automatically by the pytest runner"""

from unittest.mock import MagicMock

from google.cloud import ndb
from google.cloud.ndb import _datastore_api
from InMemoryCloudDatastoreStub.datastore_stub import LocalDatastoreStub
import pytest
from _pytest.monkeypatch import MonkeyPatch


@pytest.fixture(autouse=True)
def ndb_stub(monkeypatch: MonkeyPatch) -> LocalDatastoreStub:
    stub = LocalDatastoreStub()
    monkeypatch.setattr(_datastore_api, "stub", MagicMock(return_value=stub))
    return stub


@pytest.fixture(autouse=True)
def ndb_context(init_ndb_env_vars):
    client = ndb.Client()
    with client.context() as context:
        yield context


@pytest.fixture(autouse=True)
def init_ndb_env_vars(monkeypatch: MonkeyPatch) -> None:
    """
    Initializing an ndb Client in a test env requires some environment variables to be set
    For now, these are just garbage values intended to give the library _something_
    (we don't expect them to actually work yet)
    """
    monkeypatch.setenv("DATASTORE_EMULATOR_HOST", "localhost")
    monkeypatch.setenv("DATASTORE_DATASET", "datastore-stub-test")


# @pytest.fixture
# def snippets_app():
#     app = snippets.app
#     # any setup stuff can go here, e.g.
#     # app.config.update({
#     #     "TESTING": True,
#     # })
#     yield app
#     # cleanup / reset resources here
#
#
# @pytest.fixture
# def snippets_client(snippets_app):
#     return snippets_app.test_client()
#
#
# @pytest.fixture
# def snippets_runner(snippets_app):
#     return snippets_app.test_cli_runner()
