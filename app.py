import logging
import os
import re
import threading
from datetime import date, datetime
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from flask import Flask, has_request_context, jsonify, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

VERIFY_TOKEN = "school_bot_verify"
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v20.0")
SCHOOL_IMAGE_URL = os.getenv("SCHOOL_IMAGE_URL", "").strip()
SERVICE_MENU_DELAY_SECONDS = float(os.getenv("SERVICE_MENU_DELAY_SECONDS", "3"))
NAVIGATION_DELAY_SECONDS = float(os.getenv("NAVIGATION_DELAY_SECONDS", "2"))
MEDIA_NAVIGATION_DELAY_SECONDS = float(os.getenv("MEDIA_NAVIGATION_DELAY_SECONDS", "4"))
STUDENT_AUTH_TIMEOUT_SECONDS = int(os.getenv("STUDENT_AUTH_TIMEOUT_SECONDS", "1800"))
STUDENT_AUTH_WARNING_SECONDS = int(os.getenv("STUDENT_AUTH_WARNING_SECONDS", "300"))
ADMISSION_FORM_PDF_URL = os.getenv("ADMISSION_FORM_PDF_URL", "").strip()
ONLINE_ADMISSION_FORM_URL = os.getenv(
    "ONLINE_ADMISSION_FORM_URL",
    "https://pspublicschool.com",
).strip()
DEFAULT_EXAM_BACKEND_STUDENT_LOGIN_URL = (
    "https://exam-backend-117372286918.asia-south1.run.app/login"
)
DEFAULT_EXAM_BACKEND_URL = "https://exam-backend-117372286918.asia-south1.run.app"
DEFAULT_STUDENT_BACKEND_URL = "https://student-backend-117372286918.asia-south1.run.app"
EXAM_BACKEND_STUDENT_LOGIN_URL = os.getenv(
    "EXAM_BACKEND_STUDENT_LOGIN_URL",
    DEFAULT_EXAM_BACKEND_STUDENT_LOGIN_URL,
).strip()
EXAM_BACKEND_URL = os.getenv("EXAM_BACKEND_URL", DEFAULT_EXAM_BACKEND_URL).strip()
STUDENT_BACKEND_URL = os.getenv("STUDENT_BACKEND_URL", DEFAULT_STUDENT_BACKEND_URL).strip()
DEFAULT_LIBRARY_BACKEND_URL = "https://library-backend-117372286918.asia-south1.run.app"
LIBRARY_BACKEND_URL = os.getenv("LIBRARY_BACKEND_URL", DEFAULT_LIBRARY_BACKEND_URL).strip().rstrip("/")
FACILITY_IMAGE_FILES = [
    ("Physics Lab", "facilities/physics-lab.jpg"),
    ("Computer Lab", "facilities/computer-lab.jpg"),
    ("Chemistry Lab", "facilities/chemistry-lab.jpg"),
    ("Transport", "facilities/transport.jpg"),
    ("Library", "facilities/library.jpg"),
    ("Biology Lab", "facilities/biology-lab.jpg"),
    ("Composite Lab", "facilities/composite-lab.jpg"),
    ("Sports", "facilities/sports.jpg"),
]
PROSPECTUS_PDF_FILE = "PROSPECTUS.pdf"
HOLIDAY_EXAM_LIST_PDF_FILE = "holiday-list-2026-27.pdf"
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RESULTS_DIR = os.path.join(app.static_folder, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)
SCHOOL_LOGO_PATH = os.path.join(app.static_folder, "school-logo.png")

