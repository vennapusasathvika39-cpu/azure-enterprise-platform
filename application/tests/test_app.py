

import sys
from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app


def test_home_endpoint(mocker):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mocker.patch("app.get_db_connection").return_value.__enter__.return_value = mock_conn

    client = app.test_client()
    response = client.get("/")

    assert response.status_code == 200
    assert response.get_json()["status"] == "running"
    assert response.get_json()["database"] == "connected"


def test_orders_endpoint(mocker):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_cursor.fetchall.return_value = [{
        "id": 1,
        "customer_name": "Test Customer",
        "product_name": "Test Product",
        "quantity": 2,
        "order_status": "pending",
        "created_at": datetime.now(timezone.utc)
    }]

    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mocker.patch("app.get_db_connection").return_value.__enter__.return_value = mock_conn

    client = app.test_client()
    response = client.get("/orders")

    assert response.status_code == 200
    assert len(response.get_json()) == 1
    assert response.get_json()[0]["customer_name"] == "Test Customer"


def test_telemetry_endpoint(mocker):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_cursor.fetchall.return_value = [{
        "id": 1,
        "device_id": "ESP32-DEV-01",
        "activity": "walking",
        "sensor_value": 12.5,
        "recorded_at": datetime.now(timezone.utc)
    }]

    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mocker.patch("app.get_db_connection").return_value.__enter__.return_value = mock_conn

    client = app.test_client()
    response = client.get("/telemetry")

    assert response.status_code == 200
    assert len(response.get_json()) == 1
    assert response.get_json()[0]["device_id"] == "ESP32-DEV-01"


def test_create_order_validation():
    client = app.test_client()

    response = client.post("/orders", json={
        "customer_name": "Test Customer",
        "product": "Test Product"
    })

    assert response.status_code == 400


def test_telemetry_validation():
    client = app.test_client()

    response = client.post("/telemetry", json={})

    assert response.status_code == 400
