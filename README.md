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

When a WhatsApp user sends `hy`, `hi`, `hello`, or any normal message, the bot replies in this sequence:

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
```

Menu responses:

- `Admission Enquiry` - Admission enquiry response.
- `Fee Structure` - Fee structure response.
- `Transport Facility` - Transport facility response.
- `Contact School` - School contact response.
- `Other Services` - Other services response.

To use a different school photo, replace `static/school.png` or set `SCHOOL_IMAGE_URL` to any public HTTPS image URL.

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