# In-memory language preference. For Render's normal single web instance this is enough.
# For multiple workers/instances, move this to a small database or Redis.
LANGUAGE_BY_USER = {}
STUDENT_DETAIL_SESSIONS = {}
STUDENT_AUTH_BY_USER = {}
STUDENT_AUTH_TIMERS_BY_USER = {}
MENU_CONTEXT_BY_USER = {}

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
    "admission_services": {
        "title": {"en": "Admission & Information", "hi": "प्रवेश और जानकारी"},
        "description": {
            "en": "Admission, fees, transport, contact",
            "hi": "प्रवेश, फीस, परिवहन, संपर्क",
        },
        "reply": {
            "en": "Admission Services",
            "hi": "प्रवेश सेवाएं",
        },
    },
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
        "title": {"en": "Transport Routes", "hi": "परिवहन रूट"},
        "description": {
            "en": "Routes and monthly transport fee",
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
    "school_timing_public": {
        "title": {"en": "School Timings", "hi": "स्कूल समय"},
        "description": {"en": "School and office hours", "hi": "स्कूल और कार्यालय समय"},
        "reply": {
            "en": (
                "School Timings\n\n"
                "Monday to Saturday: 8:30 AM to 2:30 PM\n\n"
                "For holiday updates or special schedule changes, please contact the school office before visiting.\n\n"
                "Call: +91 94162 93661\nWhatsApp: +91 94168 38604"
            ),
            "hi": (
                "स्कूल समय\n\n"
                "वर्तमान स्कूल समय, कार्यालय समय, छुट्टी अपडेट या विशेष समय बदलाव की जानकारी के लिए "
                "कृपया आने से पहले स्कूल कार्यालय से संपर्क करें।\n\n"
                "फोन: +91 94162 93661\nWhatsApp: +91 94168 38604"
            ),
        },
    },
    "holiday_list": {
        "title": {"en": "Holiday List", "hi": "छुट्टी सूची"},
        "description": {"en": "Holiday and exam list", "hi": "छुट्टी और परीक्षा सूची"},
        "reply": {
            "en": "Holiday & Exam List 2026-27\n\nThe holiday and exam list PDF will be sent in the next message.",
            "hi": "Holiday & Exam List 2026-27\n\nHoliday और exam list PDF अगले message में भेजा जाएगा।",
        },
    },
    "school_facilities": {
        "title": {"en": "School Facilities", "hi": "स्कूल सुविधाएं"},
        "description": {"en": "Labs, library, sports, transport", "hi": "लैब, लाइब्रेरी, खेल, परिवहन"},
        "reply": {
            "en": (
                "School Facilities\n\n"
                "P.S. Public School provides a strong learning environment with practical labs, reading resources, safe transport, and sports activities.\n\n"
                "- Physics Lab: hands-on experiments for concepts like mechanics, optics, electricity, and measurement.\n"
                "- Chemistry Lab: supervised practical work with lab apparatus, chemicals, and safety practices.\n"
                "- Biology Lab: models, charts, microscopes, and practical observation for life-science learning.\n"
                "- Computer Lab: computer-based learning, digital practice, typing, projects, and basic IT skills.\n"
                "- Composite Lab: integrated science activities for observation, experimentation, and project work.\n"
                "- Library: reading space with books, reference material, newspapers, and study support.\n"
                "- Transport: school bus facility on selected routes with regular coordination.\n"
                "- Sports: outdoor activities, physical fitness, discipline, teamwork, and confidence building."
            ),
            "hi": (
                "स्कूल सुविधाएं\n\n"
                "P.S. Public School में practical learning, reading support, safe transport और sports activities की सुविधाएं उपलब्ध हैं।\n\n"
                "- Physics Lab: experiments और practical learning\n"
                "- Chemistry Lab: supervised practical work और safety practice\n"
                "- Biology Lab: models, charts, microscope और observation work\n"
                "- Computer Lab: digital learning, typing, projects और IT skills\n"
                "- Composite Lab: integrated science activities और project work\n"
                "- Library: books, reference material और study support\n"
                "- Transport: selected routes पर school bus facility\n"
                "- Sports: fitness, discipline, teamwork और confidence building"
            ),
        },
    },
    "prospectus": {
        "title": {"en": "Prospectus", "hi": "प्रॉस्पेक्टस"},
        "description": {"en": "School information and admission guide", "hi": "स्कूल जानकारी और प्रवेश गाइड"},
        "reply": {
            "en": (
                "Prospectus\n\n"
                "School Time: Monday to Saturday, 8:30 AM to 2:30 PM\n\n"
                "The school prospectus includes admission information, facilities, rules, and general guidance. "
                "The PDF will be sent in the next message.\n\n"
                "Call: +91 94162 93661\nWebsite: pspublicschool.com"
            ),
            "hi": (
                "प्रॉस्पेक्टस\n\n"
                "School Time: Monday to Saturday, 8:30 AM to 2:30 PM\n\n"
                "Prospectus PDF में admission information, facilities, rules और general guidance दी गई है। "
                "PDF अगले message में भेजा जाएगा।\n\n"
                "फोन: +91 94162 93661\nWebsite: pspublicschool.com"
            ),
        },
    },
    "other_services": {
        "title": {"en": "Student Services", "hi": "विद्यार्थी सेवाएं"},
        "description": {
            "en": "Accounts, fee, certificates",
            "hi": "फीस, रसीद, लाइब्रेरी, प्रमाण पत्र",
        },
        "reply": {
            "en": (
                "Student Services & Accounts\n\n"
                "For fee details, receipts, certificates, or account support, "
                "please contact the school office."
            ),
            "hi": (
                "शैक्षणिक सेवाएं\n\n"
                "किताबें, यूनिफॉर्म, प्रमाण पत्र, स्कूल समय या सामान्य सहायता के लिए "
                "कृपया स्कूल कार्यालय से संपर्क करें।"
            ),
        },
    },
    "exam_services": {
        "title": {"en": "Academic Services", "hi": "शैक्षणिक सेवाएं"},
        "description": {
            "en": "Attendance, homework, results, exams",
            "hi": "रिजल्ट, परीक्षा, रिपोर्ट कार्ड",
        },
        "reply": {
            "en": "Academic Services",
            "hi": "परीक्षा सेवाएं",
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
    "fee_details": {
        "title": {"en": "Fee Details", "hi": "फीस विवरण"},
        "description": {"en": "Student fee summary", "hi": "विद्यार्थी फीस सारांश"},
        "reply": {
            "en": "Fee Details\n\nFee detail integration is not available on WhatsApp yet. Please contact the accounts office for student-wise fee details.",
            "hi": "फीस विवरण\n\nWhatsApp पर student-wise fee detail अभी उपलब्ध नहीं है। कृपया accounts office से संपर्क करें।",
        },
    },
    "fee_receipt": {
        "title": {"en": "Fee Receipt", "hi": "फीस रसीद"},
        "description": {"en": "Receipt and payment proof", "hi": "रसीद और payment proof"},
        "reply": {
            "en": "Fee Receipt\n\nFor fee receipt or payment proof, please contact the school accounts office.",
            "hi": "फीस रसीद\n\nFee receipt या payment proof के लिए कृपया school accounts office से संपर्क करें।",
        },
    },
    "transport_details": {
        "title": {"en": "Transport Details", "hi": "परिवहन विवरण"},
        "description": {"en": "Student route and bus fee", "hi": "Student route और bus fee"},
        "reply": {
            "en": "Transport Details\n\nFor student-specific transport route, pickup point, timing, and bus fee, please contact the transport/accounts office.",
            "hi": "परिवहन विवरण\n\nStudent-specific route, pickup point, timing और bus fee के लिए transport/accounts office से संपर्क करें।",
        },
    },
    "library_records": {
        "title": {"en": "Library Records", "hi": "लाइब्रेरी रिकॉर्ड"},
        "description": {"en": "Books issued and return status", "hi": "Books issue और return status"},
        "reply": {
            "en": "Library Records\n\nLibrary record integration is not available on WhatsApp yet. Please contact the library/school office.",
            "hi": "लाइब्रेरी रिकॉर्ड\n\nWhatsApp पर library record अभी उपलब्ध नहीं है। कृपया library/school office से संपर्क करें।",
        },
    },
    "fine_details": {
        "title": {"en": "Fine Details", "hi": "जुर्माना विवरण"},
        "description": {"en": "Fine or pending dues", "hi": "Fine या pending dues"},
        "reply": {
            "en": "Fine Details\n\nFor fine details or pending dues, please contact the school accounts office.",
            "hi": "जुर्माना विवरण\n\nFine details या pending dues के लिए कृपया school accounts office से संपर्क करें।",
        },
    },
    "payment_history": {
        "title": {"en": "Payment History", "hi": "Payment History"},
        "description": {"en": "Previous payments and dues", "hi": "पुरानी payment और dues"},
        "reply": {
            "en": "Payment History\n\nPayment history integration is not available on WhatsApp yet. Please contact the accounts office for a verified statement.",
            "hi": "Payment History\n\nWhatsApp पर payment history अभी उपलब्ध नहीं है। Verified statement के लिए accounts office से संपर्क करें।",
        },
    },
    "attendance": {
        "title": {"en": "Attendance", "hi": "उपस्थिति"},
        "description": {"en": "Student attendance status", "hi": "Student attendance status"},
        "reply": {
            "en": "Attendance\n\nAttendance view is not available on WhatsApp yet. Please contact the class teacher or school office.",
            "hi": "उपस्थिति\n\nWhatsApp पर attendance view अभी उपलब्ध नहीं है। कृपया class teacher या school office से संपर्क करें।",
        },
    },
    "homework": {
        "title": {"en": "Homework", "hi": "होमवर्क"},
        "description": {"en": "Daily work and homework", "hi": "Daily work और homework"},
        "reply": {
            "en": "Homework\n\nFor homework and daily work, please contact the concerned class teacher.",
            "hi": "होमवर्क\n\nHomework और daily work के लिए कृपया संबंधित class teacher से संपर्क करें।",
        },
    },
    "exam_schedule": {
        "title": {"en": "Exam Schedule", "hi": "परीक्षा समय-सारणी"},
        "description": {"en": "Datesheet and exam timing", "hi": "Datesheet और exam timing"},
        "reply": {
            "en": "Exam Schedule\n\nThe exam schedule PDF will be sent in the next message.",
            "hi": "परीक्षा समय-सारणी\n\nExam schedule PDF अगले message में भेजा जाएगा।",
        },
    },
    "syllabus": {
        "title": {"en": "Syllabus", "hi": "सिलेबस"},
        "description": {"en": "Class-wise syllabus", "hi": "Class-wise syllabus"},
        "reply": {
            "en": "Syllabus\n\nFor class-wise syllabus, please contact the concerned subject teacher or school office.",
            "hi": "सिलेबस\n\nClass-wise syllabus के लिए concerned subject teacher या school office से संपर्क करें।",
        },
    },
    "assignments": {
        "title": {"en": "Assignments", "hi": "असाइनमेंट"},
        "description": {"en": "Assignments and projects", "hi": "Assignments और projects"},
        "reply": {
            "en": "Assignments\n\nFor assignments and project work, please contact the concerned class/subject teacher.",
            "hi": "असाइनमेंट\n\nAssignments और project work के लिए concerned class/subject teacher से संपर्क करें।",
        },
    },
    "ptm_schedule": {
        "title": {"en": "PTM Schedule", "hi": "PTM समय"},
        "description": {"en": "Parent teacher meeting", "hi": "Parent teacher meeting"},
        "reply": {
            "en": "PTM Schedule\n\nFor PTM dates and timings, please contact the school office or class teacher.",
            "hi": "PTM समय\n\nPTM dates और timings के लिए school office या class teacher से संपर्क करें।",
        },
    },
    "teacher_remarks": {
        "title": {"en": "Teacher Remarks", "hi": "शिक्षक टिप्पणी"},
        "description": {"en": "Teacher feedback", "hi": "Teacher feedback"},
        "reply": {
            "en": "Teacher Remarks\n\nFor teacher remarks or performance feedback, please contact the concerned class teacher.",
            "hi": "शिक्षक टिप्पणी\n\nTeacher remarks या performance feedback के लिए concerned class teacher से संपर्क करें।",
        },
    },
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
            "en": "Profile, photo and ID card",
            "hi": "प्रोफाइल, फोटो और ID कार्ड",
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

CERTIFICATE_CATEGORIES = {
    "certificate_bonafide": {
        "title": {"en": "Bonafide Certificate", "hi": "बोनाफाइड प्रमाण पत्र"},
        "description": {
            "en": "Student identity and school record",
            "hi": "विद्यार्थी और स्कूल रिकॉर्ड",
        },
        "certificate_type": "bonafide",
    },
    "certificate_character": {
        "title": {"en": "Character Certificate", "hi": "चरित्र प्रमाण पत्र"},
        "description": {
            "en": "Conduct and character certificate",
            "hi": "आचरण और चरित्र प्रमाण",
        },
        "certificate_type": "character",
    },
    "certificate_study": {
        "title": {"en": "Study Certificate", "hi": "अध्ययन प्रमाण पत्र"},
        "description": {
            "en": "Class and session study proof",
            "hi": "कक्षा और सत्र प्रमाण",
        },
        "certificate_type": "study",
    },
    "certificate_tc": {
        "title": {"en": "Transfer Certificate", "hi": "ट्रांसफर सर्टिफिकेट"},
        "description": {
            "en": "Contact office for TC",
            "hi": "TC के लिए कार्यालय संपर्क",
        },
        "certificate_type": "tc",
    },
}

MAIN_SERVICE_IDS = [
    "admission_services",
    "other_services",
    "exam_services",
    "change_language",
]

ADMISSION_SERVICE_IDS = [
    "admission_enquiry",
    "fee_structure",
    "transport_facility",
    "school_timing_public",
    "holiday_list",
    "contact_school",
    "school_facilities",
    "prospectus",
]

ACADEMIC_CATEGORY_IDS = [
    "student_details",
    "fee_details",
    "fee_receipt",
    "transport_details",
    "library_records",
    "fine_details",
    "certificates",
    "payment_history",
]

EXAM_CATEGORY_IDS = [
    "attendance",
    "homework",
    "results_exams",
    "exam_schedule",
    "syllabus",
    "assignments",
    "ptm_schedule",
    "teacher_remarks",
]

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

NAVIGATION_ACTIONS = {
    "nav_main_menu",
    "nav_previous_menu",
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
            "You can send it as DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD, DD-MM-YYYY, MM-DD-YYYY, or DDMMYYYY.\n\n"
            "For privacy, this is used only for login verification and is not stored."
        ),
        "hi": (
            "अब कृपया विद्यार्थी की DOB भेजें, बिल्कुल वैसे ही जैसे exam portal में saved है।\n\n"
            "आप DOB को DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD, DD-MM-YYYY, MM-DD-YYYY या DDMMYYYY format में भेज सकते हैं।\n\n"
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
    "result_error": {
        "en": (
            "Result could not be fetched right now. Please try again later or contact the school office."
        ),
        "hi": (
            "अभी result प्राप्त नहीं हो पाया। कृपया बाद में प्रयास करें या स्कूल कार्यालय से संपर्क करें।"
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


def certificate_title_to_id(language):
    return {
        category["title"][language].lower(): category_id
        for category_id, category in CERTIFICATE_CATEGORIES.items()
    }


def send_whatsapp_payload(payload):
    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        logger.error(
            "WhatsApp send skipped. ACCESS_TOKEN configured=%s PHONE_NUMBER_ID configured=%s",
            bool(ACCESS_TOKEN),
            bool(PHONE_NUMBER_ID),
        )
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
        logger.error(
            "Failed to send WhatsApp message. type=%s to=%s error=%s response=%s",
            payload.get("type"),
            payload.get("to"),
            exc,
            response_text,
        )
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


def send_result_document_message(to_phone_number, document_url, filename, caption):
    return send_document_message(to_phone_number, document_url, filename, caption)


def build_url(base_url, path, params=None):
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    if params:
        url = f"{url}?{urlencode(params)}"
    return url


def build_public_static_url(filename):
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL}/static/{filename.lstrip('/')}"

    if has_request_context():
        return url_for("static", filename=filename, _external=True, _scheme="https")

    logger.warning("PUBLIC_BASE_URL is not set; cannot build public URL outside request context.")
    return ""


def static_file_exists(filename):
    return os.path.isfile(os.path.join(app.static_folder, filename.replace("/", os.sep)))


def send_school_facilities_flow(to_phone_number, language):
    send_text_message(to_phone_number, SERVICES["school_facilities"]["reply"][language])

    sent_any_image = False
    sent_image_count = 0
    for title, filename in FACILITY_IMAGE_FILES:
        if not static_file_exists(filename):
            continue

        image_url = build_public_static_url(filename)
        if not image_url:
            continue

        caption = {
            "en": f"P.S. Public School - {title}",
            "hi": f"P.S. Public School - {title}",
        }[language]
        if send_image_message(to_phone_number, image_url, caption):
            sent_any_image = True
            sent_image_count += 1

    if not sent_any_image:
        logger.info("No facility images found in static/facilities to send.")

    delay = MEDIA_NAVIGATION_DELAY_SECONDS + (sent_image_count * 1.5)
    send_navigation_buttons_later(to_phone_number, language, "admission", delay)


def send_prospectus_flow(to_phone_number, language):
    send_text_message(to_phone_number, SERVICES["prospectus"]["reply"][language])

    if static_file_exists(PROSPECTUS_PDF_FILE):
        prospectus_url = build_public_static_url(PROSPECTUS_PDF_FILE)
        if prospectus_url:
            send_document_message(
                to_phone_number,
                prospectus_url,
                "P.S. Public School Prospectus.pdf",
                {
                    "en": "P.S. Public School Prospectus",
                    "hi": "P.S. Public School Prospectus",
                }[language],
            )
        else:
            send_text_message(
                to_phone_number,
                {
                    "en": "Prospectus PDF is available, but the public URL is not configured.",
                    "hi": "Prospectus PDF available है, लेकिन public URL configured नहीं है।",
                }[language],
            )
    else:
        send_text_message(
            to_phone_number,
            {
                "en": "Prospectus PDF is not available right now. Please contact the school office.",
                "hi": "Prospectus PDF अभी उपलब्ध नहीं है। कृपया school office से संपर्क करें।",
            }[language],
        )

    send_navigation_buttons_later(to_phone_number, language, "admission", MEDIA_NAVIGATION_DELAY_SECONDS)


def send_holiday_exam_list_flow(to_phone_number, language, previous_menu="admission"):
    send_text_message(to_phone_number, SERVICES["holiday_list"]["reply"][language])

    if static_file_exists(HOLIDAY_EXAM_LIST_PDF_FILE):
        pdf_url = build_public_static_url(HOLIDAY_EXAM_LIST_PDF_FILE)
        if pdf_url:
            send_document_message(
                to_phone_number,
                pdf_url,
                "P.S. Public School Holiday & Exam List 2026-27.pdf",
                {
                    "en": "Holiday & Exam List 2026-27",
                    "hi": "Holiday & Exam List 2026-27",
                }[language],
            )
        else:
            send_text_message(
                to_phone_number,
                {
                    "en": "Holiday and exam list PDF is available, but the public URL is not configured.",
                    "hi": "Holiday और exam list PDF available है, लेकिन public URL configured नहीं है।",
                }[language],
            )
    else:
        send_text_message(
            to_phone_number,
            {
                "en": "Holiday and exam list PDF is not available right now. Please contact the school office.",
                "hi": "Holiday और exam list PDF अभी उपलब्ध नहीं है। कृपया school office से संपर्क करें।",
            }[language],
        )

    send_navigation_buttons_later(to_phone_number, language, previous_menu, MEDIA_NAVIGATION_DELAY_SECONDS)


def fetch_json_url(url, timeout=20):
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def normalize_roll(value):
    text = str(value or "").strip()
    normalized = text.lstrip("0")
    return normalized or text


def is_internal_enabled(exam):
    return not (
        exam.get("internal_marks") is False
        or str(exam.get("internal_marks", "")).strip().lower() in {"no", "false", "0"}
    )


def get_result_status_text(key, language):
    labels = {
        "not_eligible": {
            "en": "You are currently not eligible for result release.",
            "hi": "आपका result अभी release के लिए eligible नहीं है।",
        },
        "not_released": {
            "en": "Result is not released for your profile yet.",
            "hi": "आपके profile के लिए result अभी release नहीं हुआ है।",
        },
        "class_result_not_released": {
            "en": (
                "Result warning\n\n"
                "The result for your class has not been released yet. Please wait for the official result announcement from the school."
            ),
            "hi": (
                "Result warning\n\n"
                "आपकी class का result अभी release नहीं हुआ है। कृपया स्कूल की official result announcement का इंतजार करें।"
            ),
        },
        "student_unauthorized": {
            "en": (
                "Result warning\n\n"
                "The result for your class is released, but this student is not authorized to view the result right now. Please contact the school office."
            ),
            "hi": (
                "Result warning\n\n"
                "आपकी class का result release हो चुका है, लेकिन यह student अभी result देखने के लिए authorized नहीं है। कृपया school office से संपर्क करें।"
            ),
        },
        "roll_not_released": {
            "en": "Roll number is not released for your profile.",
            "hi": "आपके profile के लिए roll number release नहीं हुआ है।",
        },
        "no_result": {
            "en": "No published result found for your profile.",
            "hi": "आपके profile के लिए कोई published result नहीं मिला।",
        },
        "backend_unavailable": {
            "en": "Result service is temporarily unavailable. Please try again later or contact the school office.",
            "hi": "Result service अभी उपलब्ध नहीं है। कृपया बाद में प्रयास करें या स्कूल कार्यालय से संपर्क करें।",
        },
    }
    return labels[key][language]


def fetch_student_results(student, language):
    exam_base_url = get_exam_backend_base_url()
    profile = fetch_student_profile(student)
    profile = enrich_student_with_backend_record(profile)

    session = str(profile.get("session") or "").replace("-", "_")
    class_name = profile.get("class_name") or profile.get("class") or ""
    roll = str(profile.get("roll") or profile.get("rollno") or "").strip()
    candidate_rolls = {roll, normalize_roll(roll)}
    candidate_rolls = {item for item in candidate_rolls if item}
    student_ids = {
        str(profile.get("id") or ""),
        str(student.get("id") or ""),
        str(student.get("_id") or ""),
        str(student.get("student_id") or ""),
    }
    student_ids = {item for item in student_ids if item}

    try:
        exams_data = fetch_json_url(build_url(exam_base_url, "/exam/list-all"))
    except Exception as exc:
        logger.error("Unable to fetch exam list: %s", exc)
        return {"ok": True, "status": "backend_unavailable", "profile": profile, "exams": []}

    exams = exams_data.get("exams", []) if isinstance(exams_data, dict) else []
    result_exams = []
    class_exam_found = False
    class_result_released = False

    for exam in exams:
        exam_name = str(exam.get("exam_name") or "").strip()
        exam_session = str(exam.get("session") or session).replace("-", "_")
        if not exam_name or not class_name:
            continue
        if session and exam_session and exam_session != session:
            continue
        class_exam_found = True

        try:
            status_data = fetch_json_url(
                build_url(
                    exam_base_url,
                    "/result/status",
                    {
                        "session": exam_session,
                        "class_name": class_name,
                        "exam_name": exam_name,
                    },
                )
            )
        except Exception as exc:
            logger.warning("Unable to fetch result status for %s: %s", exam_name, exc)
            result_exams.append({"exam_name": exam_name, "status": "coming_soon"})
            continue

        if not status_data.get("success") or not status_data.get("published"):
            result_exams.append({"exam_name": exam_name, "status": "coming_soon"})
            continue

        class_result_released = True

        if profile.get("eligible") is False or profile.get("release_result") is False:
            return {"ok": True, "status": "student_unauthorized", "profile": profile, "exams": []}

        if not candidate_rolls:
            return {"ok": True, "status": "roll_not_released", "profile": profile, "exams": []}

        try:
            marks_data = fetch_json_url(
                build_url(
                    exam_base_url,
                    "/exam/get-marks",
                    {
                        "session": exam_session,
                        "class_name": class_name,
                        "exam_name": exam_name,
                    },
                )
            )
        except Exception as exc:
            logger.warning("Unable to fetch marks for %s: %s", exam_name, exc)
            result_exams.append({"exam_name": exam_name, "status": "not_uploaded"})
            continue

        if not marks_data.get("success"):
            result_exams.append({"exam_name": exam_name, "status": "not_uploaded"})
            continue

        marks_by_roll = {}
        for mark in marks_data.get("marks", []):
            mark_roll = str(mark.get("roll") or mark.get("student_id") or "").strip()
            if not mark_roll:
                continue
            marks_by_roll.setdefault(mark_roll, {})[str(mark.get("subject") or "")] = mark.get("marks")

        subject_marks = None
        for candidate in candidate_rolls:
            if candidate in marks_by_roll:
                subject_marks = marks_by_roll[candidate]
                break

        if not subject_marks:
            result_exams.append({"exam_name": exam_name, "status": "not_uploaded"})
            continue

        allow_internal = is_internal_enabled(exam)
        rows = []
        total = 0
        total_max = 0
        failed = False

        for subject, external_value in subject_marks.items():
            if not subject:
                continue

            external = int(float(external_value or 0))
            external_max = int(float(exam.get("total_marks") or 0))
            internal = 0
            internal_max = 0

            try:
                config_data = fetch_json_url(
                    build_url(
                        exam_base_url,
                        "/exam/subject-config/get",
                        {
                            "session": exam_session,
                            "class_name": class_name,
                            "exam_name": exam_name,
                            "subject": subject,
                        },
                    )
                )
                config = config_data.get("config") or {}
                if config.get("external_max_marks") is not None:
                    external_max = int(float(config.get("external_max_marks") or 0))
                if allow_internal and config.get("internal_max_marks") is not None:
                    internal_max = int(float(config.get("internal_max_marks") or 0))
            except Exception:
                pass

            if allow_internal:
                try:
                    internal_data = fetch_json_url(
                        build_url(
                            exam_base_url,
                            "/internal-marks/list",
                            {
                                "session": exam_session,
                                "class_name": class_name,
                                "subject": subject,
                                "exam_name": exam_name,
                            },
                        )
                    )
                    for row in internal_data.get("marks", []):
                        if str(row.get("student_id") or "") in student_ids:
                            internal = int(float(row.get("marks") or 0))
                            break
                except Exception:
                    pass

            subject_total = external + internal
            subject_max = external_max + internal_max
            pass_mark = int((subject_max * 0.33) + 0.9999) if subject_max else 0
            passed = subject_total >= pass_mark
            failed = failed or not passed
            total += subject_total
            total_max += subject_max
            rows.append(
                {
                    "subject": subject,
                    "external": external,
                    "external_max": external_max,
                    "internal": internal,
                    "internal_max": internal_max,
                    "total": subject_total,
                    "total_max": subject_max,
                    "status": "PASS" if passed else "FAIL",
                }
            )

        result_exams.append(
            {
                "exam_name": exam_name,
                "status": "published",
                "session": exam_session,
                "allow_internal": allow_internal,
                "rows": rows,
                "total": total,
                "total_max": total_max,
                "result": "FAIL" if failed else "PASS",
            }
        )

    if class_exam_found and not class_result_released:
        return {"ok": True, "status": "class_result_not_released", "profile": profile, "exams": result_exams}

    if not result_exams:
        return {"ok": True, "status": "no_result", "profile": profile, "exams": []}

    return {"ok": True, "status": "ok", "profile": profile, "exams": result_exams}


def result_summary_text(result_data, language):
    profile = result_data.get("profile") or {}
    if result_data.get("status") != "ok":
        return (
            f"{ {'en': 'Results & Exams', 'hi': 'रिजल्ट व परीक्षा'}[language] }\n\n"
            f"Name: {profile.get('name', '-')}\n"
            f"Class: {profile.get('class_name') or profile.get('class') or '-'} {profile.get('section') or ''}\n"
            f"Roll No.: {profile.get('roll') or profile.get('rollno') or '-'}\n"
            f"Session: {profile.get('session') or '-'}\n\n"
            f"{get_result_status_text(result_data.get('status', 'no_result'), language)}"
        )

    title = {"en": "Results & Exams", "hi": "रिजल्ट व परीक्षा"}[language]
    lines = [
        title,
        "",
        f"Name: {profile.get('name', '-')}",
        f"Class: {profile.get('class_name') or profile.get('class') or '-'} {profile.get('section') or ''}".strip(),
        f"Roll No.: {profile.get('roll') or profile.get('rollno') or '-'}",
        f"Session: {profile.get('session') or '-'}",
        "",
    ]

    for exam in result_data.get("exams", []):
        exam_name = exam.get("exam_name", "Exam")
        status = exam.get("status")
        if status == "coming_soon":
            lines.append(f"{exam_name}: Result coming soon.")
        elif status == "not_uploaded":
            lines.append(f"{exam_name}: Result not uploaded yet.")
        elif status == "published":
            lines.append(
                f"{exam_name}: {exam.get('result')} | {exam.get('total')}/{exam.get('total_max')}"
            )
            for row in exam.get("rows", []):
                lines.append(
                    f"- {row['subject']}: {row['total']}/{row['total_max']} ({row['status']})"
                )
        lines.append("")

    lines.append("PDF marksheet is being sent separately.")
    return "\n".join(lines).strip()


def pdf_escape(text):
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_simple_pdf(path, lines):
    pages = [lines[i : i + 38] for i in range(0, len(lines), 38)] or [["No result data"]]
    objects = []
    page_ids = []
    content_ids = []

    def add_object(body):
        objects.append(body)
        return len(objects)

    catalog_id = add_object("<< /Type /Catalog /Pages 2 0 R >>")
    pages_id = add_object("")
    font_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for page_lines in pages:
        y = 790
        commands = ["BT", "/F1 10 Tf", "50 790 Td"]
        first = True
        for line in page_lines:
            if first:
                commands.append(f"({pdf_escape(line)}) Tj")
                first = False
            else:
                commands.append("0 -18 Td")
                commands.append(f"({pdf_escape(line)}) Tj")
            y -= 18
        commands.append("ET")
        stream = "\n".join(commands)
        content_id = add_object(
            f"<< /Length {len(stream.encode('latin-1', errors='replace'))} >>\n"
            f"stream\n{stream}\nendstream"
        )
        page_id = add_object(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        )
        content_ids.append(content_id)
        page_ids.append(page_id)

    objects[pages_id - 1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{pid} 0 R' for pid in page_ids)}] "
        f"/Count {len(page_ids)} >>"
    )

    pdf_parts = ["%PDF-1.4\n"]
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(sum(len(part.encode("latin-1", errors="replace")) for part in pdf_parts))
        pdf_parts.append(f"{index} 0 obj\n{body}\nendobj\n")

    xref_offset = sum(len(part.encode("latin-1", errors="replace")) for part in pdf_parts)
    pdf_parts.append(f"xref\n0 {len(objects) + 1}\n")
    pdf_parts.append("0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf_parts.append(f"{offset:010d} 00000 n \n")
    pdf_parts.append(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )

    with open(path, "wb") as pdf_file:
        pdf_file.write("".join(pdf_parts).encode("latin-1", errors="replace"))


def result_pdf_lines(result_data):
    profile = result_data.get("profile") or {}
    lines = [
        "P.S. Public School",
        "Student Result / Marksheet",
        "",
        f"Name: {profile.get('name', '-')}",
        f"Admission No.: {profile.get('admission_no', '-')}",
        f"Class: {profile.get('class_name') or profile.get('class') or '-'} {profile.get('section') or ''}".strip(),
        f"Roll No.: {profile.get('roll') or profile.get('rollno') or '-'}",
        f"Session: {profile.get('session') or '-'}",
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    if result_data.get("status") != "ok":
        lines.append(get_result_status_text(result_data.get("status", "no_result"), "en"))
        return lines

    for exam in result_data.get("exams", []):
        lines.append(f"Exam: {exam.get('exam_name', 'Exam')}")
        if exam.get("status") != "published":
            lines.append(f"Status: {exam.get('status', 'pending').replace('_', ' ').title()}")
            lines.append("")
            continue
        lines.append("Subject | Ext | Int | Total | Status")
        for row in exam.get("rows", []):
            lines.append(
                f"{row['subject']} | {row['external']}/{row['external_max']} | "
                f"{row['internal']}/{row['internal_max']} | "
                f"{row['total']}/{row['total_max']} | {row['status']}"
            )
        lines.append(f"Result: {exam.get('result')} | {exam.get('total')}/{exam.get('total_max')}")
        lines.append("")
    return lines


def draw_marksheet_pdf(path, result_data):
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph, Table, TableStyle

    profile = result_data.get("profile") or {}
    width, height = A4
    pdf = canvas.Canvas(path, pagesize=A4)

    def clean(value, fallback="-"):
        text = str(value or "").strip()
        return fallback if not text or text.lower() in {"nan", "none", "null"} else text

    def draw_header():
        pdf.setStrokeColor(colors.HexColor("#0b2f5b"))
        pdf.setLineWidth(1.6)
        pdf.rect(13 * mm, 12 * mm, width - 26 * mm, height - 24 * mm)

        if os.path.exists(SCHOOL_LOGO_PATH):
            pdf.drawImage(
                SCHOOL_LOGO_PATH,
                19 * mm,
                height - 42 * mm,
                26 * mm,
                26 * mm,
                preserveAspectRatio=True,
                mask="auto",
            )
        else:
            pdf.setFillColor(colors.HexColor("#0b2f5b"))
            pdf.circle(30 * mm, height - 28 * mm, 12 * mm, stroke=1, fill=0)
            pdf.setFont("Helvetica-Bold", 14)
            pdf.drawCentredString(30 * mm, height - 30 * mm, "PS")
            pdf.setFont("Helvetica", 6)
            pdf.drawCentredString(30 * mm, height - 37 * mm, "PUBLIC SCHOOL")

        pdf.setFont("Helvetica-Bold", 24)
        pdf.drawCentredString(width / 2, height - 25 * mm, "P.S. PUBLIC SCHOOL")
        pdf.setFont("Helvetica", 11)
        pdf.drawCentredString(width / 2, height - 32 * mm, "Ganaur Road Bhurri (Sonipat) - 131101")
        pdf.setFont("Helvetica", 8)
        pdf.drawCentredString(width / 2, height - 38 * mm, "Phone: +91 94162 93661 | Email: psbhurri@gmail.com | Website: pspublicschool.com")

        pdf.line(22 * mm, height - 45 * mm, width - 22 * mm, height - 45 * mm)
        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawCentredString(width / 2, height - 55 * mm, "STUDENT RESULT / MARKSHEET")

    def draw_photo(x, y):
        photo_url = get_student_photo_url(profile)
        pdf.setStrokeColor(colors.HexColor("#0b2f5b"))
        pdf.rect(x, y, 30 * mm, 38 * mm)
        if not photo_url:
            pdf.setFont("Helvetica", 8)
            pdf.drawCentredString(x + 15 * mm, y + 21 * mm, "PHOTO")
            pdf.drawCentredString(x + 15 * mm, y + 16 * mm, "ON RECORD")
            return
        try:
            response = requests.get(photo_url, timeout=10)
            response.raise_for_status()
            image_data = ImageReader(BytesIO(response.content))
            pdf.drawImage(image_data, x + 1.5 * mm, y + 1.5 * mm, 27 * mm, 35 * mm, preserveAspectRatio=True, anchor="c")
        except Exception as exc:
            logger.warning("Unable to draw student photo in marksheet PDF: %s", exc)
            pdf.setFont("Helvetica", 8)
            pdf.drawCentredString(x + 15 * mm, y + 21 * mm, "PHOTO")
            pdf.drawCentredString(x + 15 * mm, y + 16 * mm, "ON RECORD")

    draw_header()

    y = height - 70 * mm
    draw_photo(width - 55 * mm, y - 34 * mm)

    pdf.setFont("Helvetica-Bold", 10)
    details = [
        ("Name", clean(profile.get("name") or profile.get("student_name"))),
        ("Admission No.", clean(profile.get("admission_no"))),
        ("Class", f"{clean(profile.get('class_name') or profile.get('class'))} {clean(profile.get('section'), '')}".strip()),
        ("Roll No.", clean(profile.get("roll") or profile.get("rollno"))),
        ("Father Name", clean(profile.get("father_name"))),
        ("Session", clean(profile.get("session"))),
    ]
    x_label = 24 * mm
    x_value = 58 * mm
    for label, value in details:
        pdf.setFont("Helvetica-Bold", 9.5)
        pdf.drawString(x_label, y, f"{label}:")
        pdf.setFont("Helvetica", 9.5)
        pdf.drawString(x_value, y, value)
        y -= 7 * mm

    y -= 5 * mm
    normal_style = ParagraphStyle("normal", fontName="Helvetica", fontSize=8, leading=10)
    for exam in result_data.get("exams", []):
        if exam.get("status") != "published" or not exam.get("rows"):
            continue

        pdf.setFillColor(colors.HexColor("#0b2f5b"))
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(22 * mm, y, f"Exam: {exam.get('exam_name', 'Exam')}")
        pdf.setFillColor(colors.black)
        y -= 7 * mm

        table_data = [[
            "Subject", "External", "Internal", "Total", "Status"
        ]]
        for row in exam.get("rows", []):
            table_data.append([
                Paragraph(str(row["subject"]), normal_style),
                f"{row['external']}/{row['external_max']}",
                f"{row['internal']}/{row['internal_max']}",
                f"{row['total']}/{row['total_max']}",
                row["status"],
            ])

        table = Table(table_data, colWidths=[58 * mm, 28 * mm, 28 * mm, 28 * mm, 25 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b2f5b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#7f8ea3")),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7fb")]),
        ]))
        table_width, table_height = table.wrapOn(pdf, width, height)
        table.drawOn(pdf, 22 * mm, y - table_height)
        y -= table_height + 8 * mm

        percentage = (exam.get("total", 0) / exam.get("total_max", 1) * 100) if exam.get("total_max") else 0
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(22 * mm, y, f"Result: {exam.get('result')}    Total: {exam.get('total')}/{exam.get('total_max')}    Percentage: {percentage:.2f}%")
        y -= 12 * mm

    coscholastic = [
        ["Co-Scholastic Area", "Grade"],
        ["Discipline", "A"],
        ["Attendance & Punctuality", "A"],
        ["Participation in School Activities", "A"],
        ["Cleanliness & Uniform", "A"],
    ]
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(22 * mm, y, "Co-Scholastic / Extra Activities")
    y -= 7 * mm
    act_table = Table(coscholastic, colWidths=[95 * mm, 30 * mm])
    act_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef7")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#7f8ea3")),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
    ]))
    tw, th = act_table.wrapOn(pdf, width, height)
    act_table.drawOn(pdf, 22 * mm, y - th)

    pdf.setFont("Helvetica", 8)
    pdf.drawString(22 * mm, 42 * mm, "Note: This digitally generated marksheet is based on school records.")
    pdf.drawString(22 * mm, 37 * mm, "For signed/stamped hard copy, please contact the school office.")

    pdf.setStrokeColor(colors.HexColor("#0b2f5b"))
    pdf.line(width - 65 * mm, 43 * mm, width - 23 * mm, 43 * mm)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(width - 62 * mm, 47 * mm, "Naveen Kumar")
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(width - 58 * mm, 38 * mm, "Principal")
    pdf.drawString(width - 70 * mm, 33 * mm, "Digitally signed by Naveen Kumar, Principal")

    pdf.showPage()
    pdf.save()


def create_result_pdf(result_data):
    profile = result_data.get("profile") or {}
    safe_admission = re.sub(r"[^A-Za-z0-9_-]", "_", str(profile.get("admission_no") or "student"))
    filename = f"result_{safe_admission}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.pdf"
    path = os.path.join(RESULTS_DIR, filename)
    try:
        draw_marksheet_pdf(path, result_data)
    except Exception as exc:
        logger.exception("Professional marksheet PDF failed, using simple PDF: %s", exc)
        write_simple_pdf(path, result_pdf_lines(result_data))
    return filename


def clean_certificate_value(value, fallback="-"):
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return fallback
    return text


def certificate_pdf_lines(student, certificate_type):
    name = clean_certificate_value(first_present(student, ["name", "student_name"]))
    father = clean_certificate_value(first_present(student, ["father_name", "fatherName"]))
    mother = clean_certificate_value(first_present(student, ["mother_name", "motherName"]), "")
    class_name = clean_certificate_value(first_present(student, ["class_name", "class"]))
    section = clean_certificate_value(first_present(student, ["section"]), "")
    session = clean_certificate_value(first_present(student, ["session"]))
    admission_no = clean_certificate_value(first_present(student, ["admission_no", "admissionNo"]))
    roll = clean_certificate_value(first_present(student, ["roll", "rollno", "roll_no"]), "")
    dob = clean_certificate_value(first_present(student, ["dob", "date_of_birth", "dateOfBirth"]), "")
    address = clean_certificate_value(first_present(student, ["address", "student_address"]), "")
    class_label = f"{class_name}{' - ' + section if section else ''}"
    today = datetime.utcnow().strftime("%d/%m/%Y")

    if certificate_type == "bonafide":
        title = "BONAFIDE CERTIFICATE"
        body = [
            f"This is to certify that {name}, child of Mr. {father}"
            f"{' and Mrs. ' + mother if mother else ''}, is a bona fide student of P.S. Public School.",
            f"The student is studying in Class {class_label} during the academic session {session}.",
            f"The admission number of the student is {admission_no}."
            f"{' The date of birth as per school record is ' + dob + '.' if dob else ''}",
            f"{'The address recorded in school record is ' + address + '.' if address else ''}",
            "This certificate is issued on request for official use.",
        ]
    elif certificate_type == "character":
        title = "CHARACTER CERTIFICATE"
        body = [
            f"This is to certify that {name}, child of Mr. {father}"
            f"{' and Mrs. ' + mother if mother else ''}, is/was a student of P.S. Public School.",
            f"The student is/was enrolled in Class {class_label} during the academic session {session}.",
            "To the best of our knowledge, the student's conduct, behavior, and character have been satisfactory.",
            "This certificate is issued on request for official use.",
        ]
    elif certificate_type == "study":
        title = "STUDY CERTIFICATE"
        body = [
            f"This is to certify that {name}, child of Mr. {father}"
            f"{' and Mrs. ' + mother if mother else ''}, is a student of P.S. Public School.",
            f"The student is studying in Class {class_label} during the academic session {session}.",
            f"Admission No.: {admission_no}{' | Roll No.: ' + roll if roll else ''}",
            "This certificate is issued as per school records.",
        ]
    else:
        title = "CERTIFICATE"
        body = ["Please contact the school office for this certificate."]

    lines = [
        "P.S. PUBLIC SCHOOL",
        "Ganaur Road Bhurri (Sonipat)",
        "",
        title,
        "",
        f"Date: {today}",
        f"Admission No.: {admission_no}",
        "",
    ]
    lines.extend(body)
    lines.extend(
        [
            "",
            "Note: This digitally generated certificate is based on school records.",
            "For signed/stamped copy, please contact the school office.",
            "",
            "Authorized Signatory",
            "P.S. Public School",
        ]
    )
    return lines


def wrap_pdf_text(text, max_chars=92):
    words = str(text).split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def certificate_content(student, certificate_type):
    name = clean_certificate_value(first_present(student, ["name", "student_name"]))
    father = clean_certificate_value(first_present(student, ["father_name", "fatherName"]))
    mother = clean_certificate_value(first_present(student, ["mother_name", "motherName"]), "")
    class_name = clean_certificate_value(first_present(student, ["class_name", "class"]))
    section = clean_certificate_value(first_present(student, ["section"]), "")
    session = clean_certificate_value(first_present(student, ["session"]))
    admission_no = clean_certificate_value(first_present(student, ["admission_no", "admissionNo"]))
    roll = clean_certificate_value(first_present(student, ["roll", "rollno", "roll_no"]), "")
    dob = clean_certificate_value(first_present(student, ["dob", "date_of_birth", "dateOfBirth"]), "")
    address = clean_certificate_value(first_present(student, ["address", "student_address"]), "")
    class_label = f"{class_name}{' - ' + section if section else ''}"

    if certificate_type == "bonafide":
        title = "BONAFIDE CERTIFICATE"
        paragraphs = [
            (
                f"This is to certify that {name}, child of Mr. {father}"
                f"{' and Mrs. ' + mother if mother else ''}, is a bona fide student of P.S. Public School."
            ),
            f"The student is studying in Class {class_label} during the academic session {session}.",
            (
                f"The admission number of the student is {admission_no}."
                f"{' The date of birth as per school record is ' + dob + '.' if dob else ''}"
            ),
            f"{'The address recorded in school record is ' + address + '.' if address else ''}",
            "This certificate is issued on request for official use.",
        ]
    elif certificate_type == "character":
        title = "CHARACTER CERTIFICATE"
        paragraphs = [
            (
                f"This is to certify that {name}, child of Mr. {father}"
                f"{' and Mrs. ' + mother if mother else ''}, is/was a student of P.S. Public School."
            ),
            f"The student is/was enrolled in Class {class_label} during the academic session {session}.",
            "To the best of our knowledge, the student's conduct, behavior, and character have been satisfactory.",
            "This certificate is issued on request for official use.",
        ]
    elif certificate_type == "study":
        title = "STUDY CERTIFICATE"
        paragraphs = [
            (
                f"This is to certify that {name}, child of Mr. {father}"
                f"{' and Mrs. ' + mother if mother else ''}, is a student of P.S. Public School."
            ),
            f"The student is studying in Class {class_label} during the academic session {session}.",
            f"Admission No.: {admission_no}{' | Roll No.: ' + roll if roll else ''}",
            "This certificate is issued as per school records.",
        ]
    else:
        title = "CERTIFICATE"
        paragraphs = ["Please contact the school office for this certificate."]

    return {
        "title": title,
        "admission_no": admission_no,
        "date": datetime.utcnow().strftime("%d/%m/%Y"),
        "paragraphs": [paragraph for paragraph in paragraphs if paragraph.strip()],
    }


def write_professional_certificate_pdf(path, student, certificate_type):
    content = certificate_content(student, certificate_type)
    ref_no = f"PSPS/{content['admission_no']}/{datetime.utcnow().strftime('%Y%m%d')}"
    commands = [
        "q",
        "1 1 1 rg",
        "0 0 595 842 re f",
        "Q",
        "q",
        "0.94 0.97 1 rg",
        "38 38 519 766 re f",
        "Q",
        "q",
        "1 1 1 rg",
        "50 50 495 742 re f",
        "Q",
        "q",
        "0.05 0.18 0.35 RG",
        "2.2 w",
        "50 50 495 742 re S",
        "Q",
        "q",
        "0.05 0.18 0.35 RG",
        "1.4 w",
        "78 710 54 54 re S",
        "Q",
        "q",
        "0.05 0.18 0.35 RG",
        "78 737 m 105 764 l 132 737 l 105 710 l h S",
        "Q",
        "BT",
        "/F2 18 Tf",
        "94 741 Td",
        f"({pdf_escape('PS')}) Tj",
        "ET",
        "BT",
        "/F1 6 Tf",
        "81 701 Td",
        f"({pdf_escape('PUBLIC SCHOOL')}) Tj",
        "ET",
        "BT",
        "/F2 28 Tf",
        "155 747 Td",
        f"({pdf_escape('P.S. PUBLIC SCHOOL')}) Tj",
        "ET",
        "BT",
        "/F1 12 Tf",
        "193 724 Td",
        f"({pdf_escape('Ganaur Road Bhurri (Sonipat) - 131101')}) Tj",
        "ET",
        "BT",
        "/F1 9 Tf",
        "440 762 Td",
        f"({pdf_escape('M. No.: 94162 93661')}) Tj",
        "0 -13 Td",
        f"({pdf_escape('Email: psbhurri@gmail.com')}) Tj",
        "ET",
        "BT",
        "/F1 9 Tf",
        "70 686 Td",
        f"({pdf_escape('Website: pspublicschool.com')}) Tj",
        "ET",
        "q",
        "0.05 0.18 0.35 RG",
        "1.4 w",
        "70 674 m 525 674 l S",
        "Q",
        "BT",
        "/F2 16 Tf",
        "210 630 Td",
        f"({pdf_escape(content['title'])}) Tj",
        "ET",
        "q",
        "0.05 0.18 0.35 RG",
        "1 w",
        "205 623 m 390 623 l S",
        "Q",
        "BT",
        "/F1 11 Tf",
        "78 590 Td",
        f"({pdf_escape('Date: ' + content['date'])}) Tj",
        "0 -20 Td",
        f"({pdf_escape('Admission No.: ' + content['admission_no'])}) Tj",
        "ET",
        "BT",
        "/F1 10 Tf",
        "395 590 Td",
        f"({pdf_escape('Ref. No.: ' + ref_no)}) Tj",
        "ET",
    ]

    y = 525
    for paragraph in content["paragraphs"]:
        wrapped_lines = wrap_pdf_text(paragraph, max_chars=84)
        commands.extend(["BT", "/F1 11 Tf", f"70 {y} Td"])
        first = True
        for line in wrapped_lines:
            if not first:
                commands.append("0 -18 Td")
                y -= 18
            commands.append(f"({pdf_escape(line)}) Tj")
            first = False
        commands.append("ET")
        y -= 36

    note_lines = [
        "Note: This digitally generated certificate is based on school records.",
        "For signed/stamped hard copy, please contact the school office.",
    ]
    y = max(y, 260)
    commands.extend(["BT", "/F1 10 Tf", f"70 {y} Td"])
    for index, line in enumerate(note_lines):
        if index:
            commands.append("0 -16 Td")
        commands.append(f"({pdf_escape(line)}) Tj")
    commands.append("ET")

    commands.extend(
        [
            "q",
            "0.05 0.18 0.35 RG",
            "1 w",
            "368 180 m 510 180 l S",
            "Q",
            "BT",
            "/F2 13 Tf",
            "395 197 Td",
            f"({pdf_escape('Naveen Kumar')}) Tj",
            "ET",
            "BT",
            "/F1 10 Tf",
            "410 164 Td",
            f"({pdf_escape('Principal')}) Tj",
            "0 -15 Td",
            f"({pdf_escape('Digitally signed')}) Tj",
            "0 -13 Td",
            f"({pdf_escape('Naveen Kumar, Principal')}) Tj",
            "ET",
            "BT",
            "/F1 8 Tf",
            "70 88 Td",
            f"({pdf_escape('This certificate is computer generated and valid for verification with school records.')}) Tj",
            "ET",
        ]
    )

    stream = "\n".join(commands)
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [5 0 R] /Count 1 >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            "/Contents 6 0 R >>"
        ),
        f"<< /Length {len(stream.encode('latin-1', errors='replace'))} >>\nstream\n{stream}\nendstream",
    ]

    pdf_parts = ["%PDF-1.4\n"]
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(sum(len(part.encode("latin-1", errors="replace")) for part in pdf_parts))
        pdf_parts.append(f"{index} 0 obj\n{body}\nendobj\n")

    xref_offset = sum(len(part.encode("latin-1", errors="replace")) for part in pdf_parts)
    pdf_parts.append(f"xref\n0 {len(objects) + 1}\n")
    pdf_parts.append("0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf_parts.append(f"{offset:010d} 00000 n \n")
    pdf_parts.append(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )

    with open(path, "wb") as pdf_file:
        pdf_file.write("".join(pdf_parts).encode("latin-1", errors="replace"))


def draw_certificate_pdf(path, student, certificate_type):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph

    content = certificate_content(student, certificate_type)
    width, height = A4
    pdf = canvas.Canvas(path, pagesize=A4)
    navy = colors.HexColor("#0b2f5b")

    pdf.setStrokeColor(navy)
    pdf.setLineWidth(1.6)
    pdf.rect(14 * mm, 12 * mm, width - 28 * mm, height - 24 * mm)

    if os.path.exists(SCHOOL_LOGO_PATH):
        pdf.drawImage(
            SCHOOL_LOGO_PATH,
            20 * mm,
            height - 43 * mm,
            27 * mm,
            27 * mm,
            preserveAspectRatio=True,
            mask="auto",
        )

    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 25)
    pdf.drawCentredString(width / 2, height - 25 * mm, "P.S. PUBLIC SCHOOL")
    pdf.setFont("Helvetica", 11)
    pdf.drawCentredString(width / 2, height - 32 * mm, "Ganaur Road Bhurri (Sonipat) - 131101")
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString(width / 2, height - 38 * mm, "Phone: +91 94162 93661 | Email: psbhurri@gmail.com | Website: pspublicschool.com")
    pdf.line(23 * mm, height - 47 * mm, width - 23 * mm, height - 47 * mm)

    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawCentredString(width / 2, height - 60 * mm, content["title"])
    pdf.line(width / 2 - 35 * mm, height - 63 * mm, width / 2 + 35 * mm, height - 63 * mm)

    y = height - 80 * mm
    pdf.setFont("Helvetica", 10.5)
    pdf.drawString(24 * mm, y, f"Date: {content['date']}")
    pdf.drawRightString(width - 24 * mm, y, f"Ref. No.: PSPS/{content['admission_no']}/{datetime.utcnow().strftime('%Y%m%d')}")
    y -= 8 * mm
    pdf.drawString(24 * mm, y, f"Admission No.: {content['admission_no']}")
    y -= 16 * mm

    body_style = ParagraphStyle(
        "certificate_body",
        fontName="Helvetica",
        fontSize=11,
        leading=18,
        textColor=colors.black,
        alignment=4,
    )
    for paragraph in content["paragraphs"]:
        p = Paragraph(paragraph, body_style)
        _, ph = p.wrap(width - 48 * mm, 120 * mm)
        p.drawOn(pdf, 24 * mm, y - ph)
        y -= ph + 8 * mm

    note_style = ParagraphStyle("note", fontName="Helvetica", fontSize=9, leading=13)
    note = Paragraph(
        "Note: This digitally generated certificate is based on school records. "
        "For signed/stamped hard copy, please contact the school office.",
        note_style,
    )
    _, nh = note.wrap(width - 48 * mm, 40 * mm)
    note.drawOn(pdf, 24 * mm, max(y - nh, 78 * mm))

    pdf.setStrokeColor(navy)
    pdf.line(width - 70 * mm, 45 * mm, width - 24 * mm, 45 * mm)
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(width - 65 * mm, 50 * mm, "Naveen Kumar")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(width - 60 * mm, 40 * mm, "Principal")
    pdf.drawString(width - 80 * mm, 35 * mm, "Digitally signed by Naveen Kumar, Principal")

    pdf.showPage()
    pdf.save()


