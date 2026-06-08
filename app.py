import logging
import os
import re
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
EXAM_BACKEND_STUDENT_LOGIN_URL = os.getenv(
    "EXAM_BACKEND_STUDENT_LOGIN_URL",
    "https://exam-backend-117372286918.asia-south1.run.app/login",
).strip()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory language preference. For Render's normal single web instance this is enough.
# For multiple workers/instances, move this to a small database or Redis.
LANGUAGE_BY_USER = {}
STUDENT_DETAIL_SESSIONS = {}

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
            "en": "Transport Facility",
            "hi": "परिवहन सुविधा",
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

OTHER_SERVICE_CATEGORIES = {
    "academic_support": {
        "title": {"en": "Academic Support", "hi": "शैक्षणिक सहायता"},
        "description": {
            "en": "Classes, syllabus, homework support",
            "hi": "कक्षा, सिलेबस, होमवर्क",
        },
        "reply": {
            "en": (
                "Academic Support\n\n"
                "This service is currently unavailable on WhatsApp.\n\n"
                "For syllabus, homework, exam preparation, or teacher communication, "
                "please contact the school office."
            ),
            "hi": (
                "शैक्षणिक सहायता\n\n"
                "यह सेवा फिलहाल WhatsApp पर उपलब्ध नहीं है।\n\n"
                "सिलेबस, होमवर्क, परीक्षा तैयारी या शिक्षक से संपर्क के लिए कृपया "
                "स्कूल कार्यालय से संपर्क करें।"
            ),
        },
    },
    "student_details": {
        "title": {"en": "Student Details", "hi": "विद्यार्थी विवरण"},
        "description": {
            "en": "Update student or parent information",
            "hi": "विद्यार्थी/अभिभावक जानकारी",
        },
        "reply": {
            "en": (
                "Student Details\n\n"
                "For updating student name, class, section, address, parent mobile "
                "number, Aadhaar details, or emergency contact, please visit the "
                "school office with valid proof."
            ),
            "hi": (
                "विद्यार्थी विवरण\n\n"
                "विद्यार्थी का नाम, कक्षा, सेक्शन, पता, अभिभावक मोबाइल नंबर, आधार "
                "विवरण या इमरजेंसी संपर्क अपडेट कराने के लिए कृपया सही प्रमाण के "
                "साथ स्कूल कार्यालय में संपर्क करें।"
            ),
        },
    },
    "results_exams": {
        "title": {"en": "Results & Exams", "hi": "रिजल्ट व परीक्षा"},
        "description": {
            "en": "Exam schedule, marks, report card",
            "hi": "परीक्षा, अंक, रिपोर्ट कार्ड",
        },
        "reply": {
            "en": (
                "Results & Exams\n\n"
                "For exam dates, marks, report cards, rechecking guidance, or result "
                "collection, please contact the school office or concerned class teacher."
            ),
            "hi": (
                "रिजल्ट व परीक्षा\n\n"
                "परीक्षा तिथि, अंक, रिपोर्ट कार्ड, री-चेकिंग जानकारी या रिजल्ट "
                "लेने के लिए कृपया स्कूल कार्यालय या संबंधित कक्षा शिक्षक से संपर्क करें।"
            ),
        },
    },
    "certificates": {
        "title": {"en": "Certificates", "hi": "प्रमाण पत्र"},
        "description": {
            "en": "TC, bonafide, character certificate",
            "hi": "TC, बोनाफाइड, कैरेक्टर",
        },
        "reply": {
            "en": (
                "Certificates\n\n"
                "For transfer certificate, bonafide certificate, character certificate, "
                "or any school document, submit a written request at the school office. "
                "Processing time may depend on record verification."
            ),
            "hi": (
                "प्रमाण पत्र\n\n"
                "ट्रांसफर सर्टिफिकेट, बोनाफाइड, कैरेक्टर सर्टिफिकेट या किसी भी "
                "स्कूल दस्तावेज के लिए स्कूल कार्यालय में लिखित आवेदन दें। रिकॉर्ड "
                "सत्यापन के अनुसार समय लग सकता है।"
            ),
        },
    },
    "uniform_books": {
        "title": {"en": "Uniform & Books", "hi": "यूनिफॉर्म व किताबें"},
        "description": {
            "en": "Uniform, books, notebooks guidance",
            "hi": "यूनिफॉर्म, किताबें, कॉपी",
        },
        "reply": {
            "en": (
                "Uniform & Books\n\n"
                "For class-wise book list, notebooks, school uniform, tie, belt, ID "
                "card, or related guidance, please contact the school office."
            ),
            "hi": (
                "यूनिफॉर्म व किताबें\n\n"
                "कक्षा अनुसार किताबों की सूची, कॉपी, स्कूल यूनिफॉर्म, टाई, बेल्ट, "
                "आई-कार्ड या संबंधित जानकारी के लिए स्कूल कार्यालय से संपर्क करें।"
            ),
        },
    },
    "school_timing": {
        "title": {"en": "School Timing", "hi": "स्कूल समय"},
        "description": {
            "en": "School hours and office timing",
            "hi": "स्कूल और कार्यालय समय",
        },
        "reply": {
            "en": (
                "School Timing\n\n"
                "For current school timing, office hours, holiday updates, or special "
                "schedule changes, please contact the school office before visiting."
            ),
            "hi": (
                "स्कूल समय\n\n"
                "वर्तमान स्कूल समय, कार्यालय समय, छुट्टी अपडेट या विशेष समय बदलाव "
                "की जानकारी के लिए आने से पहले स्कूल कार्यालय से संपर्क करें।"
            ),
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

TRANSPORT_OVERVIEW_MESSAGE = {
    "en": (
        "Transport Facility - P.S. Public School\n\n"
        "P.S. Public School provides school transport on selected routes for the "
        "convenience and safety of students. The school bus facility is planned "
        "to support regular attendance, timely arrival, and comfortable travel "
        "for children.\n\n"
        "Key Points\n"
        "- School bus facility available on selected routes.\n"
        "- Students are picked and dropped at fixed points.\n"
        "- Parents should ensure students reach the stop on time.\n"
        "- Bus routes and seats are subject to availability.\n"
        "- Any route change should be confirmed with the school office first.\n"
        "- Monthly transport fee depends on route/location.\n\n"
        "For route confirmation:\n"
        "Call: +91 94162 93661\n"
        "WhatsApp: +91 94168 38604"
    ),
    "hi": (
        "परिवहन सुविधा - पी.एस. पब्लिक स्कूल\n\n"
        "पी.एस. पब्लिक स्कूल विद्यार्थियों की सुविधा और सुरक्षा के लिए चयनित "
        "रूटों पर स्कूल बस सुविधा उपलब्ध कराता है। यह सुविधा बच्चों की नियमित "
        "उपस्थिति, समय पर स्कूल पहुंचने और आरामदायक यात्रा में मदद करती है।\n\n"
        "मुख्य बातें\n"
        "- चयनित रूटों पर स्कूल बस सुविधा उपलब्ध है।\n"
        "- विद्यार्थियों को निर्धारित स्टॉप से पिक और ड्रॉप किया जाता है।\n"
        "- अभिभावक कृपया बच्चे को समय पर स्टॉप पर पहुंचाएं।\n"
        "- रूट और सीट उपलब्धता के अनुसार मिलेंगे।\n"
        "- रूट बदलने से पहले स्कूल कार्यालय से पुष्टि करें।\n"
        "- मासिक परिवहन शुल्क रूट/स्थान के अनुसार है।\n\n"
        "रूट की पुष्टि के लिए:\n"
        "फोन: +91 94162 93661\n"
        "WhatsApp: +91 94168 38604"
    ),
}

TRANSPORT_FEE_MESSAGE = {
    "en": (
        "Monthly Transport Fee\n\n"
        "```text\n"
        "Route / Area              Fee\n"
        "Rajpur, Kami, Garhi       Rs. 350\n"
        "Rajlu Garhi, Lalheri      Rs. 400\n"
        "Bhigan                    Rs. 400\n"
        "Sonipat, Ganaur           Rs. 500\n"
        "```\n\n"
        "Note: Transport facility is available only on selected routes. Final "
        "pickup point, timing, and seat availability should be confirmed from "
        "the school office."
    ),
    "hi": (
        "मासिक परिवहन शुल्क\n\n"
        "```text\n"
        "रूट / स्थान               शुल्क\n"
        "Rajpur, Kami, Garhi       Rs. 350\n"
        "Rajlu Garhi, Lalheri      Rs. 400\n"
        "Bhigan                    Rs. 400\n"
        "Sonipat, Ganaur           Rs. 500\n"
        "```\n\n"
        "नोट: परिवहन सुविधा केवल चयनित रूटों पर उपलब्ध है। अंतिम पिकअप पॉइंट, "
        "समय और सीट उपलब्धता की पुष्टि स्कूल कार्यालय से करें।"
    ),
}

STUDENT_LOGIN_TEXT = {
    "ask_username": {
        "en": (
            "Student Details Login\n\n"
            "Please send the student's admission number."
        ),
        "hi": (
            "विद्यार्थी विवरण लॉगिन\n\n"
            "कृपया विद्यार्थी का admission number भेजें।"
        ),
    },
    "ask_password": {
        "en": (
            "Now please send the student's DOB exactly as saved in the exam portal.\n\n"
            "You can send it as DD/MM/YYYY or DDMMYYYY.\n\n"
            "For privacy, this is used only for login verification and is not stored."
        ),
        "hi": (
            "अब कृपया विद्यार्थी की DOB भेजें, बिल्कुल वैसे ही जैसे exam portal में saved है।\n\n"
            "आप DOB को DD/MM/YYYY या DDMMYYYY format में भेज सकते हैं।\n\n"
            "गोपनीयता के लिए यह केवल login verification के लिए उपयोग होगा, store नहीं किया जाएगा।"
        ),
    },
    "cancelled": {
        "en": "Student details login cancelled.",
        "hi": "विद्यार्थी विवरण लॉगिन रद्द कर दिया गया है।",
    },
    "missing_url": {
        "en": (
            "Student Details service is ready, but the exam backend login URL is not configured.\n\n"
            "Please add this environment variable in Render:\n"
            "EXAM_BACKEND_STUDENT_LOGIN_URL=https://YOUR-EXAM-BACKEND/student-login-api"
        ),
        "hi": (
            "विद्यार्थी विवरण सेवा तैयार है, लेकिन exam backend login URL configure नहीं है।\n\n"
            "कृपया Render में यह environment variable जोड़ें:\n"
            "EXAM_BACKEND_STUDENT_LOGIN_URL=https://YOUR-EXAM-BACKEND/student-login-api"
        ),
    },
    "login_failed": {
        "en": (
            "Login failed. Please check the admission number and DOB, then try again.\n\n"
            "To restart, select Student Details again."
        ),
        "hi": (
            "Login failed. कृपया admission number और DOB जांचकर दोबारा प्रयास करें।\n\n"
            "फिर से शुरू करने के लिए Student Details चुनें।"
        ),
    },
    "server_error": {
        "en": (
            "Student details could not be fetched right now. Please try again later or contact the school office."
        ),
        "hi": (
            "अभी विद्यार्थी विवरण प्राप्त नहीं हो पाया। कृपया बाद में प्रयास करें या स्कूल कार्यालय से संपर्क करें।"
        ),
    },
    "not_student": {
        "en": (
            "This login was verified, but it is not a student login. Please use the student's admission number and DOB."
        ),
        "hi": (
            "Login verify हुआ, लेकिन यह student login नहीं है। कृपया विद्यार्थी का admission number और DOB उपयोग करें।"
        ),
    },
}


def normalize_message(message_text):
    return (message_text or "").strip().lower()


def service_title_to_id(language):
    return {
        service["title"][language].lower(): service_id
        for service_id, service in SERVICES.items()
    }


def other_service_title_to_id(language):
    return {
        category["title"][language].lower(): category_id
        for category_id, category in OTHER_SERVICE_CATEGORIES.items()
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


def send_other_services_list_message(to_phone_number, language):
    rows = [
        {
            "id": category_id,
            "title": category["title"][language],
            "description": category["description"][language],
        }
        for category_id, category in OTHER_SERVICE_CATEGORIES.items()
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
                "text": {"en": "Other Services", "hi": "अन्य सेवाएं"}[language],
            },
            "body": {
                "text": {
                    "en": "Please select the category you need help with.",
                    "hi": "कृपया वह श्रेणी चुनें जिसमें आपको सहायता चाहिए।",
                }[language]
            },
            "footer": {
                "text": {
                    "en": "P.S. Public School support",
                    "hi": "पी.एस. पब्लिक स्कूल सहायता",
                }[language]
            },
            "action": {
                "button": {"en": "View Categories", "hi": "श्रेणी देखें"}[language],
                "sections": [
                    {
                        "title": {"en": "Support Categories", "hi": "सहायता श्रेणियां"}[language],
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


def send_transport_facility_flow(to_phone_number, language):
    send_text_message(to_phone_number, TRANSPORT_OVERVIEW_MESSAGE[language])
    run_later(1.5, send_text_message, to_phone_number, TRANSPORT_FEE_MESSAGE[language])


def start_student_details_flow(to_phone_number, language):
    STUDENT_DETAIL_SESSIONS[to_phone_number] = {
        "step": "awaiting_username",
        "language": language,
    }
    send_text_message(to_phone_number, STUDENT_LOGIN_TEXT["ask_username"][language])


def normalize_dob_for_exam_login(raw_password):
    value = str(raw_password or "").strip()
    digits = re.sub(r"\D", "", value)
    if len(digits) == 8:
        return f"{digits[0:2]}/{digits[2:4]}/{digits[4:8]}"

    normalized = value.replace("-", "/").replace(".", "/")
    return normalized


def get_exam_backend_base_url():
    if "/login" in EXAM_BACKEND_STUDENT_LOGIN_URL:
        return EXAM_BACKEND_STUDENT_LOGIN_URL.rsplit("/login", 1)[0].rstrip("/")

    return EXAM_BACKEND_STUDENT_LOGIN_URL.rstrip("/")


def fetch_student_profile(student):
    student_id = (
        student.get("id")
        or student.get("_id")
        or student.get("student_id")
        or student.get("studentId")
    )
    if not student_id:
        return student

    profile_url = f"{get_exam_backend_base_url()}/portal/student/{student_id}"
    try:
        response = requests.get(profile_url, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.warning("Student profile fetch failed: %s", exc)
        return student
    except ValueError:
        logger.warning("Student profile returned non-JSON response.")
        return student

    profile = data.get("student") or data.get("data") or data
    if isinstance(profile, dict):
        merged = dict(student)
        merged.update(profile)
        return merged

    return student


def fetch_student_details(username, password):
    if not EXAM_BACKEND_STUDENT_LOGIN_URL:
        return {"ok": False, "reason": "missing_url"}

    payload = {
        "username": str(username or "").strip(),
        "password": normalize_dob_for_exam_login(password),
    }
    try:
        response = requests.post(
            EXAM_BACKEND_STUDENT_LOGIN_URL,
            json=payload,
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.error("Student login request failed: %s", exc)
        return {"ok": False, "reason": "server_error"}

    if response.status_code in {401, 403, 404}:
        logger.warning("Student login failed: %s", response.text)
        return {"ok": False, "reason": "login_failed"}

    if not response.ok:
        logger.error(
            "Student login backend returned %s: %s",
            response.status_code,
            response.text,
        )
        return {"ok": False, "reason": "server_error"}

    try:
        data = response.json()
    except ValueError:
        logger.error("Student login backend returned non-JSON response.")
        return {"ok": False, "reason": "server_error"}

    if data.get("success") is False or data.get("error"):
        logger.warning("Student login backend rejected credentials: %s", data)
        return {"ok": False, "reason": "login_failed"}

    if data.get("role") and data.get("role") != "student":
        logger.warning("Student details login returned non-student role: %s", data.get("role"))
        return {"ok": False, "reason": "not_student"}

    student = (
        data.get("student")
        or data.get("student_details")
        or data.get("user")
        or data.get("data")
        or data
    )
    if not isinstance(student, dict):
        return {"ok": False, "reason": "server_error"}

    student = fetch_student_profile(student)
    return {"ok": True, "student": student}


def first_present(data, keys):
    for key in keys:
        value = data.get(key)
        if value not in {None, ""}:
            return str(value)
    return "-"


def format_student_details(student, language):
    fields = [
        (
            {"en": "Name", "hi": "नाम"}[language],
            ["name", "student_name", "full_name", "studentName"],
        ),
        (
            {"en": "Admission No.", "hi": "प्रवेश नंबर"}[language],
            ["admission_no", "admissionNo"],
        ),
        (
            {"en": "Class", "hi": "कक्षा"}[language],
            ["class", "class_name", "student_class", "className"],
        ),
        (
            {"en": "Section", "hi": "सेक्शन"}[language],
            ["section", "section_name", "sectionName"],
        ),
        (
            {"en": "Roll No.", "hi": "रोल नंबर"}[language],
            ["roll_no", "roll", "roll_number", "rollNo"],
        ),
        (
            {"en": "Father Name", "hi": "पिता का नाम"}[language],
            ["father_name", "father", "fatherName"],
        ),
        (
            {"en": "Mother Name", "hi": "माता का नाम"}[language],
            ["mother_name", "mother", "motherName"],
        ),
        (
            {"en": "Mobile", "hi": "मोबाइल"}[language],
            ["mobile", "phone", "contact", "parent_mobile", "parentMobile"],
        ),
        (
            {"en": "Address", "hi": "पता"}[language],
            ["address", "student_address", "studentAddress"],
        ),
        (
            {"en": "Session", "hi": "सत्र"}[language],
            ["session"],
        ),
    ]

    title = {
        "en": "Student Details",
        "hi": "विद्यार्थी विवरण",
    }[language]
    lines = [title, ""]
    for label, keys in fields:
        lines.append(f"{label}: {first_present(student, keys)}")

    username = first_present(student, ["username", "user_name", "login_id", "loginId"])
    if username != "-":
        lines.append(f"Username: {username}")

    release_rollno = student.get("release_rollno")
    release_result = student.get("release_result")
    eligible = student.get("eligible")
    if release_rollno is not None or release_result is not None or eligible is not None:
        lines.append("")
        lines.append({"en": "Portal Access", "hi": "Portal Access"}[language])
        if eligible is not None:
            lines.append(f"Eligible: {'Yes' if eligible else 'No'}")
        if release_rollno is not None:
            lines.append(f"Roll No. Released: {'Yes' if release_rollno else 'No'}")
        if release_result is not None:
            lines.append(f"Result Released: {'Yes' if release_result else 'No'}")

    footer = {
        "en": (
            "\nFor any correction in student details, please visit the school office with valid proof."
        ),
        "hi": (
            "\nविद्यार्थी विवरण में सुधार के लिए कृपया सही प्रमाण के साथ स्कूल कार्यालय में संपर्क करें।"
        ),
    }[language]
    lines.append(footer)
    return "\n".join(lines)


def handle_student_details_session(to_phone_number, message_text):
    session = STUDENT_DETAIL_SESSIONS.get(to_phone_number)
    if not session:
        return False

    language = session.get("language") or LANGUAGE_BY_USER.get(to_phone_number, "en")
    normalized_text = normalize_message(message_text)

    if normalized_text in {"cancel", "stop", "रद्द", "बंद"}:
        STUDENT_DETAIL_SESSIONS.pop(to_phone_number, None)
        send_text_message(to_phone_number, STUDENT_LOGIN_TEXT["cancelled"][language])
        return True

    if session.get("step") == "awaiting_username":
        session["username"] = message_text.strip()
        session["step"] = "awaiting_password"
        send_text_message(to_phone_number, STUDENT_LOGIN_TEXT["ask_password"][language])
        return True

    if session.get("step") == "awaiting_password":
        username = session.get("username", "")
        password = message_text.strip()
        STUDENT_DETAIL_SESSIONS.pop(to_phone_number, None)

        send_text_message(
            to_phone_number,
            {
                "en": "Please wait. Fetching student details from the school exam portal...",
                "hi": "कृपया प्रतीक्षा करें। स्कूल exam portal से विद्यार्थी विवरण निकाला जा रहा है...",
            }[language],
        )

        result = fetch_student_details(username, password)
        if not result["ok"]:
            send_text_message(
                to_phone_number,
                STUDENT_LOGIN_TEXT[result["reason"]][language],
            )
            return True

        send_text_message(
            to_phone_number,
            format_student_details(result["student"], language),
        )
        return True

    STUDENT_DETAIL_SESSIONS.pop(to_phone_number, None)
    return False


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

    if handle_student_details_session(to_phone_number, message_text):
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

    if service_id == "transport_facility":
        send_transport_facility_flow(to_phone_number, language)
        return

    if service_id == "other_services":
        send_other_services_list_message(to_phone_number, language)
        return

    if service_id == "change_language":
        send_language_buttons(to_phone_number)
        return

    other_category_id = other_service_title_to_id(language).get(normalized_text, normalized_text)
    if other_category_id == "student_details":
        start_student_details_flow(to_phone_number, language)
        return

    if other_category_id in OTHER_SERVICE_CATEGORIES:
        send_text_message(
            to_phone_number,
            OTHER_SERVICE_CATEGORIES[other_category_id]["reply"][language],
        )
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
