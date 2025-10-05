Multi-Telescope Data Fusion (Sky Unifier)
 
Problem: Different telescopes capture different spectra (optical, IR, X-ray, radio). Scientists need to combine these for a complete picture.
Solution:
 
Build a tool that takes datasets from multiple observatories (e.g., JWST + Hubble + Chandra) and overlays them into a unified, interactive sky map.
 
Users can toggle wavelengths to see how an object looks in different spectra.
Tech: Python (Astropy), NASA SkyView API, JS visualization (Plotly/D3).
Impact: Helps researchers and educators explore full-spectrum astronomy easily.


How to start : 

Below is the full step-by-step setup guide — all commands ready to copy–paste 👇

🛰️ 1️⃣ Clone the Repository
cd Sky-Unifire-NASA

🧠 2️⃣ Backend Setup (Python + FastAPI)
🔹 Step 2.1 — Go to backend folder
cd "Sky Unifire"   // if this not work 
or  
cd Sky Unifire

🔹 Step 2.2 — Create and activate virtual environment
🪟 On Windows (CMD/PowerShell)
python -m venv venv          // use this       
venv\Scripts\activate

🐧 On macOS/Linux
python3 -m venv venv
source venv/bin/activate

🔹 Step 2.3 — Install dependencies
pip install -r requirements.txt

🔹 Step 2.4 — Run the FastAPI server
uvicorn sky_unifier_fastapi:app --reload --host 0.0.0.0 --port 8000


✅ Backend now runs at 👉 http://localhost:8000

⚡ 3️⃣ Frontend Setup (React + Vite)
🔹 Step 3.1 — Go to frontend folder
cd ../sky-unifier-frontend

🔹 Step 3.2 — Install npm dependencies
npm install

🔹 Step 3.3 — Run Vite development server
npm run dev


✅ Frontend now runs at 👉 http://localhost:5173