def create_certificate_pdf(student, certificate_type):
    admission_no = clean_certificate_value(first_present(student, ["admission_no", "admissionNo"]), "student")
    safe_admission = re.sub(r"[^A-Za-z0-9_-]", "_", admission_no)
    safe_type = re.sub(r"[^A-Za-z0-9_-]", "_", certificate_type)
    filename = f"{safe_type}_certificate_{safe_admission}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.pdf"
    path = os.path.join(RESULTS_DIR, filename)
    try:
        draw_certificate_pdf(path, student, certificate_type)
    except Exception as exc:
        logger.exception("ReportLab certificate PDF failed, using raw PDF fallback: %s", exc)
        write_professional_certificate_pdf(path, student, certificate_type)
    return filename


def check_certificate_permission(student, certificate_type):
    exam_backend_url = (EXAM_BACKEND_URL or DEFAULT_EXAM_BACKEND_URL).rstrip("/")
    params = {
        "session": first_present(student, ["session"]),
        "class_name": first_present(student, ["class_name", "class"]),
        "admission_no": first_present(student, ["admission_no", "admissionNo"]),
        "student_id": first_present(student, ["student_id", "id", "_id"]),
        "certificate_type": certificate_type,
    }
    params = {key: value for key, value in params.items() if value and value != "-"}
    try:
        response = requests.get(
            f"{exam_backend_url}/certificate-access/check",
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("Unable to check certificate permission: %s", exc)
        return {"ok": False, "allowed": False, "reason": "server_error"}

    return {
        "ok": bool(data.get("success", True)),
        "allowed": bool(data.get("allowed")),
        "reason": data.get("reason") or "permission_required",
    }


def create_certificate_permission_application_pdf(student, certificate_title, certificate_type):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    admission_no = clean_certificate_value(first_present(student, ["admission_no", "admissionNo"]), "student")
    safe_admission = re.sub(r"[^A-Za-z0-9_-]", "_", admission_no)
    safe_type = re.sub(r"[^A-Za-z0-9_-]", "_", certificate_type)
    filename = f"certificate_permission_application_{safe_type}_{safe_admission}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.pdf"
    path = os.path.join(RESULTS_DIR, filename)

    width, height = A4
    pdf = canvas.Canvas(path, pagesize=A4)
    pdf.setStrokeColor(colors.HexColor("#0b2f5b"))
    pdf.setLineWidth(1.4)
    pdf.rect(14 * mm, 14 * mm, width - 28 * mm, height - 28 * mm)

    if os.path.exists(SCHOOL_LOGO_PATH):
        pdf.drawImage(SCHOOL_LOGO_PATH, 22 * mm, height - 42 * mm, 24 * mm, 24 * mm, preserveAspectRatio=True, mask="auto")

    pdf.setFillColor(colors.HexColor("#0b2f5b"))
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawCentredString(width / 2, height - 24 * mm, "P.S. PUBLIC SCHOOL")
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(width / 2, height - 31 * mm, "Ganaur Road Bhurri (Sonipat) - 131101")
    pdf.drawCentredString(width / 2, height - 37 * mm, "Phone: +91 94162 93661 | Email: psbhurri@gmail.com")
    pdf.line(22 * mm, height - 47 * mm, width - 22 * mm, height - 47 * mm)

    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawCentredString(width / 2, height - 60 * mm, "CERTIFICATE ISSUE PERMISSION APPLICATION")

    y = height - 78 * mm
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica", 10)
    today = datetime.utcnow().strftime("%d/%m/%Y")
    details = [
        ("Date", today),
        ("Requested Certificate", certificate_title),
        ("Student Name", first_present(student, ["name", "student_name"])),
        ("Admission No.", admission_no),
        ("Class", f"{first_present(student, ['class_name', 'class'])} {first_present(student, ['section'])}".replace(" -", "").strip()),
        ("Father Name", first_present(student, ["father_name", "fatherName", "father"])),
        ("Mother Name", first_present(student, ["mother_name", "motherName", "mother"])),
        ("Session", first_present(student, ["session"])),
    ]
    for label, value in details:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(26 * mm, y, f"{label}:")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(68 * mm, y, clean_certificate_value(value))
        y -= 8 * mm

    y -= 8 * mm
    body_lines = [
        "To",
        "The Principal / School Office",
        "P.S. Public School",
        "",
        f"Subject: Request for permission to issue {certificate_title}",
        "",
        "Respected Sir/Madam,",
        "",
        "I request the school office to kindly verify my record and grant permission",
        f"for issuing the above certificate through the school WhatsApp service.",
        "I understand that certificate issue is subject to office verification, fee/dues",
        "clearance, and school approval.",
        "",
        "Thank you.",
    ]
    pdf.setFont("Helvetica", 10)
    for line in body_lines:
        pdf.drawString(26 * mm, y, line)
        y -= 7 * mm

    y -= 10 * mm
    pdf.line(26 * mm, y, 78 * mm, y)
    pdf.line(width - 78 * mm, y, width - 26 * mm, y)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(26 * mm, y - 6 * mm, "Parent / Guardian Signature")
    pdf.drawString(width - 78 * mm, y - 6 * mm, "Office Approval")

    pdf.setFont("Helvetica-Oblique", 8)
    pdf.setFillColor(colors.HexColor("#555555"))
    pdf.drawCentredString(width / 2, 24 * mm, "This application is generated for school office permission and verification.")
    pdf.showPage()
    pdf.save()
    return filename


def send_certificate_permission_denied_flow(to_phone_number, language, student, certificate):
    certificate_type = certificate["certificate_type"]
    certificate_title = certificate["title"]["en"]
    send_text_message(
        to_phone_number,
        {
            "en": (
                f"{certificate['title'][language]} cannot be issued on WhatsApp right now.\n\n"
                "Permission is not approved for this student/certificate. Please contact the school office and submit the permission application.\n\n"
                "The application PDF will be sent in the next message."
            ),
            "hi": (
                f"{certificate['title'][language]} अभी WhatsApp पर issue नहीं हो सकता।\n\n"
                "इस student/certificate के लिए permission approved नहीं है। कृपया school office से संपर्क करें और permission application जमा करें।\n\n"
                "Application PDF अगले message में भेजा जाएगा।"
            ),
        }[language],
    )
    try:
        filename = create_certificate_permission_application_pdf(student, certificate_title, certificate_type)
        pdf_url = build_public_static_url(f"results/{filename}")
        if pdf_url:
            send_document_message(
                to_phone_number,
                pdf_url,
                f"{certificate_title} Permission Application.pdf",
                "Certificate Permission Application",
            )
    except Exception as exc:
        logger.exception("Failed to generate certificate permission application PDF: %s", exc)

    send_navigation_buttons_later(to_phone_number, language, "certificates", MEDIA_NAVIGATION_DELAY_SECONDS)


def send_certificate_flow(to_phone_number, language, student, certificate_id):
    certificate = CERTIFICATE_CATEGORIES.get(certificate_id)
    if not certificate:
        send_text_message(
            to_phone_number,
            {
                "en": "Certificate type not found. Please select again.",
                "hi": "प्रमाण पत्र प्रकार नहीं मिला। कृपया दोबारा चुनें।",
            }[language],
        )
        return

    certificate_type = certificate["certificate_type"]
    permission = check_certificate_permission(student, certificate_type)
    if not permission.get("allowed"):
        send_certificate_permission_denied_flow(to_phone_number, language, student, certificate)
        return

    if certificate_type == "tc":
        send_text_message(
            to_phone_number,
            {
                "en": (
                    "Transfer Certificate\n\n"
                    "For TC, please contact the school office directly. TC requires "
                    "office verification, fee clearance, and official signature/stamp.\n\n"
                    "Call: +91 94162 93661\n"
                    "WhatsApp: +91 94168 38604"
                ),
                "hi": (
                    "ट्रांसफर सर्टिफिकेट\n\n"
                    "TC के लिए कृपया सीधे स्कूल कार्यालय से संपर्क करें। TC के लिए "
                    "office verification, fee clearance और official signature/stamp जरूरी है।\n\n"
                    "फोन: +91 94162 93661\n"
                    "WhatsApp: +91 94168 38604"
                ),
            }[language],
        )
        send_navigation_buttons_later(to_phone_number, language, "certificates")
        return

    try:
        filename = create_certificate_pdf(student, certificate_type)
        certificate_url = build_public_static_url(f"results/{filename}")
        if not certificate_url:
            raise RuntimeError("Unable to build public certificate URL.")

        send_text_message(
            to_phone_number,
            {
                "en": f"{certificate['title'][language]} generated successfully. Sending PDF now.",
                "hi": f"{certificate['title'][language]} generate हो गया है। PDF भेजा जा रहा है।",
            }[language],
        )
        send_document_message(
            to_phone_number,
            certificate_url,
            f"{certificate['title']['en']}.pdf",
            certificate["title"][language],
        )
        send_navigation_buttons_later(to_phone_number, language, "certificates", MEDIA_NAVIGATION_DELAY_SECONDS)
    except Exception as exc:
        logger.exception("Failed to generate certificate: %s", exc)
        send_text_message(
            to_phone_number,
            {
                "en": "Certificate PDF could not be generated right now. Please try again later or contact the office.",
                "hi": "Certificate PDF अभी generate नहीं हो पाया। कृपया बाद में प्रयास करें या कार्यालय से संपर्क करें।",
            }[language],
        )
        send_navigation_buttons_later(to_phone_number, language, "certificates")


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


def set_menu_context(to_phone_number, current_menu, previous_menu="main"):
    MENU_CONTEXT_BY_USER[to_phone_number] = {
        "current": current_menu,
        "previous": previous_menu,
    }


def send_navigation_buttons(to_phone_number, language, previous_menu="main"):
    set_menu_context(to_phone_number, "navigation", previous_menu)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": {
                    "en": "Where would you like to go next?",
                    "hi": "अब आप कहां जाना चाहते हैं?",
                }[language]
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "nav_main_menu",
                            "title": {"en": "Main Menu", "hi": "मुख्य मेनू"}[language],
                        },
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "nav_previous_menu",
                            "title": {"en": "Previous Menu", "hi": "पिछला मेनू"}[language],
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


