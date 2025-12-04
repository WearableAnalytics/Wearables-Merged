from time import strptime

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse

from app.charite_client import mock_lookup_user_in_charite
from app.crud import create_registration
from app.db import SessionLocal, Base, engine
from app.mail import EmailService
from app.models import PatientResponse, PatientRequest, RegistrationToken, RegisterResponse
from app.token import RegistrationTokenService

app = FastAPI(title="Test", version="0.1.0", description="Test")
Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
async def health():
    return {"status": "200"}


@app.get("/", response_class=HTMLResponse)
async def root():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Patient Management Portal</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
    
            body {
                font-family: Arial, sans-serif;
                background-color: #f5f5f5;
                padding: 20px;
            }
    
            .container {
                max-width: 800px;
                margin: 0 auto;
            }
    
            .header {
                text-align: center;
                margin-bottom: 50px;
                padding: 30px;
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
    
            .header h1 {
                color: #333;
                margin-bottom: 10px;
            }
    
            .header p {
                color: #666;
            }
    
            .menu-buttons {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
    
            .menu-btn {
                padding: 40px 20px;
                background-color: white;
                border: 2px solid #ddd;
                border-radius: 8px;
                cursor: pointer;
                transition: all 0.3s;
                text-align: center;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
    
            .menu-btn:hover {
                transform: translateY(-5px);
                box-shadow: 0 4px 20px rgba(0,0,0,0.15);
                border-color: #4CAF50;
            }
    
            .menu-btn h2 {
                color: #333;
                margin-bottom: 10px;
                font-size: 1.5em;
            }
    
            .menu-btn p {
                color: #666;
                font-size: 0.9em;
            }
    
            .content-section {
                display: none;
                background-color: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
    
            .content-section.active {
                display: block;
            }
    
            .back-btn {
                padding: 10px 20px;
                background-color: #666;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                margin-bottom: 20px;
                font-size: 14px;
            }
    
            .back-btn:hover {
                background-color: #555;
            }
    
            .form-group {
                margin-bottom: 20px;
            }
    
            label {
                display: block;
                margin-bottom: 5px;
                color: #555;
                font-weight: bold;
            }
    
            input, select {
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
            }
    
            .datetime-group, .time-group {
                display: grid;
                grid-template-columns: 1fr 1fr 1fr;
                gap: 10px;
            }
    
            .submit-btn {
                width: 100%;
                padding: 12px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                cursor: pointer;
                margin-top: 10px;
            }
    
            .submit-btn:hover {
                background-color: #45a049;
            }
    
            .response {
                margin-top: 20px;
                padding: 15px;
                border-radius: 4px;
                display: none;
            }
    
            .response.success {
                background-color: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
                display: block;
            }
    
            .response.error {
                background-color: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
                display: block;
            }
    
            .qr-container {
                text-align: center;
                margin-top: 30px;
                padding: 20px;
                background-color: #f9f9f9;
                border-radius: 8px;
            }
    
            .qr-container h3 {
                margin-bottom: 15px;
                color: #333;
            }
    
            #qrcode {
                display: inline-block;
                padding: 20px;
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
    
            .event-id-display {
                margin-top: 15px;
                padding: 15px;
                background-color: white;
                border-radius: 4px;
                font-family: monospace;
                font-size: 1.1em;
                color: #333;
                border: 2px solid #4CAF50;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Header -->
            <div class="header">
                <h1>Patient Management Portal</h1>
                <p>Manage patient registration and onboarding</p>
            </div>
    
            <!-- Main Menu -->
            <div id="mainMenu" class="menu-buttons">
                <div class="menu-btn" onclick="showSection('registerSection')">
                    <h2>Register New Patient</h2>
                    <p>Create a new patient registration</p>
                </div>
                <div class="menu-btn" onclick="showSection('onboardSection')">
                    <h2>Onboard Patient</h2>
                    <p>Complete patient onboarding with token</p>
                </div>
                <div class="menu-btn" onclick="openDashboard()">
                    <h2>View Dashboard</h2>
                    <p>Access Grafana analytics</p>
                </div>
            </div>
    
            <!-- Register Patient Section -->
            <div id="registerSection" class="content-section">
                <button class="back-btn" onclick="showMenu()">← Back to Menu</button>
                <h2 style="margin-bottom: 30px; color: #333;">Register New Patient</h2>
                
                <form id="registrationForm">
                    <div class="form-group">
                        <label for="patient_id">Patient ID:</label>
                        <input type="text" id="patient_id" name="patient_id" required>
                    </div>
                    <div class="form-group">
                        <label for="context_id">Context ID:</label>
                        <input type="text" id="context_id" name="context_id" required>
                    </div>
                    <div class="form-group">
                        <label for="watch_id">Watch ID:</label>
                        <input type="text" id="watch_id" name="watch_id" required>
                    </div>
                    <div class="form-group">
                        <label for="phone_id">Phone ID:</label>
                        <input type="text" id="phone_id" name="phone_id" required>
                    </div>
                    <div class="form-group">
                        <label for="patient_mail">Patient Email:</label>
                        <input type="email" id="patient_mail" name="patient_mail" required>
                    </div>    
                    <div class="form-group">
                        <label>Registration-Appointment Date:</label>
                        <div class="datetime-group">
                            <select id="month" name="month" required>
                                <option value="">Month</option>
                            </select>
                            <select id="day" name="day" required>
                                <option value="">Day</option>
                            </select>
                            <select id="year" name="year" required>
                                <option value="">Year</option>
                            </select>
                        </div>
                    </div>
                    <div class="form-group">
                        <label>Registration-Appointment Time:</label>
                        <div class="time-group">
                            <select id="hour" name="hour" required>
                                <option value="">Hour</option>
                            </select>
                            <select id="minute" name="minute" required>
                                <option value="">Minute</option>
                            </select>
                            <select id="ampm" name="ampm" required>
                                <option value="">AM/PM</option>
                                <option value="AM">AM</option>
                                <option value="PM">PM</option>
                            </select>
                        </div>
                    </div>
                    <button type="submit" class="submit-btn">Submit Registration</button>    
                </form>
                <div id="registerResponse" class="response"></div>
            </div>
    
            <!-- Onboard Patient Section -->
            <div id="onboardSection" class="content-section">
                <button class="back-btn" onclick="showMenu()">← Back to Menu</button>
                <h2 style="margin-bottom: 30px; color: #333;">Onboard Patient</h2>
                
                <form id="onboardForm">
                    <div class="form-group">
                        <label for="registration_token">Registration Token (UUID):</label>
                        <input type="text" id="registration_token" name="registration_token" 
                               placeholder="e.g., 550e8400-e29b-41d4-a716-446655440000" required>
                    </div>
                    <button type="submit" class="submit-btn">Generate Event ID</button>
                </form>
                <div id="onboardResponse" class="response"></div>
                
                <div id="qrContainer" class="qr-container" style="display: none;">
                    <h3>Scan this QR Code</h3>
                    <div id="qrcode"></div>
                    <div class="event-id-display">
                        <strong>Event ID:</strong> <span id="eventIdDisplay"></span>
                    </div>
                </div>
            </div>
        </div>
    
        <!-- QR Code Library -->
        <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
    
        <script>
            const API_BASE_URL = 'http://localhost:8000';
            const GRAFANA_URL = 'http://94.130.230.161:30300/d/wearables-health/wearables-health-dashboard?orgId=1&from=now-7d&to=now&timezone=browser&var-DS_INFLUXDB=cf5irkhmbkfswb'; // Update with your Grafana URL
    
            // Navigation functions
            function showSection(sectionId) {
                document.getElementById('mainMenu').style.display = 'none';
                document.querySelectorAll('.content-section').forEach(section => {
                    section.classList.remove('active');
                });
                document.getElementById(sectionId).classList.add('active');
            }
    
            function showMenu() {
                document.getElementById('mainMenu').style.display = 'grid';
                document.querySelectorAll('.content-section').forEach(section => {
                    section.classList.remove('active');
                });
                // Clear responses
                document.querySelectorAll('.response').forEach(resp => {
                    resp.style.display = 'none';
                });
                document.getElementById('qrContainer').style.display = 'none';
            }
    
            function openDashboard() {
                window.open(GRAFANA_URL, '_blank');
            }
    
            // Populate date/time dropdowns
            function populateDropdowns() {
                const monthSelect = document.getElementById('month');
                for (let i = 1; i <= 12; i++) {
                    const option = document.createElement('option');
                    option.value = String(i).padStart(2, '0');
                    option.textContent = String(i).padStart(2, '0');
                    monthSelect.appendChild(option);
                }
    
                const daySelect = document.getElementById('day');
                for (let i = 1; i <= 31; i++) {
                    const option = document.createElement('option');
                    option.value = String(i).padStart(2, '0');
                    option.textContent = String(i).padStart(2, '0');
                    daySelect.appendChild(option);
                }
    
                const yearSelect = document.getElementById('year');
                const currentYear = new Date().getFullYear();
                for (let i = currentYear; i <= currentYear + 1; i++) {
                    const option = document.createElement('option');
                    option.value = i;
                    option.textContent = i;
                    yearSelect.appendChild(option);
                }
    
                const hourSelect = document.getElementById('hour');
                for (let i = 1; i <= 12; i++) {
                    const option = document.createElement('option');
                    option.value = String(i).padStart(2, '0');
                    option.textContent = String(i).padStart(2, '0');
                    hourSelect.appendChild(option);
                }
    
                const minuteSelect = document.getElementById('minute');
                for (let i = 0; i <= 59; i++) {
                    const option = document.createElement('option');
                    option.value = String(i).padStart(2, '0');
                    option.textContent = String(i).padStart(2, '0');
                    minuteSelect.appendChild(option);
                }
            }
    
            // Handle registration form submission
            document.getElementById('registrationForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const month = document.getElementById('month').value;
                const day = document.getElementById('day').value;
                const year = document.getElementById('year').value;
                const hour = document.getElementById('hour').value;
                const minute = document.getElementById('minute').value;
                const ampm = document.getElementById('ampm').value;
                
                const formattedDateTime = `${month}/${day}/${year}, ${hour}:${minute} ${ampm}`;
                
                const formData = {
                    patient_id: document.getElementById('patient_id').value,
                    context_id: document.getElementById('context_id').value,
                    watch_id: document.getElementById('watch_id').value,
                    phone_id: document.getElementById('phone_id').value,
                    patient_mail: document.getElementById('patient_mail').value,
                    appointment_date: formattedDateTime
                };
                
                const responseDiv = document.getElementById('registerResponse');
                
                try {
                    const response = await fetch(`${API_BASE_URL}/register/patient`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(formData)
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        responseDiv.className = 'response success';
                        responseDiv.textContent = `✓ Registration submitted successfully! Appointment: ${formattedDateTime}`;
                        this.reset();
                    } else {
                        throw new Error('Registration failed');
                    }
                } catch (error) {
                    responseDiv.className = 'response error';
                    responseDiv.textContent = `✗ Error: ${error.message}. Please try again.`;
                }
            });
    
            // Handle onboarding form submission
            document.getElementById('onboardForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const registrationToken = document.getElementById('registration_token').value.trim();
            const responseDiv = document.getElementById('onboardResponse');
            const qrContainer = document.getElementById('qrContainer');
            
            try {
                const response = await fetch(`${API_BASE_URL}/onboard/${registrationToken}`, {
                    method: 'GET',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    const eventId = data.reg_id;
                    
                    responseDiv.className = 'response success';
                    responseDiv.textContent = `✓ ${data.message}`;
                    
                    // Display QR Code
                    qrContainer.style.display = 'block';
                    document.getElementById('eventIdDisplay').textContent = eventId;
                    
                    // Clear previous QR code if exists
                    document.getElementById('qrcode').innerHTML = '';
                    
                    // Generate QR Code
                    new QRCode(document.getElementById('qrcode'), {
                        text: eventId,
                        width: 256,
                        height: 256,
                        colorDark: '#000000',
                        colorLight: '#ffffff',
                        correctLevel: QRCode.CorrectLevel.H
                    });
                    
                    this.reset();
                } else {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || 'Onboarding failed');
                }
            } catch (error) {
                responseDiv.className = 'response error';
                responseDiv.textContent = `✗ Error: ${error.message}`;
                qrContainer.style.display = 'none';
            }
        });
               
    
            // Initialize dropdowns on page load
            populateDropdowns();
        </script>
    </body>
    </html>
    """
    return html_content


@app.post("/register/patient", response_model=RegisterResponse)
async def register_patient(payload: PatientRequest, db: Session = Depends(get_db)):
    charite_info = await mock_lookup_user_in_charite(payload.patient_id)

    if not charite_info:
        raise HTTPException(status_code=404, detail="User not found")

    reg = await create_registration(
        db=db,
        username=payload.patient_id,
        context_name=payload.context_id,
        watch_id=payload.watch_id,
        phone_id=payload.phone_id,
    )

    db.commit()

    # Generate new Token
    token_obj = RegistrationTokenService.create_registration_token(
        db,
        reg.id,
    )

    token_id = token_obj.id

    # send the token via E-Mail to the user-mail
    test_mail = payload.patient_mail
    appointment_date = strptime(payload.appointment_date, "%m/%d/%Y, %I:%M %p")

    b = await EmailService.send_registration_mail(test_mail, token_id, appointment_date)

    if not b:
        raise HTTPException(status_code=404, detail="Email not found")

    return RegisterResponse(
        status="OK",
        message=f"Registered successfully",
    )


@app.get("/onboard/{token_id}", response_model=PatientResponse)
async def onboard_patient(token_id: str, db: Session = Depends(get_db)):
    print("Now checking if it's token is valid")
    valid, message = RegistrationTokenService.validate_and_consume_token(db, token_id)

    if not valid:
        raise HTTPException(status_code=404, detail=message)

    token = RegistrationTokenService.get_token(db, token_id)

    return PatientResponse(
        status="OK",
        message=message,
        reg_id=token.event_id,
    )


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
