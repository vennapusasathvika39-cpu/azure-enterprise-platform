
import os
import uuid

import psycopg
from psycopg.rows import dict_row

from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient


# --------------------------------------------------
# Flask application
# --------------------------------------------------

app = Flask(__name__)


# --------------------------------------------------
# Azure Blob Storage configuration
# --------------------------------------------------

STORAGE_ACCOUNT_NAME = "storderuat2026xyz"
CONTAINER_NAME = "order-data"

credential = DefaultAzureCredential()

blob_service_client = BlobServiceClient(
    account_url=f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
    credential=credential
)


# --------------------------------------------------
# PostgreSQL database connection
# --------------------------------------------------

def get_db_connection():
    return psycopg.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "orderdb"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ["DB_PASSWORD"],
        sslmode="require",
        row_factory=dict_row
    )


# --------------------------------------------------
# Home / Health check
# --------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()

        return jsonify({
            "message": "Order and Telemetry API",
            "status": "running",
            "database": "connected"
        }), 200

    except psycopg.Error:
        app.logger.exception("Database health check failed")

        return jsonify({
            "message": "Order and Telemetry API",
            "status": "running",
            "database": "disconnected"
        }), 503


# --------------------------------------------------
# Create Order
# --------------------------------------------------

@app.route("/orders", methods=["POST"])
def create_order():
    data = request.get_json(silent=True) or {}

    customer_name = data.get("customer_name")
    product = data.get("product")
    quantity = data.get("quantity")

    if not customer_name or not product or quantity is None:
        return jsonify({
            "error": "customer_name, product and quantity are required"
        }), 400

    try:
        quantity = int(quantity)

        if quantity <= 0:
            raise ValueError()

    except (ValueError, TypeError):
        return jsonify({
            "error": "quantity must be a positive integer"
        }), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO orders
                    (customer_name, product_name, quantity)
                    VALUES (%s, %s, %s)
                    RETURNING id, customer_name, product_name,
                              quantity, order_status, created_at
                    """,
                    (customer_name, product, quantity)
                )

                order = cur.fetchone()

        return jsonify({
            "order_id": order["id"],
            "customer_name": order["customer_name"],
            "product": order["product_name"],
            "quantity": order["quantity"],
            "status": order["order_status"],
            "created_at": order["created_at"].isoformat()
        }), 201

    except psycopg.Error:
        app.logger.exception("Database error while creating order")

        return jsonify({
            "error": "Could not save order"
        }), 500


# --------------------------------------------------
# Get Orders
# --------------------------------------------------

@app.route("/orders", methods=["GET"])
def get_orders():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, customer_name, product_name,
                           quantity, order_status, created_at
                    FROM orders
                    ORDER BY id DESC
                    """
                )

                rows = cur.fetchall()

        orders = [{
            "order_id": row["id"],
            "customer_name": row["customer_name"],
            "product": row["product_name"],
            "quantity": row["quantity"],
            "status": row["order_status"],
            "created_at": row["created_at"].isoformat()
        } for row in rows]

        return jsonify(orders), 200

    except psycopg.Error:
        app.logger.exception("Database error while retrieving orders")

        return jsonify({
            "error": "Could not retrieve orders"
        }), 500


# --------------------------------------------------
# Receive Telemetry
# --------------------------------------------------

@app.route("/telemetry", methods=["POST"])
def receive_telemetry():
    data = request.get_json(silent=True) or {}

    device_id = data.get("device_id")
    activity = data.get("activity")
    sensor_value = data.get("sensor_value")

    if not device_id:
        return jsonify({
            "error": "device_id is required"
        }), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO telemetry
                    (device_id, activity, sensor_value)
                    VALUES (%s, %s, %s)
                    RETURNING id, device_id, activity,
                              sensor_value, recorded_at
                    """,
                    (device_id, activity, sensor_value)
                )

                record = cur.fetchone()

        return jsonify({
            "record_id": record["id"],
            "device_id": record["device_id"],
            "activity": record["activity"],
            "sensor_value": record["sensor_value"],
            "timestamp": record["recorded_at"].isoformat()
        }), 201

    except psycopg.Error:
        app.logger.exception("Database error while saving telemetry")

        return jsonify({
            "error": "Could not save telemetry"
        }), 500


# --------------------------------------------------
# Get Telemetry
# --------------------------------------------------

@app.route("/telemetry", methods=["GET"])
def get_telemetry():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, device_id, activity,
                           sensor_value, recorded_at
                    FROM telemetry
                    ORDER BY id DESC
                    """
                )

                rows = cur.fetchall()

        records = [{
            "record_id": row["id"],
            "device_id": row["device_id"],
            "activity": row["activity"],
            "sensor_value": row["sensor_value"],
            "timestamp": row["recorded_at"].isoformat()
        } for row in rows]

        return jsonify(records), 200

    except psycopg.Error:
        app.logger.exception("Database error while retrieving telemetry")

        return jsonify({
            "error": "Could not retrieve telemetry"
        }), 500


# --------------------------------------------------
# Upload File to Azure Blob Storage
# --------------------------------------------------

@app.route("/upload", methods=["POST"])
def upload_file():

    if "file" not in request.files:
        return jsonify({
            "error": "No file provided"
        }), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify({
            "error": "No file selected"
        }), 400

    filename = secure_filename(file.filename)

    if not filename:
        return jsonify({
            "error": "Invalid filename"
        }), 400

    blob_name = f"{uuid.uuid4()}-{filename}"

    try:
        blob_client = blob_service_client.get_blob_client(
            container=CONTAINER_NAME,
            blob=blob_name
        )

        blob_client.upload_blob(
            file,
            overwrite=False
        )

        return jsonify({
            "message": "File uploaded successfully",
            "container": CONTAINER_NAME,
            "blob_name": blob_name
        }), 201

    except Exception:
        app.logger.exception("Blob upload failed")

        return jsonify({
            "error": "File upload failed"
        }), 500


# --------------------------------------------------
# Run application locally
# --------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )


