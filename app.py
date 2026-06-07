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
ADMISSION_FORM_PDF_URL = os.getenv("ADMISSION_FORM_PDF_URL", "").strip()
ONLINE_ADMISSION_FORM_URL = os.getenv(
    "ONLINE_ADMISSION_FORM_URL",
    "https://pspublicschool.com",
).strip()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory language preference. For Render's normal single web instance this is enough.
# For multiple workers/instances, move this to a small database or Redis.
LANGUAGE_BY_USER = {}

LANGUAGE_LABELS = {
    "en": "English",
    "hi": "Hindi",
}

SCHOOL_INTRO = {
    "en": (
        "Welcome to P.S. Public School\n\n"
        "P.S. Public School is committed to quality education, discipline, "
        "student safety, and all-round development. Our team focuses on building "
        "strong academic foundations along with confidence, values, and life skills."
    ),
    "hi": (
        "पी.एस. पब्लिक स्कूल में आपका स्वागत है\n\n"
        "पी.एस. पब्लिक स्कूल गुणवत्तापूर्ण शिक्षा, अनुशासन, बच्चों की सुरक्षा "
        "और सर्वांगीण विकास के लिए प्रतिबद्ध है। हमारा उद्देश्य विद्यार्थियों "
        "को मजबूत शिक्षा, अच्छे संस्कार, आत्मविश्वास और जीवन कौशल देना है।"
    ),
}

SERVICES = {
    "admission_enquiry": {
        "title": {"en": "Admission Enquiry", "hi": "प्रवेश जानकारी"},
        "description": {
            "en": "Admission process and details",
            "hi": "प्रवेश प्रक्रिया और जानकारी",
        },
        "reply": {
            "en": "Admission Enquiry",
            "hi": "प्रवेश जानकारी",
        },
    },
    "fee_structure": {
        "title": {"en": "Fee Structure", "hi": "फीस जानकारी"},
        "description": {
            "en": "Latest school fee information",
            "hi": "वर्तमान फीस की जानकारी",
        },
        "reply": {
            "en": "Fee Structure",
            "hi": "फीस जानकारी",
        },
    },
    "transport_facility": {
        "title": {"en": "Transport Facility", "hi": "परिवहन सुविधा"},
        "description": {
            "en": "Bus routes and availability",
            "hi": "बस रूट और उपलब्धता",
        },
        "reply": {
            "en": "Transport Facility\n\nTransport facility is available on selected routes.",
            "hi": "परिवहन सुविधा\n\nचयनित रूटों पर स्कूल परिवहन सुविधा उपलब्ध है।",
        },
    },
    "contact_school": {
        "title": {"en": "Contact School", "hi": "स्कूल संपर्क"},
        "description": {
            "en": "Phone number and office contact",
            "hi": "फोन और कार्यालय संपर्क",
        },
        "reply": {
            "en": (
                "Contact School\n\n"
                "Call: +91 94162 93661\n"
                "WhatsApp: +91 94168 38604\n"
                "Email: psbhurri@gmail.com\n"
                "Website: pspublicschool.com"
            ),
            "hi": (
                "स्कूल संपर्क\n\n"
                "फोन: +91 94162 93661\n"
                "WhatsApp: +91 94168 38604\n"
                "ईमेल: psbhurri@gmail.com\n"
                "वेबसाइट: pspublicschool.com"
            ),
        },
    },
    "other_services": {
        "title": {"en": "Other Services", "hi": "अन्य सेवाएं"},
        "description": {
            "en": "Books, uniform, certificates, timing",
            "hi": "किताबें, यूनिफॉर्म, प्रमाण पत्र",
        },
        "reply": {
            "en": (
                "Other Services\n\n"
                "For books, uniforms, certificates, school timings, or general support, "
                "please contact the school office."
            ),
            "hi": (
                "अन्य सेवाएं\n\n"
                "किताबें, यूनिफॉर्म, प्रमाण पत्र, स्कूल समय या सामान्य सहायता के लिए "
                "कृपया स्कूल कार्यालय से संपर्क करें।"
            ),
        },
    },
    "change_language": {
        "title": {"en": "Change Language", "hi": "भाषा बदलें"},
        "description": {
            "en": "Switch between English and Hindi",
            "hi": "English या Hindi चुनें",
        },
        "reply": {
            "en": "Change Language",
            "hi": "भाषा बदलें",
        },
    },
}

ACTION_REPLIES = {
    "fill_admission_form": {
        "en": (
            "Online Admission Form\n\n"
            f"Please fill the admission form here:\n{ONLINE_ADMISSION_FORM_URL}\n\n"
            "After submitting, keep the required documents ready for verification at the school office."
        ),
        "hi": (
            "ऑनलाइन प्रवेश फॉर्म\n\n"
            f"कृपया प्रवेश फॉर्म यहां भरें:\n{ONLINE_ADMISSION_FORM_URL}\n\n"
            "फॉर्म जमा करने के बाद सत्यापन के लिए जरूरी दस्तावेज स्कूल कार्यालय में लेकर आएं।"
        ),
    },
    "admission_contact": {
        "en": (
            "Admission Help Desk\n\n"
            "Call: +91 94162 93661\n"
            "WhatsApp: +91 94168 38604\n"
            "Email: psbhurri@gmail.com\n"
            "Website: pspublicschool.com"
        ),
        "hi": (
            "प्रवेश सहायता\n\n"
            "फोन: +91 94162 93661\n"
            "WhatsApp: +91 94168 38604\n"
            "ईमेल: psbhurri@gmail.com\n"
            "वेबसाइट: pspublicschool.com"
        ),
    },
}

SCHOOL_HIGHLIGHTS_MESSAGE = {
    "en": (
        "Admission Enquiry - P.S. Public School\n\n"
        "Why choose our school?\n"
        "- Quality education with strong academic focus.\n"
        "- Safe, disciplined, and student-friendly environment.\n"
        "- Holistic development through activities, values, and confidence building.\n"
        "- Experienced staff and personal attention for students.\n"
        "- Transport facility available on selected routes.\n"
        "- Regular communication with parents for student progress.\n\n"
        "Contact Details\n"
        "Call: +91 94162 93661\n"
        "WhatsApp: +91 94168 38604\n"
        "Email: psbhurri@gmail.com\n"
        "Website: pspublicschool.com"
    ),
    "hi": (
        "प्रवेश जानकारी - पी.एस. पब्लिक स्कूल\n\n"
        "हमारे स्कूल की विशेषताएं:\n"
        "- मजबूत शैक्षणिक आधार के साथ गुणवत्तापूर्ण शिक्षा।\n"
        "- सुरक्षित, अनुशासित और बच्चों के अनुकूल वातावरण।\n"
        "- गतिविधियों, संस्कारों और आत्मविश्वास के साथ सर्वांगीण विकास।\n"
        "- अनुभवी शिक्षक और विद्यार्थियों पर व्यक्तिगत ध्यान।\n"
        "- चयनित रूटों पर परिवहन सुविधा।\n"
        "- विद्यार्थियों की प्रगति के लिए अभिभावकों से नियमित संपर्क।\n\n"
        "संपर्क जानकारी\n"
        "फोन: +91 94162 93661\n"
        "WhatsApp: +91 94168 38604\n"
        "ईमेल: psbhurri@gmail.com\n"
        "वेबसाइट: pspublicschool.com"
    ),
}

ADMISSION_REQUIREMENTS_MESSAGE = {
    "en": (
        "What to bring for admission\n\n"
        "Please keep these documents ready:\n"
        "- Filled admission form.\n"
        "- Student birth certificate.\n"
        "- Student Aadhaar card, if available.\n"
        "- Parent/guardian Aadhaar or ID proof.\n"
        "- Address proof.\n"
        "- Previous class report card, if applicable.\n"
        "- Transfer certificate, if applicable.\n"
        "- Recent passport-size photographs of the student.\n\n"
        "Admission Process\n"
        "1. Fill the admission form online or offline.\n"
        "2. Submit required documents for verification.\n"
        "3. Visit the school office for confirmation and fee guidance.\n"
        "4. Complete admission formalities and collect joining details."
    ),
    "hi": (
        "प्रवेश के लिए क्या लेकर आएं\n\n"
        "कृपया ये दस्तावेज तैयार रखें:\n"
        "- भरा हुआ प्रवेश फॉर्म।\n"
        "- विद्यार्थी का जन्म प्रमाण पत्र।\n"
        "- विद्यार्थी का आधार कार्ड, यदि उपलब्ध हो।\n"
        "- माता-पिता/अभिभावक का आधार या पहचान पत्र।\n"
        "- पते का प्रमाण।\n"
        "- पिछली कक्षा की मार्कशीट, यदि लागू हो।\n"
        "- ट्रांसफर सर्टिफिकेट, यदि लागू हो।\n"
        "- विद्यार्थी की हाल की पासपोर्ट साइज फोटो।\n\n"
        "प्रवेश प्रक्रिया\n"
        "1. प्रवेश फॉर्म ऑनलाइन या ऑफलाइन भरें।\n"
        "2. जरूरी दस्तावेज सत्यापन के लिए जमा करें।\n"
        "3. पुष्टि और फीस जानकारी के लिए स्कूल कार्यालय आएं।\n"
        "4. प्रवेश प्रक्रिया पूरी करें और जॉइनिंग जानकारी प्राप्त करें।"
    ),
}

FEE_OVERVIEW_MESSAGE = {
    "en": (
        "Fee Structure - Session 2026-2027\n\n"
        "P.S. Public School, Ganaur Road Bhurri (Sonipat), provides a disciplined "
        "and supportive academic environment from foundational classes to senior "
        "secondary streams. The school focuses on strong classroom learning, "
        "regular academic monitoring, value-based education, co-curricular "
        "activities, and parent communication.\n\n"
        "The fee details below are shared class-wise for parent convenience. "
        "For final confirmation, fee deposit dates, concessions if any, or account "
        "support, please contact the school office."
    ),
    "hi": (
        "फीस जानकारी - सत्र 2026-2027\n\n"
        "पी.एस. पब्लिक स्कूल, गन्नौर रोड भूरी (सोनीपत), बच्चों को अनुशासित और "
        "सहयोगी शैक्षणिक वातावरण प्रदान करता है। स्कूल में मजबूत कक्षा शिक्षण, "
        "नियमित पढ़ाई की निगरानी, संस्कार आधारित शिक्षा, गतिविधियां और "
        "अभिभावकों से संपर्क पर विशेष ध्यान दिया जाता है।\n\n"
        "नीचे अभिभावकों की सुविधा के लिए कक्षा अनुसार फीस दी गई है। अंतिम पुष्टि, "
        "फीस जमा तिथि, किसी भी छूट या अकाउंट सहायता के लिए कृपया स्कूल कार्यालय "
        "से संपर्क करें।"
    ),
}

