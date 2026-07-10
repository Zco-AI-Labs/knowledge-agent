from unittest.mock import MagicMock, patch

from app.core import hubscape_adk


def test_adk_platform_scope_db_path():
    ctx = hubscape_adk.RemoteContext(
        user_id="user123",
        agent_id="custom-agent"
    )

    path = ctx.get_agent_db_path(scope="platform", collection_name="submissions", doc_id="doc456")
    assert path == "agents/custom-agent/agent_data/platform/submissions/doc456"

def test_adk_storage_paths():
    ctx = hubscape_adk.RemoteContext(
        user_id="user123",
        agent_id="custom-agent",
        hub_id="hub123",
        org_id="org123"
    )

    p_path = ctx.get_agent_storage_path(scope="platform", filename="img.png")
    assert p_path == "agents/custom-agent/platform/img.png"

    u_path = ctx.get_agent_storage_path(scope="user", filename="img.png")
    assert u_path == "agents/custom-agent/user/user123/img.png"

    h_path = ctx.get_agent_storage_path(scope="hub", filename="img.png")
    assert h_path == "agents/custom-agent/hub/hub123/img.png"

    o_path = ctx.get_agent_storage_path(scope="org", filename="img.png")
    assert o_path == "agents/custom-agent/org/org123/img.png"

@patch("google.cloud.storage.Client")
def test_adk_save_get_delete_file(mock_gcs_client):
    ctx = hubscape_adk.RemoteContext(
        user_id="user123",
        agent_id="custom-agent",
        project_id="test-project",
        raw_context={"storageBucket": "my-bucket"}
    )

    mock_client_inst = MagicMock()
    mock_gcs_client.return_value = mock_client_inst

    mock_bucket = MagicMock()
    mock_bucket.name = "my-bucket"
    mock_client_inst.bucket.return_value = mock_bucket

    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    # Save file
    res = ctx.save_file(scope="platform", filename="test.txt", content=b"hello world", content_type="text/plain")
    assert res["storage_path"] == "agents/custom-agent/platform/test.txt"
    assert "download_url" in res
    assert "alt=media" in res["download_url"]
    mock_bucket.blob.assert_called_with("agents/custom-agent/platform/test.txt")
    mock_blob.upload_from_string.assert_called_once_with(b"hello world", content_type="text/plain")

    # Get file
    mock_blob.exists.return_value = True
    mock_blob.download_as_bytes.return_value = b"hello world"
    file_bytes = ctx.get_file(scope="platform", filename="test.txt")
    assert file_bytes == b"hello world"
    mock_blob.download_as_bytes.assert_called_once()

    # Delete file
    ctx.delete_file(scope="platform", filename="test.txt")
    mock_blob.delete.assert_called_once()

def test_adk_db_crud_operations():
    ctx = hubscape_adk.RemoteContext(
        user_id="user123",
        agent_id="custom-agent",
        project_id="test-project"
    )

    mock_db = MagicMock()
    ctx._db = mock_db

    mock_doc_ref = MagicMock()
    mock_db.document.return_value = mock_doc_ref

    mock_snap = MagicMock()
    mock_snap.exists = False
    mock_doc_ref.get.return_value = mock_snap

    # Test save (create)
    data = {"name": "test"}
    res = ctx.save(scope="user", collection_name="todos", doc_id="123", data=data)
    assert res["name"] == "test"
    assert "created_at" in res
    assert res["version"] == 1
    mock_db.document.assert_called_with("platform_users/user123/agent_data/custom-agent/todos/123")
    mock_doc_ref.set.assert_called_once()

    # Test get
    mock_snap.exists = True
    mock_snap.to_dict.return_value = {"name": "test_existing", "version": 1}
    mock_snap.id = "123"
    doc = ctx.get(scope="user", collection_name="todos", doc_id="123")
    assert doc["name"] == "test_existing"
    assert doc["id"] == "123"

    # Test list
    mock_col_ref = MagicMock()
    mock_db.collection.return_value = mock_col_ref
    mock_doc1 = MagicMock()
    mock_doc1.to_dict.return_value = {"name": "t1"}
    mock_doc1.id = "doc1"
    mock_col_ref.stream.return_value = [mock_doc1]

    docs = ctx.list(scope="user", collection_name="todos")
    assert len(docs) == 1
    assert docs[0]["name"] == "t1"
    assert docs[0]["id"] == "doc1"
    mock_db.collection.assert_called_with("platform_users/user123/agent_data/custom-agent/todos")

    # Test delete
    ctx.delete(scope="user", collection_name="todos", doc_id="123")
    mock_doc_ref.delete.assert_called_once()
