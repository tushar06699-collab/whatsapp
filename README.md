# WhatsApp Auto Reply Bot

Python Flask bot for the Meta WhatsApp Cloud API. The bot never sends messages first. It only replies to WhatsApp messages received through the `/webhook` endpoint.

## Files

- `app.py` - Flask app with Meta webhook verification and incoming message handling.
- `requirements.txt` - Python dependencies.
- `render.yaml` - Render deployment configuration.
- `.env.example` - Required environment variable example.
- `static/school.png` - School image sent with the welcome message.

## Local Setup

1. Create a virtual environment:

   ```bash
   python -m venv .venv
   ```

2. Activate the virtual environment:

   Windows PowerShell:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   macOS/Linux:

   ```bash
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file from `.env.example`:

   ```bash
   cp .env.example .env
   ```

5. Add your Meta WhatsApp Cloud API values:

   ```env
   ACCESS_TOKEN=your_meta_whatsapp_cloud_api_access_token
   PHONE_NUMBER_ID=your_whatsapp_phone_number_id
   GRAPH_API_VERSION=v20.0
   SCHOOL_IMAGE_URL=https://YOUR-APP.onrender.com/static/school.png
   SERVICE_MENU_DELAY_SECONDS=3
   ADMISSION_FORM_PDF_URL=https://YOUR-APP.onrender.com/static/admission-form-final.pdf
   ONLINE_ADMISSION_FORM_URL=https://pspublicschool.com
   ```

6. Run locally:

   ```bash
   python app.py
   ```

Local webhook URL:

```text
http://localhost:5000/webhook
```

For local Meta testing, expose your local server with a public HTTPS tunnel such as ngrok.

## Bot Behavior

When a WhatsApp user sends `hy`, `hi`, `hello`, or any first message, the bot first asks for language:

```text
Please choose your preferred language.

कृपया अपनी भाषा चुनें।

English
Hindi
```

After the user selects a language, all menus and replies continue in that language.

For English, the bot replies in this sequence:

1. School image with this intro as the caption:

```text
Welcome to P.S. Public School

P.S. Public School is committed to quality education, discipline, student safety, and all-round development. Our team focuses on building strong academic foundations along with confidence, values, and life skills.
```

2. A WhatsApp interactive service list with a `View Services` button.

The user taps `View Services`, chooses a service, and WhatsApp sends that selected service back to the bot. The bot then replies with the correct information.

Services shown in the list:

```text
Admission Enquiry
Fee Structure
Transport Facility
Contact School
Other Services
Change Language
```

For Hindi, the same flow is shown in simple Hindi:

```text
प्रवेश जानकारी
फीस जानकारी
परिवहन सुविधा
स्कूल संपर्क
अन्य सेवाएं
भाषा बदलें
```

Users can select `Change Language` / `भाषा बदलें` anytime if they selected the wrong language or want to switch between English and Hindi.

Menu responses:

- `Admission Enquiry` - Professional admission flow with school highlights, contact details, admission form PDF, required documents, and fill-form option.
- `Fee Structure` - School academic overview, then class-wise fee structure for session 2026-2027.
- `Transport Facility` - Transport overview, safety/route points, and monthly route-wise transport fee.
- `Contact School` - School contact response.
- `Other Services` - Opens a category menu for academics, student details, results, certificates, uniform/books, and school timing.

To use a different school photo, replace `static/school.png` or set `SCHOOL_IMAGE_URL` to any public HTTPS image URL.

## Admission Enquiry Flow

When a user selects `Admission Enquiry`, the bot sends:

1. School highlights and contact details:

   ```text
   Call: +91 94162 93661
   WhatsApp: +91 94168 38604
   Email: psbhurri@gmail.com
   Website: pspublicschool.com
   ```

2. Admission form PDF:

   ```text
   https://YOUR-APP.onrender.com/static/admission-form-final.pdf
   ```

3. Required documents and admission process.
4. Buttons:

   ```text
   Fill Form
   Contact Office
   ```

## Fee Structure Flow

When a user selects `Fee Structure`, the bot sends:

1. Basic academic details about the school.
2. Class-wise fee structure with:

   ```text
   Class
   Fresh Admission Fee
   Old Admission Fee
   Annual Charge
   Tuition Fee
   Registration Fee
   I-Card Fee
   ```

3. Additional charges:

   ```text
   Exam Fee: Rs. 350
   Late Fee Charge: Rs. 50
   ```

## Transport Facility Flow

When a user selects `Transport Facility`, the bot sends:

1. Transport facility details and important route/safety points.
2. Monthly bus fee:

   ```text
   Rajpur, Kami, Garhi: Rs. 350
   Rajlu Garhi, Lalheri, Bhigan: Rs. 400
   Sonipat, Ganaur: Rs. 500
   ```

## Other Services Flow

When a user selects `Other Services`, the bot opens a second category menu:

```text
Academic Support
Student Details
Results & Exams
Certificates
Uniform & Books
School Timing
```

In Hindi:

```text
शैक्षणिक सहायता
विद्यार्थी विवरण
रिजल्ट व परीक्षा
प्रमाण पत्र
यूनिफॉर्म व किताबें
स्कूल समय
```

## Deploy on Render

1. Push this project to a GitHub repository.
2. Open Render and create a new Blueprint or Web Service from the repository.
3. If using `render.yaml`, Render will use:

   ```text
   Build Command: pip install -r requirements.txt
   Start Command: gunicorn app:app
   ```

4. Add environment variables in Render:

   ```text
   ACCESS_TOKEN=your_meta_whatsapp_cloud_api_access_token
   PHONE_NUMBER_ID=your_whatsapp_phone_number_id
   GRAPH_API_VERSION=v20.0
   SCHOOL_IMAGE_URL=https://YOUR-APP.onrender.com/static/school.png
   SERVICE_MENU_DELAY_SECONDS=3
   ADMISSION_FORM_PDF_URL=https://YOUR-APP.onrender.com/static/admission-form-final.pdf
   ONLINE_ADMISSION_FORM_URL=https://pspublicschool.com
   ```

5. After deployment, your webhook URL will be:

   ```text
   https://YOUR-APP.onrender.com/webhook
   ```

## Connect Webhook in Meta

In Meta for Developers, go to your WhatsApp app webhook settings and set:

```text
Callback URL = https://YOUR-APP.onrender.com/webhook
Verify Token = school_bot_verify
```

Subscribe to the WhatsApp `messages` webhook field.

## Important

- This app only sends replies from the incoming `POST /webhook` handler.
- It does not contain any route, scheduler, startup task, or background job that sends outbound messages first.
- Keep `ACCESS_TOKEN` private and never commit your real `.env` file.

## Student Details Setup

The `Other Services -> Student Details` option asks for the student's exam portal username and password, then calls the exam backend login API.

Set this in Render:

```text
EXAM_BACKEND_STUDENT_LOGIN_URL=https://exam-backend-117372286918.asia-south1.run.app/login
```

Use the same student login API endpoint that your exam frontend login page uses.