FEE_STRUCTURE_MESSAGE = {
    "en": (
        "Class-wise Fee Structure\n"
        "Session: 2026-2027\n\n"
        "Fresh Admission Fee, Old Admission Fee, and Annual Charge are shown as "
        "`-` where no amount is mentioned in the provided fee sheet.\n\n"
        "Pre-Primary & Primary\n"
        "```text\n"
        "Cls  Fr  Old Ann Tuit Reg ID\n"
        "NUR  -   -   -   1100 500 100\n"
        "LKG  -   -   -   1200 500 100\n"
        "UKG  -   -   -   1200 500 100\n"
        "1    -   -   -   1200 500 100\n"
        "2    -   -   -   1200 500 100\n"
        "3    -   -   -   1200 500 100\n"
        "4    -   -   -   1300 500 100\n"
        "5    -   -   -   1300 500 100\n"
        "```\n\n"
        "Middle & Secondary\n"
        "```text\n"
        "Cls  Fr  Old Ann Tuit Reg ID\n"
        "6    -   -   -   1400 500 100\n"
        "7    -   -   -   1400 500 100\n"
        "8    -   -   -   1600 500 100\n"
        "9    -   -   -   1800 500 100\n"
        "10   -   -   -   1800 500 100\n"
        "```\n\n"
        "Senior Secondary\n"
        "```text\n"
        "Cls/Stream Fr Old Ann Tuit Reg ID\n"
        "11 Med     -  -   -   2100 500 100\n"
        "11 Comm    -  -   -   2000 500 100\n"
        "11 Arts    -  -   -   2000 500 100\n"
        "12 Med     -  -   -   2100 500 100\n"
        "12 Comm    -  -   -   2000 500 100\n"
        "12 Arts    -  -   -   2000 500 100\n"
        "```\n\n"
        "Column Guide: Fr=Fresh Admission Fee, Old=Old Admission Fee, "
        "Ann=Annual Charge, Tuit=Tuition Fee, Reg=Registration Fee, ID=I-Card Fee.\n\n"
        "Additional Charges\n"
        "- Exam Fee: Rs. 350\n"
        "- Late Fee Charge: Rs. 50\n\n"
        "For payment confirmation, receipt, or any fee-related query:\n"
        "Call: +91 94162 93661\n"
        "WhatsApp: +91 94168 38604"
    ),
    "hi": (
        "कक्षा अनुसार फीस संरचना\n"
        "सत्र: 2026-2027\n\n"
        "Fresh Admission Fee, Old Admission Fee और Annual Charge में जहां राशि "
        "नहीं दी गई है, वहां `-` लिखा गया है।\n\n"
        "Pre-Primary और Primary\n"
        "```text\n"
        "Cls  Fr  Old Ann Tuit Reg ID\n"
        "NUR  -   -   -   1100 500 100\n"
        "LKG  -   -   -   1200 500 100\n"
        "UKG  -   -   -   1200 500 100\n"
        "1    -   -   -   1200 500 100\n"
        "2    -   -   -   1200 500 100\n"
        "3    -   -   -   1200 500 100\n"
        "4    -   -   -   1300 500 100\n"
        "5    -   -   -   1300 500 100\n"
        "```\n\n"
        "Middle और Secondary\n"
        "```text\n"
        "Cls  Fr  Old Ann Tuit Reg ID\n"
        "6    -   -   -   1400 500 100\n"
        "7    -   -   -   1400 500 100\n"
        "8    -   -   -   1600 500 100\n"
        "9    -   -   -   1800 500 100\n"
        "10   -   -   -   1800 500 100\n"
        "```\n\n"
        "Senior Secondary\n"
        "```text\n"
        "Cls/Stream Fr Old Ann Tuit Reg ID\n"
        "11 Med     -  -   -   2100 500 100\n"
        "11 Comm    -  -   -   2000 500 100\n"
        "11 Arts    -  -   -   2000 500 100\n"
        "12 Med     -  -   -   2100 500 100\n"
        "12 Comm    -  -   -   2000 500 100\n"
        "12 Arts    -  -   -   2000 500 100\n"
        "```\n\n"
        "Column Guide: Fr=Fresh Admission Fee, Old=Old Admission Fee, "
        "Ann=Annual Charge, Tuit=Tuition Fee, Reg=Registration Fee, ID=I-Card Fee.\n\n"
        "अतिरिक्त शुल्क\n"
        "- परीक्षा शुल्क: Rs. 350\n"
        "- लेट फीस: Rs. 50\n\n"
        "फीस भुगतान, रसीद या किसी भी फीस संबंधी जानकारी के लिए:\n"
        "फोन: +91 94162 93661\n"
        "WhatsApp: +91 94168 38604"
    ),
}


def normalize_message(message_text):
    return (message_text or "").strip().lower()


def service_title_to_id(language):
    return {
        service["title"][language].lower(): service_id
        for service_id, service in SERVICES.items()
    }


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


def send_document_message(to_phone_number, document_url, filename, caption):
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone_number,
        "type": "document",
        "document": {
            "link": document_url,
            "filename": filename,
            "caption": caption,
        },
    }
    return send_whatsapp_payload(payload)


def send_language_buttons(to_phone_number):
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": (
                    "Please choose your preferred language.\n\n"
                    "कृपया अपनी भाषा चुनें।"
                )
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": "language_en", "title": "English"},
                    },
                    {
                        "type": "reply",
                        "reply": {"id": "language_hi", "title": "Hindi"},
                    },
                ]
            },
        },
    }
    return send_whatsapp_payload(payload)


def send_admission_action_buttons(to_phone_number, language):
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": {
                    "en": "Choose how you would like to continue with admission.",
                    "hi": "कृपया बताएं आप प्रवेश प्रक्रिया कैसे आगे बढ़ाना चाहते हैं।",
                }[language]
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "fill_admission_form",
                            "title": {"en": "Fill Form", "hi": "फॉर्म भरें"}[language],
                        },
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "admission_contact",
                            "title": {"en": "Contact Office", "hi": "संपर्क करें"}[language],
                        },
                    },
                ]
            },
        },
    }
    return send_whatsapp_payload(payload)


def run_later(delay_seconds, callback, *args):
    timer = threading.Timer(delay_seconds, callback, args=args)
    timer.daemon = True
    timer.start()
    return timer


