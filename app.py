import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-12345')

# Database: Uses DATABASE_URL if deployed with Postgres on Render, else local SQLite
db_url = os.environ.get('DATABASE_URL', 'sqlite:///periods.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ----------------- Database Models -----------------
class Cycle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.Date, nullable=False)
    period_length = db.Column(db.Integer, default=5) # Days of bleeding
    cycle_length = db.Column(db.Integer, nullable=True) # Computed between consecutive periods
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "start_date": self.start_date.strftime("%Y-%m-%d"),
            "period_length": self.period_length,
            "cycle_length": self.cycle_length
        }

class DailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    flow = db.Column(db.String(20), nullable=True) # light, medium, heavy, spotting
    mood = db.Column(db.String(50), nullable=True)
    symptoms = db.Column(db.String(255), nullable=True) # comma separated
    notes = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date.strftime("%Y-%m-%d"),
            "flow": self.flow,
            "mood": self.mood,
            "symptoms": self.symptoms.split(",") if self.symptoms else [],
            "notes": self.notes
        }

with app.app_context():
    db.create_all()

# ----------------- Predictive Engine -----------------
def get_cycle_analytics():
    cycles = Cycle.query.order_by(Cycle.start_date.asc()).all()
    if not cycles:
        return {
            "avg_cycle_length": 28,
            "avg_period_length": 5,
            "next_period_start": None,
            "ovulation_date": None,
            "fertile_window_start": None,
            "fertile_window_end": None,
            "current_phase": "Unknown"
        }

    # Update cycle lengths between consecutive cycles
    cycle_durations = []
    period_durations = []
    for i in range(len(cycles)):
        period_durations.append(cycles[i].period_length or 5)
        if i > 0:
            diff = (cycles[i].start_date - cycles[i-1].start_date).days
            if 20 <= diff <= 45: # Filter valid biological ranges
                cycles[i].cycle_length = diff
                cycle_durations.append(diff)
    
    avg_cycle = round(sum(cycle_durations) / len(cycle_durations)) if cycle_durations else 28
    avg_period = round(sum(period_durations) / len(period_durations)) if period_durations else 5
    
    last_cycle = cycles[-1]
    next_start = last_cycle.start_date + timedelta(days=avg_cycle)
    
    # Luteal phase standard: ovulation happens roughly 14 days before next cycle
    est_ovulation = next_start - timedelta(days=14)
    fertile_start = est_ovulation - timedelta(days=5)
    fertile_end = est_ovulation + timedelta(days=1)
    
    # Determine current cycle day and phase
    today = datetime.now().date()
    days_since_start = (today - last_cycle.start_date).days

    if 0 <= days_since_start < avg_period:
        phase = "Menstrual Phase"
    elif days_since_start < (avg_cycle - 16):
        phase = "Follicular Phase"
    elif (avg_cycle - 16) <= days_since_start <= (avg_cycle - 12):
        phase = "Ovulation Window"
    elif days_since_start < avg_cycle:
        phase = "Luteal Phase"
    else:
        phase = "Cycle Overdue / Upcoming"

    return {
        "avg_cycle_length": avg_cycle,
        "avg_period_length": avg_period,
        "next_period_start": next_start.strftime("%Y-%m-%d"),
        "ovulation_date": est_ovulation.strftime("%Y-%m-%d"),
        "fertile_window_start": fertile_start.strftime("%Y-%m-%d"),
        "fertile_window_end": fertile_end.strftime("%Y-%m-%d"),
        "current_phase": phase,
        "days_since_start": days_since_start
    }

# ----------------- Routes -----------------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/analytics', methods=['GET'])
def analytics():
    return jsonify(get_cycle_analytics())

@app.route('/api/cycles', methods=['GET', 'POST'])
def handle_cycles():
    if request.method == 'POST':
        data = request.get_json() or {}
        start_date_str = data.get('start_date')
        period_length = int(data.get('period_length', 5))
        
        if not start_date_str:
            return jsonify({"error": "start_date is required"}), 400
            
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        cycle = Cycle(start_date=start_date, period_length=period_length)
        db.session.add(cycle)
        db.session.commit()
        return jsonify({"message": "Cycle logged successfully", "cycle": cycle.to_dict()}), 201

    cycles = Cycle.query.order_by(Cycle.start_date.desc()).all()
    return jsonify([c.to_dict() for c in cycles])

@app.route('/api/cycles/<int:cycle_id>', methods=['DELETE'])
def delete_cycle(cycle_id):
    cycle = Cycle.query.get_or_404(cycle_id)
    db.session.delete(cycle)
    db.session.commit()
    return jsonify({"message": "Cycle deleted"})

@app.route('/api/logs', methods=['GET', 'POST'])
def handle_logs():
    if request.method == 'POST':
        data = request.get_json() or {}
        log_date_str = data.get('date')
        if not log_date_str:
            return jsonify({"error": "date is required"}), 400

        log_date = datetime.strptime(log_date_str, "%Y-%m-%d").date()
        existing = DailyLog.query.filter_by(date=log_date).first()

        symptoms_str = ",".join(data.get('symptoms', [])) if isinstance(data.get('symptoms'), list) else data.get('symptoms', '')

        if existing:
            existing.flow = data.get('flow', existing.flow)
            existing.mood = data.get('mood', existing.mood)
            existing.symptoms = symptoms_str
            existing.notes = data.get('notes', existing.notes)
        else:
            existing = DailyLog(
                date=log_date,
                flow=data.get('flow'),
                mood=data.get('mood'),
                symptoms=symptoms_str,
                notes=data.get('notes')
            )
            db.session.add(existing)

        db.session.commit()
        return jsonify({"message": "Daily log saved", "log": existing.to_dict()}), 200

    logs = DailyLog.query.order_by(DailyLog.date.desc()).limit(30).all()
    return jsonify([l.to_dict() for l in logs])

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)