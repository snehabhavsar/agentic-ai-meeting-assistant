# How to Run and Get Real Output

Follow these steps to run the app and verify you get real transcription and meeting minutes.

---

## 1. Get API keys (free)

You need two keys for real output:

| What for       | Where to get it |
|----------------|------------------|
| **Transcription** (Deepgram) | https://console.deepgram.com/signup |
| **Summary + actions** (Gemini) | https://makersuite.google.com/app/apikey |

Sign up, create an API key in each place, and copy the keys.

---

## 2. Run the server

Open a terminal. From the **meeting ai** project folder:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

On **Windows** (Command Prompt):

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
```

Then install dependencies and start the server **with your keys**:

```bash
pip install -r requirements.txt

export DEEPGRAM_API_KEY="paste-your-deepgram-key-here"
export GEMINI_API_KEY="paste-your-gemini-key-here"
export FLASK_APP=run.py
python run.py
```

You should see the server start. Note the URL, e.g. **http://127.0.0.1:5000**.

---

## 3. Open the app

In your browser go to: **http://127.0.0.1:5000**

---

## 4. What to do to check real output

### A. Create a project

1. Click **Setup** in the left sidebar.
2. Under **Create a new project**, type a name (e.g. `Test Project`).
3. Click **Create Project**.

### B. Add a meeting (record OR upload)

Click **Record** in the sidebar.

**Option 1 – Record with your mic**

1. Click **Start Recording**.
2. Speak for **10–30 seconds**. Example:
   - *"Today we discussed the Q1 launch. We decided to go live next Monday. Alice will prepare the slides by Friday. Bob will send the email to the team by tomorrow."*
3. Click **Stop**.
4. Wait for processing (you'll see progress like "Processing… 85% (summary)").
5. When it finishes, the app will switch to **Project Intelligence**.

**Option 2 – Upload an audio file**

1. Under **Upload an existing recording**, click **Choose File** and select an audio file (e.g. `.wav`, `.mp3`, `.m4a`, `.webm`).
2. Optionally enter a meeting title.
3. Click **Upload & Process**.
4. Wait until processing completes and **Project Intelligence** is shown.

### C. Check that you got real output

In **Project Intelligence** you should see:

| Section | What "real" looks like |
|--------|-------------------------|
| **Meeting minutes** | A proper **Summary** (not "ASR disabled" or a raw stub). **Decisions** and **Action items extracted** filled from your speech. |
| **Pending action items** | One or more tasks (e.g. "Alice — do — prepare the slides — By …"). |
| **Meetings (history)** | Your meeting with status **processed**. |

If you see a normal summary, decisions, and action items (and not placeholder text), real output is working.

---

## 5. Quick test sentence

If you're recording with the mic, you can say exactly:

- *"We decided to use the new API. Sarah will update the documentation by next Monday."*

You should then see:

- One decision (e.g. "We decided to use the new API").
- One action item (Sarah, update the documentation, by next Monday).

---

## Troubleshooting

- **No real summary / still see "ASR disabled"**  
  Make sure `DEEPGRAM_API_KEY` and `GEMINI_API_KEY` are set in the same terminal where you run `python run.py`. Restart the server after setting them.

- **Processing fails or stays on "processing"**  
  Check the terminal where the server is running for errors. Typical causes: invalid API key, no internet, or audio too short/empty.

- **Port 5000 already in use**  
  Run on another port: `PORT=5001 python run.py` (or use `bash run.sh`, which may switch to 5001 automatically).
