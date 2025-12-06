from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse

from app.charite_client import mock_lookup_user_in_charite
from app.crud import create_registration
from app.db import SessionLocal, Base, engine
from app.jwt_auth import JWTAuthService
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
def health_check():
    return {"status": "OK"}


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

            input[type="date"],
            input[type="time"],
            input[type="datetime-local"] {
                cursor: pointer;
            }

            .time-input-group {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                align-items: end;
            }

            .duration-toggle {
                display: flex;
                gap: 10px;
                margin-bottom: 15px;
                background-color: #f9f9f9;
                padding: 10px;
                border-radius: 4px;
            }

            .duration-toggle label {
                display: flex;
                align-items: center;
                gap: 5px;
                cursor: pointer;
                font-weight: normal;
                margin: 0;
            }

            .duration-toggle input[type="radio"] {
                width: auto;
                cursor: pointer;
            }

            .duration-input-container {
                display: none;
            }

            .duration-input-container.active {
                display: block;
            }

            .duration-fields {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 10px;
            }

            .duration-field {
                display: flex;
                flex-direction: column;
            }

            .duration-field label {
                font-size: 12px;
                color: #666;
                margin-bottom: 5px;
            }

            .duration-field input {
                text-align: center;
            }

            .helper-text {
                font-size: 12px;
                color: #666;
                margin-top: 5px;
                font-style: italic;
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

                    <!-- Appointment Date/Time -->
                    <div class="form-group">
                        <label for="appointment_date">Appointment Date:</label>
                        <input type="date" id="appointment_date" name="appointment_date" required>
                        <p class="helper-text">Date of the registration appointment</p>
                    </div>

                    <div class="form-group">
                        <label for="appointment_time">Appointment Time:</label>
                        <input type="time" id="appointment_time" name="appointment_time" value="00:00" required>
                        <p class="helper-text">Time of the registration appointment</p>
                    </div>

                    <!-- Event Start Time -->
                    <div class="form-group">
                        <label for="event_start_date">Event Start Date:</label>
                        <input type="date" id="event_start_date" name="event_start_date" required>
                        <p class="helper-text">Select the date when the event/monitoring starts</p>
                    </div>

                    <div class="form-group">
                        <label for="event_start_time">Event Start Time:</label>
                        <input type="time" id="event_start_time" name="event_start_time" value="00:00" required>
                        <p class="helper-text">Default is midnight (00:00:00), or enter a custom time</p>
                    </div>

                    <!-- Duration/End Time Toggle -->
                    <div class="form-group">
                        <label>Event Duration/End Time:</label>
                        <div class="duration-toggle">
                            <label>
                                <input type="radio" name="duration_type" value="duration" checked onchange="toggleDurationInput()">
                                Specify Duration
                            </label>
                            <label>
                                <input type="radio" name="duration_type" value="end_time" onchange="toggleDurationInput()">
                                Specify End Time
                            </label>
                        </div>

                        <!-- Duration Input -->
                        <div id="durationInput" class="duration-input-container active">
                            <div class="duration-fields">
                                <div class="duration-field">
                                    <label>Days</label>
                                    <input type="number" id="duration_days" min="0" value="0">
                                </div>
                                <div class="duration-field">
                                    <label>Hours</label>
                                    <input type="number" id="duration_hours" min="0" max="23" value="0">
                                </div>
                                <div class="duration-field">
                                    <label>Minutes</label>
                                    <input type="number" id="duration_minutes" min="0" max="59" value="0">
                                </div>
                                <div class="duration-field">
                                    <label>Seconds</label>
                                    <input type="number" id="duration_seconds" min="0" max="59" value="0">
                                </div>
                            </div>
                            <p class="helper-text">Enter the duration of the event</p>
                        </div>

                        <!-- End Time Input -->
                        <div id="endTimeInput" class="duration-input-container">
                            <div class="time-input-group">
                                <div>
                                    <label for="event_end_date">End Date:</label>
                                    <input type="date" id="event_end_date" name="event_end_date">
                                </div>
                                <div>
                                    <label for="event_end_time">End Time:</label>
                                    <input type="time" id="event_end_time" name="event_end_time" value="00:00">
                                </div>
                            </div>
                            <p class="helper-text">Select when the event ends</p>
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
            const GRAFANA_URL = 'http://94.130.230.161:30300/d/wearables-health/wearables-health-dashboard?orgId=1&from=now-7d&to=now&timezone=browser&var-DS_INFLUXDB=cf5irkhmbkfswb';
    
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
                document.querySelectorAll('.response').forEach(resp => {
                    resp.style.display = 'none';
                });
                document.getElementById('qrContainer').style.display = 'none';
            }
    
            function openDashboard() {
                window.open(GRAFANA_URL, '_blank');
            }

            function toggleDurationInput() {
                const durationType = document.querySelector('input[name="duration_type"]:checked').value;
                const durationInput = document.getElementById('durationInput');
                const endTimeInput = document.getElementById('endTimeInput');
                
                if (durationType === 'duration') {
                    durationInput.classList.add('active');
                    endTimeInput.classList.remove('active');
                } else {
                    durationInput.classList.remove('active');
                    endTimeInput.classList.add('active');
                }
            }

            function calculateDuration() {
                const durationType = document.querySelector('input[name="duration_type"]:checked').value;
                
                if (durationType === 'duration') {
                    const days = parseInt(document.getElementById('duration_days').value) || 0;
                    const hours = parseInt(document.getElementById('duration_hours').value) || 0;
                    const minutes = parseInt(document.getElementById('duration_minutes').value) || 0;
                    const seconds = parseInt(document.getElementById('duration_seconds').value) || 0;
                    
                    return (days * 86400) + (hours * 3600) + (minutes * 60) + seconds;
                } else {
                    const startDate = document.getElementById('event_start_date').value;
                    const startTime = document.getElementById('event_start_time').value;
                    const endDate = document.getElementById('event_end_date').value;
                    const endTime = document.getElementById('event_end_time').value;
                    
                    if (!endDate || !endTime) {
                        throw new Error('Please specify both end date and end time');
                    }
                    
                    const startDateTime = new Date(`${startDate}T${startTime}`);
                    const endDateTime = new Date(`${endDate}T${endTime}`);
                    
                    const durationMs = endDateTime - startDateTime;
                    
                    if (durationMs <= 0) {
                        throw new Error('End time must be after start time');
                    }
                    
                    return Math.floor(durationMs / 1000);
                }
            }

            function formatToISO(date, time) {
                return `${date}T${time}:00`;
            }

            function setDefaultDate() {
                const today = new Date().toISOString().split('T')[0];
                document.getElementById('event_start_date').value = today;
                document.getElementById('appointment_date').value = today;
            }

            document.getElementById('registrationForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const responseDiv = document.getElementById('registerResponse');
                
                try {
                    const appointmentDate = document.getElementById('appointment_date').value;
                    const appointmentTime = document.getElementById('appointment_time').value;
                    const appointmentDateTime = formatToISO(appointmentDate, appointmentTime);
                    
                    const eventDate = document.getElementById('event_start_date').value;
                    const eventTime = document.getElementById('event_start_time').value;
                    const eventStartDateTime = formatToISO(eventDate, eventTime);
                    
                    const eventDuration = calculateDuration();
                    
                    if (eventDuration === 0) {
                        throw new Error('Event duration must be greater than 0');
                    }
                    
                    const formData = {
                        patient_id: document.getElementById('patient_id').value,
                        watch_id: document.getElementById('watch_id').value,
                        phone_id: document.getElementById('phone_id').value,
                        context_id: document.getElementById('context_id').value,
                        patient_mail: document.getElementById('patient_mail').value,
                        appointment_date: appointmentDateTime,
                        event_duration: eventDuration.toString(),
                        event_start_date: eventStartDateTime
                    };
                    
                    console.log('Sending:', JSON.stringify(formData, null, 2));
                    
                    const response = await fetch(`${API_BASE_URL}/register/patient`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(formData)
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        const durationHours = Math.floor(eventDuration / 3600);
                        const durationMinutes = Math.floor((eventDuration % 3600) / 60);
                        responseDiv.className = 'response success';
                        responseDiv.textContent = `✓ Registration submitted successfully! Appointment: ${appointmentDateTime}, Event Start: ${eventStartDateTime}, Duration: ${durationHours}h ${durationMinutes}m`;
                        this.reset();
                        setDefaultDate();
                    } else {
                        const errorData = await response.json();
                        console.error('Backend error:', errorData);
                        throw new Error(errorData.detail || 'Registration failed');
                    }
                } catch (error) {
                    responseDiv.className = 'response error';
                    responseDiv.textContent = `✗ Error: ${error.message}`;
                }
            });

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
                        
                        qrContainer.style.display = 'block';
                        document.getElementById('eventIdDisplay').textContent = eventId;
                        
                        document.getElementById('qrcode').innerHTML = '';
                        
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
    
            setDefaultDate();
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

    start_time = datetime.fromisoformat(payload.event_start_date.replace('Z', '+00:00'))

    reg = await create_registration(
        db=db,
        username=payload.patient_id,
        context_name=payload.context_id,
        watch_id=payload.watch_id,
        phone_id=payload.phone_id,
        start_time=start_time,
        duration=payload.event_duration,
    )

    db.commit()

    # Generate new Token
    token_obj = RegistrationTokenService.create_registration_token(
        db,
        reg.id,
        start_time=payload.event_start_date.replace('Z', '+00:00'),
        duration=payload.event_duration,
    )

    token_id = token_obj.id

    # send the token via E-Mail to the user-mail
    test_mail = payload.patient_mail
    appointment_date = datetime.fromisoformat(payload.appointment_date.replace('Z', '+00:00'))

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

    event_id = token.event_id

    jwt_auth = JWTAuthService.generate_auth_token(
        event_id=event_id,
        event_start_time=token.start_time,
        event_duration=token.duration,
    )


    return PatientResponse(
        status="OK",
        message=message,
        reg_id=jwt_auth,
    )


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
