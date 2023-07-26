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
    """Set environment variables for the test ndb client.

    Initializing an ndb Client in a test env requires some environment variables
    to be set. For now, these are just garbage values intended to give the
    library _something_ (we don't expect them to actually work yet)
    """
    monkeypatch.setenv("DATASTORE_EMULATOR_HOST", "localhost")
    monkeypatch.setenv("DATASTORE_DATASET", "datastore-stub-test")
