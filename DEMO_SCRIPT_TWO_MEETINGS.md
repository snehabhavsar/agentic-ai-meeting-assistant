# Demo script: 2 meetings with context (Eliz, Sneha, Gargi)

Use **one project** for both meetings so the system can use context from Meeting 1 when processing Meeting 2.

---

## How the system knows *who* will do it

The app does **not** use speaker diarization (no “Speaker 1 / Speaker 2” from the audio). The summarizer only sees **one block of transcript text**. So if someone says *“I will do task 1”* with no name in the sentence, the system cannot tell who said it and may show assignee as “Not specified”.

**Make sure the transcript text includes the name:**

- **Option A – Self‑identify:** The person committing says their own name, e.g. *“This is Sneha, I will do task 1 today”* or *“Sneha here — I’ll do task 1, the auth module, today.”*
- **Option B – Third person:** Someone else says the name and task, e.g. Eliz: *“Sneha will do task 1 today”* or *“Sneha, you’ll take task 1?”* and Sneha: *“Yes, I will do task 1 today.”*

The script below uses both: Eliz names people when assigning, and **Sneha says her name** when she commits to task 1 so the model can attribute it to her reliably.

---

## Will the repeated commitment get noticed?

Yes. When you process Meeting 2, the app sends Meeting 1’s summary and **pending action items** (e.g. “Sneha – Task 1”) to the summarizer. The prompt tells the model: if someone commits again to a task that’s already in PENDING ACTION ITEMS, **explicitly note that they did not complete it on time**. So saying “today I will do task 1” again in Meeting 2 should show up as a repeated/unfulfilled commitment.  
*(Requires `GEMINI_API_KEY` in `backend/.env`.)*

---

## Meeting 1 – Kickoff

**Setup:** Create a project (e.g. “Q1 Launch”). Start recording. Read the lines below in order. **Important:** Sneha’s line must include her **name** so the system attributes task 1 to her (e.g. “This is Sneha” or “Sneha here”).

| Speaker | Line |
|--------|------|
| **Eliz** | Hey everyone, thanks for joining. Quick sync on the Q1 launch. Let’s assign owners. |
| **Gargi** | This is Gargi. I can own the deck. I’ll have the first draft by Friday. |
| **Eliz** | Perfect, Gargi. Sneha, what about you? |
| **Sneha** | This is Sneha. I’ll take the API integration. Today I will do task 1, the auth module. I’ll finish it today. |
| **Eliz** | Great. I’ll handle the design review. So we have Gargi on the deck, Sneha on task 1 the auth module today, and me on design. Same time next week? |
| **Gargi** | Works for me. |
| **Sneha** | Yes. |
| **Eliz** | Done. Talk then. |

**Stop recording.** Wait for processing. Check the summary and action items: you should see **Sneha – Task 1 / auth module** as a pending action.

---

## Meeting 2 – Follow-up (same project)

**Setup:** In the **same project**, start a **new meeting** and record. Here Sneha says again that she will do “task 1” today, so the system should treat it as a **repeated commitment** (not done on time).

| Speaker | Line |
|--------|------|
| **Eliz** | Welcome back. Quick follow-up from last week. Gargi, how’s the deck? |
| **Gargi** | This is Gargi. Done. I shared it yesterday. |
| **Eliz** | Thanks. Sneha, what about the auth module, task 1? |
| **Sneha** | Sneha here. I’m on it. Today I will do task 1. I’ll get it done today. |
| **Eliz** | Okay, let’s aim for EOD. I’ll send the design feedback by tomorrow. |
| **Gargi** | Sounds good. |
| **Sneha** | Sure. |
| **Eliz** | Thanks everyone. |

**Stop recording.** Wait for processing.

**What to check:**  
In Meeting 2’s summary (or “additional notes”), the system should **explicitly note** that Sneha committed again to the same task (Task 1 / auth module) that was already pending from Meeting 1 — i.e. that she did not complete it on time. Pending action items may still show Task 1 for Sneha, now linked to the same carry-forward item.

---

## Tips

- **Same project:** Both meetings must be under the same project so context (summaries + pending actions) is reused.
- **Names in the transcript:** So the system can attribute tasks, have each person say their name when they commit (e.g. “This is Sneha, I will do task 1 today”). The app has no speaker IDs from the audio — it only sees the words.
- **ASR misrecognized names (e.g. “kagi” for Gargi):** Use **Speaker name corrections** in the project: add a mapping like `kagi → Gargi`. Summaries and action item labels will show “Gargi”; the stored transcript text is not changed.
- **Clear wording:** Use “task 1” or “the auth module” in both meetings so the model can match the same pending item.
- **Gemini:** Set `GEMINI_API_KEY` (and optionally `DEEPGRAM_API_KEY`) in `backend/.env` for real summarization and context behavior.
- **Recording:** You can read the lines aloud in turn, or paraphrase; keep the name + task in the same turn so the model can assign correctly.
