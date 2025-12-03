from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse

from app.charite_client import mock_lookup_user_in_charite
from app.crud import create_registration
from app.db import SessionLocal, Base, engine
from app.models import PatientResponse, PatientRequest

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
        <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
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
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            h1 {
                color: #333;
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
            input {
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
                box-sizing: border-box;
                font-size: 14px;
            }
            button {
                width: 100%;
                padding: 12px;
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 16px;
                font-weight: bold;
            }
            button:hover {
                background-color: #0056b3;
            }
            .response {
                margin-top: 20px;
                padding: 15px;
                border-radius: 4px;
                display: none;
            }
            .response.success {
                background-color: #d4edda;
                border: 1px solid #c3e6cb;
                color: #155724;
            }
            .response.error {
                background-color: #f8d7da;
                border: 1px solid #f5c6cb;
                color: #721c24;
            }
            #qrcode {
                display: flex;
                justify-content: center;
                margin: 20px 0;
            }
            .qr-container {
                text-align: center;
            }
            .master-id-text {
                margin-top: 15px;
                font-size: 18px;
                font-weight: bold;
                color: #333;
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
                <button type="submit">Submit</button>
            </form>
            <div id="response" class="response"></div>
        </div>

        <script>
            document.getElementById('registrationForm').addEventListener('submit', async (e) => {
                e.preventDefault();

                const formData = {
                    patient_id: document.getElementById('patient_id').value,
                    context_id: document.getElementById('context_id').value,
                    watch_id: document.getElementById('watch_id').value,
                    phone_id: document.getElementById('phone_id').value
                };

                const responseDiv = document.getElementById('response');
                responseDiv.style.display = 'none';
                responseDiv.innerHTML = '';

                try {
                    const response = await fetch('/register/patient', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(formData)
                    });

                    const data = await response.json();

                    if (response.ok) {
                        responseDiv.className = 'response success';
                        responseDiv.innerHTML = `
                            <div class="qr-container">
                                <h3>Registration Successful!</h3>
                                <p><strong>Status:</strong> ${data.status}</p>
                                <p><strong>Message:</strong> ${data.message}</p>
                                <div id="qrcode"></div>
                                <p class="master-id-text">Master ID: ${data.reg_id}</p>
                                <p style="margin-top: 10px; color: #666;">Scan this QR code to access the registration</p>
                            </div>
                        `;

                        // Generate QR code
                        new QRCode(document.getElementById("qrcode"), {
                            text: data.reg_id,
                            width: 200,
                            height: 200,
                            colorDark: "#000000",
                            colorLight: "#ffffff",
                            correctLevel: QRCode.CorrectLevel.H
                        });
                    } else {
                        responseDiv.className = 'response error';
                        responseDiv.innerHTML = `
                            <h3>Error</h3>
                            <p>${data.detail || 'An error occurred'}</p>
                        `;
                    }
                } catch (error) {
                    responseDiv.className = 'response error';
                    responseDiv.innerHTML = `
                        <h3>Error</h3>
                        <p>Failed to connect to the server: ${error.message}</p>
                    `;
                }

                responseDiv.style.display = 'block';
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

    return PatientResponse(
        status="OK",
        message=f"Registration created, master_id is be scaned on: {reg.id}",
        reg_id=str(reg.id)
    )

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