def send_navigation_buttons_later(to_phone_number, language, previous_menu="main", delay_seconds=None):
    delay = NAVIGATION_DELAY_SECONDS if delay_seconds is None else max(float(delay_seconds), 0.0)
    return run_later(delay, send_navigation_buttons, to_phone_number, language, previous_menu)


def clear_student_auth_timers(to_phone_number):
    timers = STUDENT_AUTH_TIMERS_BY_USER.pop(to_phone_number, [])
    for timer in timers:
        try:
            timer.cancel()
        except Exception:
            pass


def send_student_session_expiring_warning(to_phone_number, language):
    if to_phone_number not in STUDENT_AUTH_BY_USER:
        return

    send_text_message(
        to_phone_number,
        {
            "en": (
                "Your verified student session is expiring soon.\n\n"
                "After it expires, please verify again with admission number and DOB to use Student or Academic Services.\n\n"
                "Thank you for using P.S. Public School WhatsApp services.\n\n"
                "Regards,\n"
                "IT Department\n"
                "P.S. Public School"
            ),
            "hi": (
                "आपका verified student session जल्द expire होने वाला है।\n\n"
                "Expire होने के बाद Student या Academic Services के लिए admission number और DOB से फिर verify करें।\n\n"
                "P.S. Public School WhatsApp services उपयोग करने के लिए धन्यवाद।\n\n"
                "Regards,\n"
                "IT Department\n"
                "P.S. Public School"
            ),
        }[language],
    )


