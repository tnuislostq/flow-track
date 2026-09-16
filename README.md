# FlowTrack 🌸 — Period & Ovulation Forecasting Platform

FlowTrack is a full-stack healthtech web application designed to track menstrual cycles, predict upcoming periods, and forecast fertility windows using rolling statistical averages. Built with a lightweight Python backend and a responsive, mobile-first interface.

---

## Features

- **Dynamic Cycle Forecasting:** Calculates rolling averages from past cycle histories to project future period start dates and cycle lengths.
- **Ovulation & Fertile Windows:** Automatically estimates ovulation and multi-day conception/fertile windows based on biological luteal phase models.
- **Cycle Phase Detection:** Identifies current cycle stages in real-time (Menstrual, Follicular, Ovulation, Luteal).
- **Daily Symptom & Mood Logging:** Records multi-tag symptoms (cramps, bloating, headache), flow intensities, mood shifts, and private journal notes.
- **Historical Overview:** View, audit, and manage previous cycle durations and bleed intervals with instant data deletion options.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3, Flask, SQLAlchemy |
| **Frontend** | HTML5, JavaScript (Fetch API), Tailwind CSS |
| **Database** | SQLite (Local) / PostgreSQL (Production) |
| **WSGI / Server** | Gunicorn |
| **Deployment** | Render Web Services |

---

## Project Structure

```text
flow-track/
├── app.py              # Application logic, REST API & prediction algorithms
├── requirements.txt    # Python dependencies
├── Procfile            # Process manager configuration for production
├── render.yaml         # Blueprint specification for Render deployment
├── .gitignore          # Ignored local files, virtual environments, and databases
└── templates/
    └── index.html      # User interface template
