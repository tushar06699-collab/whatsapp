import logging
import os
import threading

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

VERIFY_TOKEN = "school_bot_verify"
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v20.0")
SCHOOL_IMAGE_URL = os.getenv("SCHOOL_IMAGE_URL", "").strip()
SERVICE_MENU_DELAY_SECONDS = float(os.getenv("SERVICE_MENU_DELAY_SECONDS", "3"))

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


SCHOOL_INTRO = (
    "\U0001f3eb Welcome to P.S. Public School\n\n"
    "P.S. Public School is committed to quality education, discipline, "
    "student safety, and all-round development. Our team focuses on building "
    "strong academic foundations along with confidence, values, and life skills."
)

SERVICES = {
    "admission_enquiry": {
        "title": "Admission Enquiry",
        "description": "Admission process and details",
        "reply": "Admission Enquiry\n\nAdmissions are open. Please call the school office for details.",
    },
    "fee_structure": {
        "title": "Fee Structure",
        "description": "Latest school fee information",
        "reply": "Fee Structure\n\nPlease contact the school office for the latest fee structure.",
    },
    "transport_facility": {
        "title": "Transport Facility",
        "description": "Bus routes and availability",
        "reply": "Transport Facility\n\nTransport facility is available on selected routes.",
    },
    "contact_school": {
        "title": "Contact School",
        "description": "Phone number and office contact",
        "reply": "Contact School\n\nContact: +91XXXXXXXXXX",
    },
    "other_services": {
        "title": "Other Services",
        "description": "Books, uniform, certificates, timing",
        "reply": (
            "Other Services\n\n"
            "For books, uniforms, certificates, school timings, or general support, "
            "please contact the school office."
        ),
    },
}

SERVICE_TITLE_TO_ID = {
    service["title"].lower(): service_id for service_id, service in SERVICES.items()
}


def normalize_message(message_text):
    return (message_text or "").strip().lower()


def send_whatsapp_payload(payload):
    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        logger.error("ACCESS_TOKEN and PHONE_NUMBER_ID must be set.")
        return False

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        response_text = getattr(exc.response, "text", "")
        logger.error("Failed to send WhatsApp message: %s %s", exc, response_text)
        return False

    return True


def send_text_message(to_phone_number, message_text):
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone_number,
        "type": "text",
        "text": {"preview_url": False, "body": message_text},
    }
    return send_whatsapp_payload(payload)


def send_image_message(to_phone_number, image_url, caption):
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone_number,
        "type": "image",
        "image": {"link": image_url, "caption": caption},
    }
    return send_whatsapp_payload(payload)


def send_service_list_message(to_phone_number):
    rows = [
        {
            "id": service_id,
            "title": service["title"],
            "description": service["description"],
        }
        for service_id, service in SERVICES.items()
    ]
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone_number,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": "P.S. Public School"},
            "body": {
                "text": "Please tap below and select the service you need."
            },
            "footer": {"text": "We will guide you with the selected service."},
            "action": {
                "button": "View Services",
                "sections": [
                    {
                        "title": "School Services",
                        "rows": rows,
                    }
                ],
            },
        },
    }
    return send_whatsapp_payload(payload)


def get_school_image_url():
    if SCHOOL_IMAGE_URL:
        return SCHOOL_IMAGE_URL

    return url_for("static", filename="school.png", _external=True, _scheme="https")


def send_school_intro(to_phone_number):
    image_url = get_school_image_url()
    if image_url:
        return send_image_message(to_phone_number, image_url, SCHOOL_INTRO)

    logger.warning("SCHOOL_IMAGE_URL is not set. Sending school intro as text.")
    return send_text_message(to_phone_number, SCHOOL_INTRO)


def reply_to_user(to_phone_number, message_text):
    normalized_text = normalize_message(message_text)
    service_id = SERVICE_TITLE_TO_ID.get(normalized_text, normalized_text)

    if service_id in SERVICES:
        send_text_message(to_phone_number, SERVICES[service_id]["reply"])
        return

    send_school_intro(to_phone_number)
    if SERVICE_MENU_DELAY_SECONDS > 0:
        timer = threading.Timer(
            SERVICE_MENU_DELAY_SECONDS,
            send_service_list_message,
            args=[to_phone_number],
        )
        timer.daemon = True
        timer.start()
        return

    send_service_list_message(to_phone_number)


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
                elif message_type == "interactive":
                    interactive = message.get("interactive", {})
                    if interactive.get("type") == "list_reply":
                        list_reply = interactive.get("list_reply", {})
                        incoming_text = list_reply.get("id") or list_reply.get("title", "")

                reply_to_user(sender, incoming_text)

    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