def expire_student_auth_session(to_phone_number, language):
    if to_phone_number not in STUDENT_AUTH_BY_USER:
        return

    STUDENT_AUTH_BY_USER.pop(to_phone_number, None)
    STUDENT_AUTH_TIMERS_BY_USER.pop(to_phone_number, None)
    send_text_message(
        to_phone_number,
        {
            "en": (
                "Your verified student session has ended.\n\n"
                "Please verify again with admission number and DOB to use Student or Academic Services.\n\n"
                "Thank you for using P.S. Public School WhatsApp services.\n\n"
                "Regards,\n"
                "IT Department\n"
                "P.S. Public School"
            ),
            "hi": (
                "आपका verified student session समाप्त हो गया है।\n\n"
                "Student या Academic Services उपयोग करने के लिए admission number और DOB से फिर verify करें।\n\n"
                "P.S. Public School WhatsApp services उपयोग करने के लिए धन्यवाद।\n\n"
                "Regards,\n"
                "IT Department\n"
                "P.S. Public School"
            ),
        }[language],
    )


def schedule_student_auth_expiry(to_phone_number, language):
    clear_student_auth_timers(to_phone_number)
    timers = []

    if STUDENT_AUTH_TIMEOUT_SECONDS <= 0:
        STUDENT_AUTH_TIMERS_BY_USER[to_phone_number] = timers
        return

    warning_delay = STUDENT_AUTH_TIMEOUT_SECONDS - STUDENT_AUTH_WARNING_SECONDS
    if warning_delay <= 0 and STUDENT_AUTH_TIMEOUT_SECONDS > 30:
        warning_delay = max(STUDENT_AUTH_TIMEOUT_SECONDS - 30, 1)

    if 0 < warning_delay < STUDENT_AUTH_TIMEOUT_SECONDS:
        timers.append(
            run_later(warning_delay, send_student_session_expiring_warning, to_phone_number, language)
        )

    timers.append(run_later(STUDENT_AUTH_TIMEOUT_SECONDS, expire_student_auth_session, to_phone_number, language))

    STUDENT_AUTH_TIMERS_BY_USER[to_phone_number] = timers


