from time import strptime

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse

from app.charite_client import mock_lookup_user_in_charite
from app.crud import create_registration
from app.db import SessionLocal, Base, engine
from app.mail import EmailService
from app.models import PatientResponse, PatientRequest, RegistrationToken
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
        <title>Patient Registration</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .container {
                background-color: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 {
                color: #333;
                text-align: center;
                margin-bottom: 30px;
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
                box-sizing: border-box;
                font-size: 14px;
            }
            .datetime-group {
                display: grid;
                grid-template-columns: 1fr 1fr 1fr;
                gap: 10px;
            }
            .time-group {
                display: grid;
                grid-template-columns: 1fr 1fr 1fr;
                gap: 10px;
            }
            button {
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
            button:hover {
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
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Patient Registration</h1>
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
                <button type="submit">Submit</button>    
            </form>
            <div id="response" class="response"></div>
        </div>
    
        <script>
            // Populate months
            const monthSelect = document.getElementById('month');
            for (let i = 1; i <= 12; i++) {
                const option = document.createElement('option');
                option.value = String(i).padStart(2, '0');
                option.textContent = String(i).padStart(2, '0');
                monthSelect.appendChild(option);
            }
    
            // Populate days
            const daySelect = document.getElementById('day');
            for (let i = 1; i <= 31; i++) {
                const option = document.createElement('option');
                option.value = String(i).padStart(2, '0');
                option.textContent = String(i).padStart(2, '0');
                daySelect.appendChild(option);
            }
    
            // Populate years (current year + 1 year forward)
            const yearSelect = document.getElementById('year');
            const currentYear = new Date().getFullYear();
            for (let i = currentYear; i <= currentYear + 1; i++) {
                const option = document.createElement('option');
                option.value = i;
                option.textContent = i;
                yearSelect.appendChild(option);
            }
    
            // Populate hours (1-12)
            const hourSelect = document.getElementById('hour');
            for (let i = 1; i <= 12; i++) {
                const option = document.createElement('option');
                option.value = String(i).padStart(2, '0');
                option.textContent = String(i).padStart(2, '0');
                hourSelect.appendChild(option);
            }
    
            // Populate minutes (00-59)
            const minuteSelect = document.getElementById('minute');
            for (let i = 0; i <= 59; i++) {
                const option = document.createElement('option');
                option.value = String(i).padStart(2, '0');
                option.textContent = String(i).padStart(2, '0');
                minuteSelect.appendChild(option);
            }
    
            // Handle form submission
            document.getElementById('registrationForm').addEventListener('submit', function(e) {
                e.preventDefault();
                
                const month = document.getElementById('month').value;
                const day = document.getElementById('day').value;
                const year = document.getElementById('year').value;
                const hour = document.getElementById('hour').value;
                const minute = document.getElementById('minute').value;
                const ampm = document.getElementById('ampm').value;
                
                // Format: MM/DD/YYYY, HH:MM AM/PM
                const formattedDateTime = `${month}/${day}/${year}, ${hour}:${minute} ${ampm}`;
                
                // Get all form data
                const formData = {
                    patient_id: document.getElementById('patient_id').value,
                    context_id: document.getElementById('context_id').value,
                    watch_id: document.getElementById('watch_id').value,
                    phone_id: document.getElementById('phone_id').value,
                    patient_mail: document.getElementById('patient_mail').value,
                    appointment_date: formattedDateTime
                };
                
                console.log('Form Data:', formData);
                
                // Display success message
                const responseDiv = document.getElementById('response');
                responseDiv.className = 'response success';
                responseDiv.textContent = `Registration submitted successfully! Appointment: ${formattedDateTime}`;
                
                // Here you would typically send the data to your backend
                fetch('/register/patient', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(formData)
                })
            });
        </script>
    </body>
    </html>
    """
    return html_content


@app.post("/register/patient", response_model=PatientResponse)
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

    return PatientResponse(
        status="OK",
        message=f"Registration created, master_id is be scaned on: {reg.id}",
        reg_id=str(reg.id)
    )


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