def send_service_list_message(to_phone_number, language):
    rows = [
        {
            "id": service_id,
            "title": service["title"][language],
            "description": service["description"][language],
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
            "header": {
                "type": "text",
                "text": {"en": "P.S. Public School", "hi": "पी.एस. पब्लिक स्कूल"}[language],
            },
            "body": {
                "text": {
                    "en": "Please tap below and select the service you need.",
                    "hi": "कृपया नीचे टैप करके अपनी जरूरत की सेवा चुनें।",
                }[language]
            },
            "footer": {
                "text": {
                    "en": "We will guide you with the selected service.",
                    "hi": "चुनी हुई सेवा के अनुसार आपको जानकारी दी जाएगी।",
                }[language]
            },
            "action": {
                "button": {"en": "View Services", "hi": "सेवाएं देखें"}[language],
                "sections": [
                    {
                        "title": {"en": "School Services", "hi": "स्कूल सेवाएं"}[language],
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


def get_admission_form_pdf_url():
    if ADMISSION_FORM_PDF_URL:
        return ADMISSION_FORM_PDF_URL

    return url_for(
        "static",
        filename="admission-form-final.pdf",
        _external=True,
        _scheme="https",
    )


def send_school_intro(to_phone_number, language):
    image_url = get_school_image_url()
    if image_url:
        return send_image_message(to_phone_number, image_url, SCHOOL_INTRO[language])

    logger.warning("SCHOOL_IMAGE_URL is not set. Sending school intro as text.")
    return send_text_message(to_phone_number, SCHOOL_INTRO[language])


def send_intro_and_services(to_phone_number, language):
    send_school_intro(to_phone_number, language)
    if SERVICE_MENU_DELAY_SECONDS > 0:
        run_later(
            SERVICE_MENU_DELAY_SECONDS,
            send_service_list_message,
            to_phone_number,
            language,
        )
        return

    send_service_list_message(to_phone_number, language)


def send_admission_enquiry_flow(to_phone_number, language):
    send_text_message(to_phone_number, SCHOOL_HIGHLIGHTS_MESSAGE[language])
    run_later(
        1.5,
        send_document_message,
        to_phone_number,
        get_admission_form_pdf_url(),
        "P.S. Public School Admission Form.pdf",
        {
            "en": "Admission Form - P.S. Public School",
            "hi": "प्रवेश फॉर्म - पी.एस. पब्लिक स्कूल",
        }[language],
    )
    run_later(3, send_text_message, to_phone_number, ADMISSION_REQUIREMENTS_MESSAGE[language])
    run_later(4.5, send_admission_action_buttons, to_phone_number, language)


def send_fee_structure_flow(to_phone_number, language):
    send_text_message(to_phone_number, FEE_OVERVIEW_MESSAGE[language])
    run_later(1.5, send_text_message, to_phone_number, FEE_STRUCTURE_MESSAGE[language])


def set_language_and_start(to_phone_number, language):
    LANGUAGE_BY_USER[to_phone_number] = language
    confirmation = {
        "en": "Language selected: English",
        "hi": "भाषा चुनी गई: हिन्दी",
    }[language]
    send_text_message(to_phone_number, confirmation)
    send_intro_and_services(to_phone_number, language)


def reply_to_user(to_phone_number, message_text):
    normalized_text = normalize_message(message_text)

    if normalized_text in {"language_en", "english"}:
        set_language_and_start(to_phone_number, "en")
        return

    if normalized_text in {"language_hi", "hindi", "हिंदी", "हिन्दी"}:
        set_language_and_start(to_phone_number, "hi")
        return

    language = LANGUAGE_BY_USER.get(to_phone_number)
    if not language:
        send_language_buttons(to_phone_number)
        return

    service_id = service_title_to_id(language).get(normalized_text, normalized_text)

    if service_id in ACTION_REPLIES:
        send_text_message(to_phone_number, ACTION_REPLIES[service_id][language])
        return

    if service_id == "admission_enquiry":
        send_admission_enquiry_flow(to_phone_number, language)
        return

    if service_id == "fee_structure":
        send_fee_structure_flow(to_phone_number, language)
        return

    if service_id == "change_language":
        send_language_buttons(to_phone_number)
        return

    if service_id in SERVICES:
        send_text_message(to_phone_number, SERVICES[service_id]["reply"][language])
        return

    send_intro_and_services(to_phone_number, language)


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
                    elif interactive.get("type") == "button_reply":
                        button_reply = interactive.get("button_reply", {})
                        incoming_text = button_reply.get("id") or button_reply.get("title", "")

                reply_to_user(sender, incoming_text)

    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