def refresh_student_auth_session(to_phone_number, language):
    auth = STUDENT_AUTH_BY_USER.get(to_phone_number)
    if not auth:
        return

    auth["last_activity_at"] = datetime.utcnow().isoformat()
    auth["language"] = language
    schedule_student_auth_expiry(to_phone_number, language)


def safe_reply_to_user(to_phone_number, message_text):
    try:
        reply_to_user(to_phone_number, message_text)
    except Exception as exc:
        logger.exception("Unexpected reply error for %s: %s", to_phone_number, exc)
        send_text_message(
            to_phone_number,
            "Sorry, something went wrong. Please send hi to restart.",
        )


def send_service_list_message(to_phone_number, language):
    set_menu_context(to_phone_number, "main", "main")
    rows = [
        {
            "id": service_id,
            "title": service["title"][language],
            "description": service["description"][language],
        }
        for service_id in MAIN_SERVICE_IDS
        for service in [SERVICES[service_id]]
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
                    "en": "Please select a service:",
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
                        "title": {"en": "Main Menu", "hi": "मुख्य मेनू"}[language],
                        "rows": rows,
                    }
                ],
            },
        },
    }
    return send_whatsapp_payload(payload)


def send_admission_services_list_message(to_phone_number, language):
    set_menu_context(to_phone_number, "admission", "main")
    rows = [
        {
            "id": service_id,
            "title": SERVICES[service_id]["title"][language],
            "description": SERVICES[service_id]["description"][language],
        }
        for service_id in ADMISSION_SERVICE_IDS
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
                "text": {"en": "Admission & Information", "hi": "प्रवेश और जानकारी"}[language],
            },
            "body": {
                "text": {
                    "en": "Please select an admission or school information service.",
                    "hi": "कृपया प्रवेश से जुड़ी सेवा चुनें।",
                }[language]
            },
            "footer": {"text": "P.S. Public School"},
            "action": {
                "button": {"en": "View Admission", "hi": "प्रवेश देखें"}[language],
                "sections": [
                    {
                        "title": {"en": "Admission & Information", "hi": "प्रवेश और जानकारी"}[language],
                        "rows": rows,
                    }
                ],
            },
        },
    }
    return send_whatsapp_payload(payload)


def send_other_services_list_message(to_phone_number, language):
    set_menu_context(to_phone_number, "academic", "main")
    rows = [
        {
            "id": category_id,
            "title": category["title"][language],
            "description": category["description"][language],
        }
        for category_id in ACADEMIC_CATEGORY_IDS
        for category in [OTHER_SERVICE_CATEGORIES[category_id]]
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
                "text": {"en": "Student Services & Accounts", "hi": "विद्यार्थी सेवाएं और खाते"}[language],
            },
            "body": {
                "text": {
                    "en": "Please select a student service or accounts option.",
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
                "button": {"en": "View Services", "hi": "सेवाएं देखें"}[language],
                "sections": [
                    {
                        "title": {"en": "Student Services", "hi": "विद्यार्थी सेवाएं"}[language],
                        "rows": rows,
                    }
                ],
            },
        },
    }
    return send_whatsapp_payload(payload)


def send_exam_services_list_message(to_phone_number, language):
    set_menu_context(to_phone_number, "exam", "main")
    rows = [
        {
            "id": category_id,
            "title": OTHER_SERVICE_CATEGORIES[category_id]["title"][language],
            "description": OTHER_SERVICE_CATEGORIES[category_id]["description"][language],
        }
        for category_id in EXAM_CATEGORY_IDS
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
                "text": {"en": "Academic Services", "hi": "शैक्षणिक सेवाएं"}[language],
            },
            "body": {
                "text": {
                    "en": "Please select an academic service.",
                    "hi": "कृपया परीक्षा से जुड़ी सेवा चुनें।",
                }[language]
            },
            "footer": {"text": "P.S. Public School"},
            "action": {
                "button": {"en": "View Academic", "hi": "शैक्षणिक देखें"}[language],
                "sections": [
                    {
                        "title": {"en": "Academic Services", "hi": "शैक्षणिक सेवाएं"}[language],
                        "rows": rows,
                    }
                ],
            },
        },
    }
    return send_whatsapp_payload(payload)


