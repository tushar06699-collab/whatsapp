import logging
import os

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

VERIFY_TOKEN = "school_bot_verify"
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v20.0")

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


MAIN_MENU = (
    "🏫 Welcome to P.S. Public School\n\n"
    "Please choose an option:\n\n"
    "1️⃣ Admission Enquiry\n"
    "2️⃣ Fee Structure\n"
    "3️⃣ Transport Facility\n"
    "4️⃣ Contact School"
)

MENU_REPLIES = {
    "1": "Admissions are open. Please call the school office for details.",
    "2": "Please contact the school office for the latest fee structure.",
    "3": "Transport facility is available on selected routes.",
    "4": "Contact: +91XXXXXXXXXX",
}


def get_reply(message_text):
    normalized_text = (message_text or "").strip()
    return MENU_REPLIES.get(normalized_text, MAIN_MENU)


def send_whatsapp_message(to_phone_number, message_text):
    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        logger.error("ACCESS_TOKEN and PHONE_NUMBER_ID must be set.")
        return False

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone_number,
        "type": "text",
        "text": {"preview_url": False, "body": message_text},
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        response_text = getattr(exc.response, "text", "")
        logger.error("Failed to send WhatsApp message: %s %s", exc, response_text)
        return False

    return True


@app.get("/")
def health_check():
    return jsonify({"status": "ok", "service": "whatsapp-auto-reply-bot"})


@app.get("/webhook")
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully.")
        return challenge or "", 200

    logger.warning("Webhook verification failed.")
    return "Forbidden", 403


@app.post("/webhook")
def receive_webhook():
    data = request.get_json(silent=True) or {}
    logger.info("Incoming webhook received.")

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])

            for message in messages:
                sender = message.get("from")
                message_type = message.get("type")

                if not sender:
                    continue

                incoming_text = ""
                if message_type == "text":
                    incoming_text = message.get("text", {}).get("body", "")

                reply_text = get_reply(incoming_text)
                send_whatsapp_message(sender, reply_text)

    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