def send_certificate_list_message(to_phone_number, language):
    set_menu_context(to_phone_number, "certificates", "academic")
    rows = [
        {
            "id": certificate_id,
            "title": certificate["title"][language],
            "description": certificate["description"][language],
        }
        for certificate_id, certificate in CERTIFICATE_CATEGORIES.items()
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
                "text": {"en": "Certificates", "hi": "प्रमाण पत्र"}[language],
            },
            "body": {
                "text": {
                    "en": "Please select the certificate you need.",
                    "hi": "कृपया जिस प्रमाण पत्र की जरूरत है उसे चुनें।",
                }[language]
            },
            "footer": {
                "text": {
                    "en": "P.S. Public School",
                    "hi": "पी.एस. पब्लिक स्कूल",
                }[language]
            },
            "action": {
                "button": {"en": "View Certificates", "hi": "प्रमाण पत्र देखें"}[language],
                "sections": [
                    {
                        "title": {"en": "Certificate Types", "hi": "प्रमाण पत्र प्रकार"}[language],
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
    send_navigation_buttons_later(to_phone_number, language, "admission", 7)


def send_fee_structure_flow(to_phone_number, language):
    send_text_message(to_phone_number, FEE_OVERVIEW_MESSAGE[language])
    run_later(1.5, send_text_message, to_phone_number, FEE_STRUCTURE_MESSAGE[language])
    send_navigation_buttons_later(to_phone_number, language, "admission", 4)


def send_transport_facility_flow(to_phone_number, language):
    send_text_message(to_phone_number, TRANSPORT_OVERVIEW_MESSAGE[language])
    run_later(1.5, send_text_message, to_phone_number, TRANSPORT_FEE_MESSAGE[language])
    send_navigation_buttons_later(to_phone_number, language, "admission", 4)


def start_student_details_flow(to_phone_number, language):
    STUDENT_DETAIL_SESSIONS[to_phone_number] = {
        "step": "awaiting_username",
        "language": language,
        "after_login": "show_student_details",
    }
    send_text_message(to_phone_number, STUDENT_LOGIN_TEXT["ask_username"][language])


def start_academic_services_login_flow(to_phone_number, language, after_login="show_academic_services"):
    STUDENT_DETAIL_SESSIONS[to_phone_number] = {
        "step": "awaiting_username",
        "language": language,
        "after_login": after_login,
    }
    send_text_message(
        to_phone_number,
        {
            "en": (
                "Student Verification\n\n"
                "For student privacy, please verify once before using this service.\n\n"
                "Please send the student's admission number."
            ),
            "hi": (
                "Student Verification\n\n"
                "विद्यार्थी की गोपनीयता के लिए यह service उपयोग करने से पहले "
                "कृपया एक बार verification करें।\n\n"
                "कृपया विद्यार्थी का admission number भेजें।"
            ),
        }[language],
    )


def start_other_services_login_flow(to_phone_number, language):
    start_academic_services_login_flow(to_phone_number, language, "show_academic_services")


def normalize_dob_for_exam_login(raw_password):
    value = str(raw_password or "").strip()
    digits = re.sub(r"\D", "", value)
    if len(digits) == 8:
        return f"{digits[0:2]}/{digits[2:4]}/{digits[4:8]}"

    normalized = value.replace("-", "/").replace(".", "/")
    return normalized


def add_valid_dob(candidates, day, month, year):
    try:
        day_i = int(day)
        month_i = int(month)
        year_i = int(year)
        parsed = date(year_i, month_i, day_i)
    except (TypeError, ValueError):
        return

    candidates.update(
        {
            parsed.strftime("%d/%m/%Y"),
            parsed.strftime("%m/%d/%Y"),
            parsed.strftime("%d-%m-%Y"),
            parsed.strftime("%m-%d-%Y"),
            parsed.strftime("%Y-%m-%d"),
            parsed.strftime("%Y/%m/%d"),
            parsed.strftime("%d%m%Y"),
            parsed.strftime("%m%d%Y"),
            parsed.strftime("%Y%m%d"),
        }
    )


def dob_canonical_values(raw_dob):
    value = str(raw_dob or "").strip()
    canonical = set()
    if not value:
        return canonical

    digits = re.sub(r"\D", "", value)
    if len(digits) == 8:
        possible_parts = [
            (digits[0:2], digits[2:4], digits[4:8]),  # DDMMYYYY
            (digits[2:4], digits[0:2], digits[4:8]),  # MMDDYYYY
            (digits[6:8], digits[4:6], digits[0:4]),  # YYYYMMDD
        ]
        for day, month, year in possible_parts:
            try:
                canonical.add(date(int(year), int(month), int(day)).isoformat())
            except ValueError:
                pass

    parts = re.split(r"[\/\-.]", value)
    if len(parts) == 3 and all(part.strip().isdigit() for part in parts):
        first, second, third = [part.strip() for part in parts]
        if len(first) == 4:
            possible_parts = [(third, second, first)]  # YYYY-MM-DD
        else:
            year = third
            if len(year) == 2:
                year = f"20{year}" if int(year) <= 40 else f"19{year}"
            possible_parts = [
                (first, second, year),  # DD/MM/YYYY
                (second, first, year),  # MM/DD/YYYY
            ]

        for day, month, year in possible_parts:
            try:
                canonical.add(date(int(year), int(month), int(day)).isoformat())
            except ValueError:
                pass

    return canonical


def dob_candidate_values(raw_dob):
    value = str(raw_dob or "").strip()
    if not value:
        return []

    candidates = {value, value.replace("-", "/").replace(".", "/")}
    for canonical in dob_canonical_values(value):
        year, month, day = canonical.split("-")
        add_valid_dob(candidates, day, month, year)

    digits = re.sub(r"\D", "", value)

    if len(digits) == 8:
        first = digits[0:2]
        second = digits[2:4]
        year = digits[4:8]
        candidates.update(
            {
                f"{first}/{second}/{year}",
                f"{second}/{first}/{year}",
                f"{first}-{second}-{year}",
                f"{second}-{first}-{year}",
            }
        )

    for separator in ("/", "-"):
        parts = value.replace(".", separator).replace("/", separator).replace("-", separator).split(separator)
        if len(parts) == 3:
            first, second, year = [part.strip() for part in parts]
            if first.isdigit() and second.isdigit() and year.isdigit():
                first = first.zfill(2)
                second = second.zfill(2)
                if len(year) == 2:
                    year = f"20{year}" if int(year) <= 40 else f"19{year}"
                candidates.update(
                    {
                        f"{first}/{second}/{year}",
                        f"{second}/{first}/{year}",
                        f"{first}-{second}-{year}",
                        f"{second}-{first}-{year}",
                    }
                )

    return list(candidates)


def dob_match(user_dob, saved_dob):
    user_canonical = dob_canonical_values(user_dob)
    saved_canonical = dob_canonical_values(saved_dob)
    if user_canonical and saved_canonical:
        return bool(user_canonical & saved_canonical)

    user_candidates = {item.lower() for item in dob_candidate_values(user_dob)}
    saved_candidates = {item.lower() for item in dob_candidate_values(saved_dob)}
    return bool(user_candidates & saved_candidates)


def get_student_login_url():
    configured_url = (EXAM_BACKEND_STUDENT_LOGIN_URL or "").strip()
    if not configured_url:
        return DEFAULT_EXAM_BACKEND_STUDENT_LOGIN_URL

    bad_placeholders = {
        "YOUR-EXAM-BACKEND",
        "student-login-api",
    }
    if any(marker in configured_url for marker in bad_placeholders):
        logger.warning(
            "Ignoring invalid EXAM_BACKEND_STUDENT_LOGIN_URL=%s; using default /login endpoint.",
            configured_url,
        )
        return DEFAULT_EXAM_BACKEND_STUDENT_LOGIN_URL

    return configured_url


def get_exam_backend_base_url():
    configured_base_url = (EXAM_BACKEND_URL or "").strip().rstrip("/")
    if configured_base_url and "YOUR-EXAM-BACKEND" not in configured_base_url:
        return configured_base_url

    student_login_url = get_student_login_url()
    if "/login" in student_login_url:
        return student_login_url.rsplit("/login", 1)[0].rstrip("/")

    return DEFAULT_EXAM_BACKEND_URL


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
        if not merged.get("roll") and student.get("rollno"):
            merged["roll"] = student.get("rollno")
        if not merged.get("rollno") and merged.get("roll"):
            merged["rollno"] = merged.get("roll")
        if not merged.get("class_name") and student.get("class"):
            merged["class_name"] = student.get("class")
        return merged

    return student


def fetch_student_details_from_student_backend(username, password):
    admission_no = str(username or "").strip()
    student_backend_url = (STUDENT_BACKEND_URL or DEFAULT_STUDENT_BACKEND_URL).rstrip("/")

    try:
        response = requests.get(f"{student_backend_url}/students", timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.error("Student backend fallback request failed: %s", exc)
        return {"ok": False, "reason": "server_error"}
    except ValueError:
        logger.error("Student backend fallback returned non-JSON response.")
        return {"ok": False, "reason": "server_error"}

    students = data.get("students") if isinstance(data, dict) else data
    if not isinstance(students, list):
        logger.error("Student backend fallback returned unexpected payload: %s", data)
        return {"ok": False, "reason": "server_error"}

    for student in students:
        if not isinstance(student, dict):
            continue

        saved_admission_no = str(student.get("admission_no", "")).strip()
        saved_dob = str(student.get("dob", "")).strip()
        if saved_admission_no == admission_no and dob_match(password, saved_dob):
            return {"ok": True, "student": student}

    return {"ok": False, "reason": "login_failed"}


def fetch_student_details(username, password):
    student_login_url = get_student_login_url()
    if not student_login_url:
        return fetch_student_details_from_student_backend(username, password)

    response = None
    for dob_value in dob_candidate_values(password):
        payload = {
            "username": str(username or "").strip(),
            "password": dob_value,
        }
        try:
            response = requests.post(
                student_login_url,
                json=payload,
                timeout=15,
            )
        except requests.RequestException as exc:
            logger.error("Student login request failed: %s", exc)
            return fetch_student_details_from_student_backend(username, password)

        if response.status_code not in {401, 403, 404}:
            break

        logger.warning("Student login failed for DOB variant %s: %s", dob_value, response.text)

    if response is None or response.status_code in {401, 403, 404}:
        return fetch_student_details_from_student_backend(username, password)

    if not response.ok:
        logger.error(
            "Student login backend returned %s: %s",
            response.status_code,
            response.text,
        )
        return fetch_student_details_from_student_backend(username, password)

    try:
        data = response.json()
    except ValueError:
        logger.error("Student login backend returned non-JSON response.")
        return fetch_student_details_from_student_backend(username, password)

    if data.get("success") is False or data.get("error"):
        logger.warning("Student login backend rejected credentials: %s", data)
        return fetch_student_details_from_student_backend(username, password)

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
    student = enrich_student_with_backend_record(student)
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


def get_student_photo_url(student):
    photo_url = str(student.get("photo_url") or "").strip()
    if not photo_url:
        return ""

    if photo_url.startswith("http://") or photo_url.startswith("https://"):
        return photo_url

    student_backend_url = (STUDENT_BACKEND_URL or DEFAULT_STUDENT_BACKEND_URL).rstrip("/")
    if photo_url.startswith("/"):
        return f"{student_backend_url}{photo_url}"

    return f"{student_backend_url}/{photo_url}"


def enrich_student_with_backend_record(student):
    admission_no = str(student.get("admission_no") or "").strip()
    if not admission_no:
        return student

    current_photo = str(student.get("photo_url") or "").strip()
    current_dob = str(student.get("dob") or "").strip()
    if current_photo and current_dob:
        return student

    student_backend_url = (STUDENT_BACKEND_URL or DEFAULT_STUDENT_BACKEND_URL).rstrip("/")
    try:
        response = requests.get(f"{student_backend_url}/students", timeout=20)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("Unable to enrich student from student backend: %s", exc)
        return student

    students = data.get("students") if isinstance(data, dict) else data
    if not isinstance(students, list):
        return student

    for row in students:
        if not isinstance(row, dict):
            continue
        if str(row.get("admission_no") or "").strip() == admission_no:
            merged = dict(row)
            merged.update({key: value for key, value in student.items() if value not in {None, ""}})
            if not merged.get("photo_url") and row.get("photo_url"):
                merged["photo_url"] = row.get("photo_url")
            if not merged.get("dob") and row.get("dob"):
                merged["dob"] = row.get("dob")
            return merged

    return student


def send_student_photo_if_available(to_phone_number, student, language):
    photo_url = get_student_photo_url(student)
    if not photo_url:
        return False

    caption = {
        "en": f"Student Photo - {first_present(student, ['name', 'student_name'])}",
        "hi": f"विद्यार्थी फोटो - {first_present(student, ['name', 'student_name'])}",
    }[language]
    return send_image_message(to_phone_number, photo_url, caption)


def send_student_details_response(to_phone_number, student, language):
    send_student_photo_if_available(to_phone_number, student, language)
    send_text_message(to_phone_number, format_student_details(student, language))
    send_student_idcard_pdf_if_possible(to_phone_number, student, language)


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
        after_login = session.get("after_login", "show_student_details")
        STUDENT_DETAIL_SESSIONS.pop(to_phone_number, None)
        run_later(
            0.1,
            process_student_details_login,
            to_phone_number,
            username,
            password,
            language,
            after_login,
        )
        return True

    STUDENT_DETAIL_SESSIONS.pop(to_phone_number, None)
    return False


def process_student_details_login(to_phone_number, username, password, language, after_login):
    try:
        result = fetch_student_details(username, password)
    except Exception as exc:
        logger.exception("Unexpected student details error: %s", exc)
        send_text_message(to_phone_number, STUDENT_LOGIN_TEXT["server_error"][language])
        return

    if not result["ok"]:
        send_text_message(
            to_phone_number,
            STUDENT_LOGIN_TEXT[result["reason"]][language],
        )
        return

    STUDENT_AUTH_BY_USER[to_phone_number] = {
        "student": result["student"],
        "language": language,
        "verified_at": datetime.utcnow().isoformat(),
        "last_activity_at": datetime.utcnow().isoformat(),
    }
    schedule_student_auth_expiry(to_phone_number, language)

    if after_login in {"show_other_services", "show_academic_services", "show_exam_services"}:
        student_name = first_present(result["student"], ["name", "student_name"])
        admission_no = first_present(result["student"], ["admission_no", "admissionNo"])
        class_name = first_present(result["student"], ["class_name", "class"])
        service_label = {
            "show_exam_services": {"en": "Academic Services", "hi": "Academic Services"},
        }.get(
            after_login,
            {"en": "Student Services & Accounts", "hi": "Student Services & Accounts"},
        )[language]
        send_text_message(
            to_phone_number,
            {
                "en": (
                    "Verification successful.\n\n"
                    f"Student: {student_name}\n"
                    f"Admission No.: {admission_no}\n"
                    f"Class: {class_name}\n\n"
                    f"You can now use {service_label} without logging in again."
                ),
                "hi": (
                    "Verification सफल रहा।\n\n"
                    f"विद्यार्थी: {student_name}\n"
                    f"Admission No.: {admission_no}\n"
                    f"कक्षा: {class_name}\n\n"
                    f"अब आप दोबारा login किए बिना {service_label} उपयोग कर सकते हैं।"
                ),
            }[language],
        )
        if after_login == "show_exam_services":
            send_exam_services_list_message(to_phone_number, language)
        else:
            send_other_services_list_message(to_phone_number, language)
        return

    if after_login == "show_results_exams":
        send_results_exams_flow(to_phone_number, language, result["student"])
        return

    try:
        details_message = format_student_details(result["student"], language)
    except Exception as exc:
        logger.exception("Failed to format student details: %s", exc)
        send_text_message(to_phone_number, STUDENT_LOGIN_TEXT["server_error"][language])
        return

    send_student_photo_if_available(to_phone_number, result["student"], language)
    send_text_message(to_phone_number, details_message)
    send_student_idcard_pdf_if_possible(to_phone_number, result["student"], language)


def draw_student_idcard_pdf(path, student):
    """Generate a professional ID-card style PDF with school logo, student photo, and details."""
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    width, height = A4
    pdf = canvas.Canvas(path, pagesize=A4)
    navy = colors.HexColor("#0b2f5b")
    light_bg = colors.HexColor("#f4f7fb")

    def clean(value, fallback="-"):
        text = str(value or "").strip()
        return fallback if not text or text.lower() in {"nan", "none", "null"} else text

    name = clean(first_present(student, ["name", "student_name"]))
    admission_no = clean(first_present(student, ["admission_no", "admissionNo"]))
    class_name = clean(first_present(student, ["class_name", "class"]))
    section = clean(first_present(student, ["section"]), "")
    class_label = f"{class_name}{' - ' + section if section else ''}"
    roll = clean(first_present(student, ["roll", "rollno", "roll_no"]), "")
    father = clean(first_present(student, ["father_name", "fatherName"]))
    mother = clean(first_present(student, ["mother_name", "motherName"]), "")
    dob = clean(first_present(student, ["dob", "date_of_birth", "dateOfBirth"]), "")
    mobile = clean(first_present(student, ["mobile", "phone", "contact", "parent_mobile", "parentMobile"]), "")
    address = clean(first_present(student, ["address", "student_address", "studentAddress"]), "")
    session = clean(first_present(student, ["session"]), "")

    # Card dimensions (credit-card-like: 85mm x 54mm, centered on A4)
    card_w = 85 * mm
    card_h = 54 * mm
    card_x = (width - card_w) / 2
    card_y = (height - card_h) / 2

    # Card background
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(navy)
    pdf.setLineWidth(1.2)
    pdf.roundRect(card_x, card_y, card_w, card_h, 3 * mm, stroke=1, fill=1)

    # Top navy header bar
    header_h = 12 * mm
    pdf.setFillColor(navy)
    pdf.setStrokeColor(navy)
    pdf.rect(card_x, card_y + card_h - header_h, card_w, header_h, stroke=0, fill=1)

    # School name in header
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawCentredString(card_x + card_w / 2, card_y + card_h - 5.5 * mm, "P.S. PUBLIC SCHOOL")
    pdf.setFont("Helvetica", 5.5)
    pdf.drawCentredString(card_x + card_w / 2, card_y + card_h - 10 * mm, "Ganaur Road Bhurri, Sonipat - 131101")

    # ID Card title below header
    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(card_x + card_w / 2, card_y + card_h - header_h - 5 * mm, "STUDENT IDENTITY CARD")

    # Separator line
    pdf.setStrokeColor(navy)
    pdf.setLineWidth(0.4)
    pdf.line(card_x + 4 * mm, card_y + card_h - header_h - 7.5 * mm,
             card_x + card_w - 4 * mm, card_y + card_h - header_h - 7.5 * mm)

    # Photo area (right side, passport size ~ 22mm x 28mm)
    photo_x = card_x + card_w - 26 * mm
    photo_y = card_y + 6 * mm
    photo_w = 22 * mm
    photo_h = 28 * mm

    pdf.setStrokeColor(navy)
    pdf.setLineWidth(0.5)
    pdf.rect(photo_x, photo_y, photo_w, photo_h)

    photo_url = get_student_photo_url(student)
    if photo_url:
        try:
            response = requests.get(photo_url, timeout=10)
            response.raise_for_status()
            image_data = ImageReader(BytesIO(response.content))
            pdf.drawImage(image_data, photo_x + 1 * mm, photo_y + 1 * mm,
                          photo_w - 2 * mm, photo_h - 2 * mm,
                          preserveAspectRatio=True, anchor="c")
        except Exception as exc:
            logger.warning("Unable to draw student photo in ID card PDF: %s", exc)
            pdf.setFont("Helvetica", 5)
            pdf.drawCentredString(photo_x + photo_w / 2, photo_y + photo_h / 2, "PHOTO")

    # School logo (small, top-left area)
    if os.path.exists(SCHOOL_LOGO_PATH):
        try:
            pdf.drawImage(SCHOOL_LOGO_PATH,
                          card_x + 3 * mm, card_y + card_h - header_h - 15 * mm,
                          9 * mm, 9 * mm, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    # Student details (left side)
    detail_x = card_x + 4 * mm
    detail_y = card_y + card_h - header_h - 16 * mm
    line_h = 4.2 * mm

    pdf.setFillColor(colors.black)
    details = [
        ("Name", name),
        ("Adm. No.", admission_no),
        ("Class", class_label),
        ("Roll No.", roll),
        ("DOB", dob),
        ("Father", father),
        ("Mobile", mobile),
    ]

    for label, value in details:
        pdf.setFont("Helvetica-Bold", 5.2)
        pdf.drawString(detail_x, detail_y, f"{label}:")
        pdf.setFont("Helvetica", 5.5)
        # Truncate long values
        display = str(value)[:28]
        pdf.drawString(detail_x + 14 * mm, detail_y, display)
        detail_y -= line_h

    # Bottom bar with validity and authorized signature
    pdf.setFillColor(navy)
    pdf.setStrokeColor(navy)
    pdf.rect(card_x, card_y, card_w, 7 * mm, stroke=0, fill=1)

    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica", 4.5)
    pdf.drawString(card_x + 3 * mm, card_y + 2.5 * mm, f"Session: {session}")
    pdf.drawString(card_x + 30 * mm, card_y + 2.5 * mm, "Valid up to: March 2027")
    pdf.setFont("Helvetica-Bold", 4.8)
    pdf.drawRightString(card_x + card_w - 3 * mm, card_y + 2.5 * mm, "Principal")

    # Footer note
    pdf.setFillColor(colors.HexColor("#555555"))
    pdf.setFont("Helvetica", 4.2)
    pdf.drawCentredString(card_x + card_w / 2, card_y + card_h + 4 * mm,
                          "If found, please return to P.S. Public School. This is a digitally generated card.")

    pdf.showPage()
    pdf.save()


def create_student_idcard_pdf(student):
    """Save the ID card PDF to RESULTS_DIR and return the filename."""
    admission_no = clean_certificate_value(
        first_present(student, ["admission_no", "admissionNo"]), "student"
    )
    safe_admission = re.sub(r"[^A-Za-z0-9_-]", "_", admission_no)
    filename = f"idcard_{safe_admission}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.pdf"
    path = os.path.join(RESULTS_DIR, filename)
    draw_student_idcard_pdf(path, student)
    return filename


def send_student_idcard_pdf_if_possible(to_phone_number, student, language):
    """Generate and send the student ID card PDF via WhatsApp, fall back gracefully."""
    try:
        filename = create_student_idcard_pdf(student)
        pdf_url = build_public_static_url(f"results/{filename}")
        if not pdf_url:
            raise RuntimeError("Unable to build public ID card PDF URL.")

        send_text_message(
            to_phone_number,
            {
                "en": "Student ID Card has been generated. Sending PDF now.",
                "hi": "Student ID Card generate हो गया है। PDF भेजा जा रहा है।",
            }[language],
        )
        send_document_message(
            to_phone_number,
            pdf_url,
            "P.S. Public School Student ID Card.pdf",
            {
                "en": "Student ID Card - P.S. Public School",
                "hi": "Student ID Card - पी.एस. पब्लिक स्कूल",
            }[language],
        )
        send_navigation_buttons_later(to_phone_number, language, "academic", MEDIA_NAVIGATION_DELAY_SECONDS)
    except Exception as exc:
        logger.exception("Failed to generate/send student ID card PDF: %s", exc)
        send_text_message(
            to_phone_number,
            {
                "en": "Student ID Card PDF could not be generated. Please contact the school office for a physical ID card.",
                "hi": "Student ID Card PDF generate नहीं हो पाया। Physical ID card के लिए कृपया school office से संपर्क करें।",
            }[language],
        )
        send_navigation_buttons_later(to_phone_number, language, "academic")


def fetch_library_records(admission_no):
    """Fetch library records for a student from the library backend."""
    try:
        url = f"{LIBRARY_BACKEND_URL}/api/records/student/{admission_no}"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("success"):
            return {"ok": True, "records": data.get("records", []), "admission_no": data.get("admission_no")}
        return {"ok": False, "records": [], "error": data.get("error", "No records found")}
    except requests.RequestException as exc:
        logger.error("Library records fetch failed for %s: %s", admission_no, exc)
        return {"ok": False, "records": [], "error": "library_backend_unavailable"}
    except ValueError:
        logger.error("Library backend returned non-JSON for %s", admission_no)
        return {"ok": False, "records": [], "error": "library_backend_unavailable"}


def format_library_records(student, records, language):
    """Format library records into a readable WhatsApp message."""
    student_name = first_present(student, ["name", "student_name"])
    admission_no = first_present(student, ["admission_no", "admissionNo"])

    title = {
        "en": "Library Records",
        "hi": "लाइब्रेरी रिकॉर्ड",
    }[language]

    lines = [
        title,
        "",
        f"Student: {student_name}",
        f"Admission No.: {admission_no}",
        "",
    ]

    if not records:
        lines.append(
            {
                "en": "No library records found.",
                "hi": "कोई लाइब्रेरी रिकॉर्ड नहीं मिला।",
            }[language]
        )
        return "\n".join(lines)

    total_fine = 0
    for idx, rec in enumerate(records, start=1):
        code = str(rec.get("code", "-"))
        book = str(rec.get("bookName", "-"))
        status = str(rec.get("status", "")).upper()
        issue_date = str(rec.get("issueDate", "-"))
        due_date = str(rec.get("dueDate", "-"))
        return_date = str(rec.get("returnDate", "-"))
        fine = int(rec.get("fine", 0) or 0)
        fine_reason = str(rec.get("fine_reason", ""))

        total_fine += fine

        status_label = {
            "en": {
                "ISSUED": "Issued",
                "RETURNED": "Returned",
                "LOST": "Lost",
                "DAMAGED": "Damaged",
                "MISPLACED": "Misplaced",
            },
            "hi": {
                "ISSUED": "जारी",
                "RETURNED": "वापस",
                "LOST": "खोया",
                "DAMAGED": "क्षतिग्रस्त",
                "MISPLACED": "गुम",
            },
        }[language].get(status, status)

        lines.append(f"{idx}. {book}")
        lines.append(f"   Code: {code} | Status: {status_label}")
        if issue_date and issue_date != "-":
            lines.append(f"   Issued: {issue_date}")
        if due_date and due_date != "-":
            lines.append(f"   Due: {due_date}")
        if return_date and return_date != "-":
            lines.append(f"   Returned: {return_date}")
        if fine > 0:
            reason_text = f" ({fine_reason})" if fine_reason else ""
            lines.append(f"   Fine: Rs. {fine}{reason_text}")
        lines.append("")

    if total_fine > 0:
        lines.append(
            {
                "en": f"Total Pending Fine: Rs. {total_fine}",
                "hi": f"कुल लंबित जुर्माना: Rs. {total_fine}",
            }[language]
        )
        lines.append(
            {
                "en": "Please clear pending fines at the school library.",
                "hi": "कृपया स्कूल लाइब्रेरी में लंबित जुर्माना जमा करें।",
            }[language]
        )
        lines.append("")

    lines.append(
        {
            "en": "For book renewal, return, or fine queries, please contact the library.",
            "hi": "Book renewal, return या fine queries के लिए library से संपर्क करें।",
        }[language]
    )

    return "\n".join(lines).strip()


def send_library_records_flow(to_phone_number, student, language):
    """Fetch library records and send them via WhatsApp."""
    admission_no = first_present(student, ["admission_no", "admissionNo"])
    if admission_no == "-":
        send_text_message(
            to_phone_number,
            {
                "en": "Library Records could not be fetched. Student admission number is missing.",
                "hi": "लाइब्रेरी रिकॉर्ड प्राप्त नहीं हो पाया। Admission number missing है।",
            }[language],
        )
        send_navigation_buttons_later(to_phone_number, language, "academic")
        return

    try:
        result = fetch_library_records(admission_no)
    except Exception as exc:
        logger.exception("Failed to fetch library records: %s", exc)
        send_text_message(
            to_phone_number,
            {
                "en": "Library records could not be fetched right now. Please try again later or contact the library.",
                "hi": "अभी लाइब्रेरी रिकॉर्ड प्राप्त नहीं हो पाया। कृपया बाद में प्रयास करें या library से संपर्क करें।",
            }[language],
        )
        send_navigation_buttons_later(to_phone_number, language, "academic")
        return

    records = result.get("records", [])
    message = format_library_records(student, records, language)
    send_text_message(to_phone_number, message)
    send_navigation_buttons_later(to_phone_number, language, "academic")


def send_results_exams_flow(to_phone_number, language, student):
    try:
        result_data = fetch_student_results(student, language)
    except Exception as exc:
        logger.exception("Failed to fetch student result: %s", exc)
        send_text_message(to_phone_number, STUDENT_LOGIN_TEXT["result_error"][language])
        return

    if not result_data.get("ok"):
        send_text_message(
            to_phone_number,
            STUDENT_LOGIN_TEXT[result_data.get("reason", "server_error")][language],
        )
        send_navigation_buttons_later(to_phone_number, language, "exam")
        return

    send_text_message(to_phone_number, result_summary_text(result_data, language))

    has_successful_result = (
        result_data.get("status") == "ok"
        and any(
            exam.get("status") == "published" and exam.get("rows")
            for exam in result_data.get("exams", [])
        )
    )
    if not has_successful_result:
        send_navigation_buttons_later(to_phone_number, language, "exam")
        return

    try:
        pdf_filename = create_result_pdf(result_data)
        pdf_url = build_public_static_url(f"results/{pdf_filename}")
        if not pdf_url:
            raise RuntimeError("Unable to build public result PDF URL.")
        send_result_document_message(
            to_phone_number,
            pdf_url,
            "P.S. Public School Result.pdf",
            {
                "en": "Result PDF - P.S. Public School",
                "hi": "Result PDF - पी.एस. पब्लिक स्कूल",
            }[language],
        )
        send_navigation_buttons_later(to_phone_number, language, "exam", MEDIA_NAVIGATION_DELAY_SECONDS)
    except Exception as exc:
        logger.exception("Failed to create/send result PDF: %s", exc)
        send_text_message(
            to_phone_number,
            {
                "en": "Text result has been sent, but the PDF could not be generated right now.",
                "hi": "Text result भेज दिया गया है, लेकिन PDF अभी generate नहीं हो पाया।",
            }[language],
        )
        send_navigation_buttons_later(to_phone_number, language, "exam")


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

    language = LANGUAGE_BY_USER.get(to_phone_number, "en")

    if normalized_text == "nav_main_menu":
        send_service_list_message(to_phone_number, language)
        return

    if normalized_text == "nav_previous_menu":
        previous_menu = MENU_CONTEXT_BY_USER.get(to_phone_number, {}).get("previous", "main")
        if previous_menu == "academic":
            send_other_services_list_message(to_phone_number, language)
        elif previous_menu == "exam":
            send_exam_services_list_message(to_phone_number, language)
        elif previous_menu == "admission":
            send_admission_services_list_message(to_phone_number, language)
        elif previous_menu == "certificates":
            send_certificate_list_message(to_phone_number, language)
        else:
            send_service_list_message(to_phone_number, language)
        return

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

    refresh_student_auth_session(to_phone_number, language)

    service_id = service_title_to_id(language).get(normalized_text, normalized_text)

    if service_id in ACTION_REPLIES:
        send_text_message(to_phone_number, ACTION_REPLIES[service_id][language])
        send_navigation_buttons_later(to_phone_number, language, "main")
        return

    if service_id == "admission_services":
        send_admission_services_list_message(to_phone_number, language)
        return

    if service_id == "other_services":
        if to_phone_number not in STUDENT_AUTH_BY_USER:
            start_academic_services_login_flow(to_phone_number, language, "show_academic_services")
            return

        send_other_services_list_message(to_phone_number, language)
        return

    if service_id == "exam_services":
        if to_phone_number not in STUDENT_AUTH_BY_USER:
            start_academic_services_login_flow(to_phone_number, language, "show_exam_services")
            return

        send_exam_services_list_message(to_phone_number, language)
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

    if service_id == "holiday_list":
        send_holiday_exam_list_flow(to_phone_number, language, "admission")
        return

    if service_id == "school_facilities":
        send_school_facilities_flow(to_phone_number, language)
        return

    if service_id == "prospectus":
        send_prospectus_flow(to_phone_number, language)
        return

    if service_id == "change_language":
        send_language_buttons(to_phone_number)
        return

    other_category_id = other_service_title_to_id(language).get(normalized_text, normalized_text)
    certificate_id = certificate_title_to_id(language).get(normalized_text, normalized_text)

    if certificate_id in CERTIFICATE_CATEGORIES:
        auth = STUDENT_AUTH_BY_USER.get(to_phone_number)
        if not auth or not isinstance(auth.get("student"), dict):
            start_other_services_login_flow(to_phone_number, language)
            return

        run_later(
            0.1,
            send_certificate_flow,
            to_phone_number,
            language,
            auth["student"],
            certificate_id,
        )
        return

    if other_category_id == "student_details":
        auth = STUDENT_AUTH_BY_USER.get(to_phone_number)
        if auth and isinstance(auth.get("student"), dict):
            send_student_details_response(to_phone_number, auth["student"], language)
            return

        start_student_details_flow(to_phone_number, language)
        return

    if other_category_id == "results_exams":
        auth = STUDENT_AUTH_BY_USER.get(to_phone_number)
        if auth and isinstance(auth.get("student"), dict):
            run_later(
                0.1,
                send_results_exams_flow,
                to_phone_number,
                language,
                auth["student"],
            )
            return

        STUDENT_DETAIL_SESSIONS[to_phone_number] = {
            "step": "awaiting_username",
            "language": language,
            "after_login": "show_results_exams",
        }
        send_text_message(
            to_phone_number,
            {
                "en": (
                    "Results & Exams Login\n\n"
                    "Please verify once to view result details.\n\n"
                    "Please send the student's admission number."
                ),
                "hi": (
                    "रिजल्ट व परीक्षा लॉगिन\n\n"
                    "Result details देखने के लिए कृपया एक बार verification करें।\n\n"
                    "कृपया विद्यार्थी का admission number भेजें।"
                ),
            }[language],
        )
        return

    if other_category_id == "certificates":
        auth = STUDENT_AUTH_BY_USER.get(to_phone_number)
        if not auth or not isinstance(auth.get("student"), dict):
            start_other_services_login_flow(to_phone_number, language)
            return

        send_certificate_list_message(to_phone_number, language)
        return

    if other_category_id == "library_records":
        auth = STUDENT_AUTH_BY_USER.get(to_phone_number)
        if not auth or not isinstance(auth.get("student"), dict):
            start_other_services_login_flow(to_phone_number, language)
            return

        run_later(
            0.1,
            send_library_records_flow,
            to_phone_number,
            auth["student"],
            language,
        )
        return

    if other_category_id == "exam_schedule":
        send_holiday_exam_list_flow(to_phone_number, language, "exam")
        return

    if other_category_id in OTHER_SERVICE_CATEGORIES:
        send_text_message(
            to_phone_number,
            OTHER_SERVICE_CATEGORIES[other_category_id]["reply"][language],
        )
        previous_menu = "exam" if other_category_id in EXAM_CATEGORY_IDS else "academic"
        send_navigation_buttons_later(to_phone_number, language, previous_menu)
        return

    if service_id in SERVICES:
        send_text_message(to_phone_number, SERVICES[service_id]["reply"][language])
        send_navigation_buttons_later(to_phone_number, language, "main")
        return

    send_intro_and_services(to_phone_number, language)


@app.get("/")
def health_check():
    return jsonify({"status": "ok", "service": "whatsapp-auto-reply-bot"})


@app.get("/debug")
def debug_config():
    return jsonify(
        {
            "status": "ok",
            "access_token_configured": bool(ACCESS_TOKEN),
            "phone_number_id_configured": bool(PHONE_NUMBER_ID),
            "phone_number_id": PHONE_NUMBER_ID or "",
            "graph_api_version": GRAPH_API_VERSION,
            "school_image_url_configured": bool(SCHOOL_IMAGE_URL),
            "admission_form_pdf_url_configured": bool(ADMISSION_FORM_PDF_URL),
            "exam_backend_student_login_url": EXAM_BACKEND_STUDENT_LOGIN_URL,
            "effective_student_login_url": get_student_login_url(),
            "exam_backend_url": get_exam_backend_base_url(),
            "student_backend_url": STUDENT_BACKEND_URL,
            "public_base_url": PUBLIC_BASE_URL,
            "service_menu_delay_seconds": SERVICE_MENU_DELAY_SECONDS,
        }
    )


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
    try:
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

                    safe_reply_to_user(sender, incoming_text)
    except Exception as exc:
        logger.exception("Webhook processing error: %s", exc)

    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
