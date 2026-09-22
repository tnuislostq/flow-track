import os
import io
import csv
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify, send_file, Response
from flask_sqlalchemy import SQLAlchemy
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# 1. Initialize Flask App First
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-12345')

# 2. Database Configuration
db_url = os.environ.get('DATABASE_URL', 'sqlite:///periods.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# 3. Database Models
class Cycle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.Date, nullable=False)
    period_length = db.Column(db.Integer, default=5)
    cycle_length = db.Column(db.Integer, nullable=True)
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
    flow = db.Column(db.String(20), nullable=True)
    mood = db.Column(db.String(50), nullable=True)
    symptoms = db.Column(db.String(255), nullable=True)
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

# 4. Predictive Engine
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
            "current_phase": "Unknown",
            "days_since_start": 0
        }

    cycle_durations = []
    period_durations = []
    for i in range(len(cycles)):
        period_durations.append(cycles[i].period_length or 5)
        if i > 0:
            diff = (cycles[i].start_date - cycles[i-1].start_date).days
            if 20 <= diff <= 45:
                cycles[i].cycle_length = diff
                cycle_durations.append(diff)

    avg_cycle = round(sum(cycle_durations) / len(cycle_durations)) if cycle_durations else 28
    avg_period = round(sum(period_durations) / len(period_durations)) if period_durations else 5

    last_cycle = cycles[-1]
    next_start = last_cycle.start_date + timedelta(days=avg_cycle)

    est_ovulation = next_start - timedelta(days=14)
    fertile_start = est_ovulation - timedelta(days=5)
    fertile_end = est_ovulation + timedelta(days=1)

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

# 5. Application Routes
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

# --- Feature 1: Data Export (CSV / JSON) ---
@app.route('/api/export')
def export_data():
    export_format = request.args.get('format', 'csv').lower()
    cycles = Cycle.query.order_by(Cycle.start_date.asc()).all()
    logs = DailyLog.query.order_by(DailyLog.date.asc()).all()

    if export_format == 'json':
        data = {
            "cycles": [c.to_dict() for c in cycles],
            "logs": [l.to_dict() for l in logs]
        }
        return jsonify(data)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["--- CYCLE HISTORY ---"])
    writer.writerow(["Cycle ID", "Start Date", "Period Length (Days)", "Cycle Interval (Days)"])
    for c in cycles:
        writer.writerow([c.id, c.start_date.strftime('%Y-%m-%d'), c.period_length, c.cycle_length or ''])

    writer.writerow([])
    writer.writerow(["--- DAILY LOGS ---"])
    writer.writerow(["Log ID", "Date", "Flow Intensity", "Mood", "Symptoms", "Notes"])
    for l in logs:
        writer.writerow([l.id, l.date.strftime('%Y-%m-%d'), l.flow or 'None', l.mood or 'None', l.symptoms or 'None', l.notes or ''])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=flowtrack_export_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

# --- Feature 2: PDF Health Report ---
@app.route('/api/report/pdf')
def export_pdf_report():
    cycles = Cycle.query.order_by(Cycle.start_date.asc()).all()
    analytics = get_cycle_analytics()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=20, textColor=colors.HexColor('#8b4a62'), spaceAfter=8)
    sub_style = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#666666'), spaceAfter=14)
    h2_style = ParagraphStyle('H2', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, textColor=colors.HexColor('#3d2931'), spaceBefore=12, spaceAfter=6)

    story = [
        Paragraph("FlowTrack — Health & Menstrual Consultation Summary", title_style),
        Paragraph(f"Generated on {datetime.now().strftime('%B %d, %Y')} • Confidential Health Summary", sub_style),
        Paragraph("Cycle Overview & Averages", h2_style)
    ]

    overview_data = [
        ["Clinical Metric", "Tracked Value", "Population Reference Range"],
        ["Average Cycle Length", f"{analytics['avg_cycle_length']} Days", "21 – 35 days (Regular)"],
        ["Average Period Duration", f"{analytics['avg_period_length']} Days", "2 – 7 days"],
        ["Total Recorded Cycles", f"{len(cycles)}", "Historical database count"],
        ["Current Phase", str(analytics['current_phase']), "Based on days since last period"]
    ]
    t1 = Table(overview_data, colWidths=[160, 140, 240])
    t1.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#fbe6eb')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#8b4a62')),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e8c5cf'))
    ]))
    story.append(t1)

    story.append(Paragraph("Recent Cycle History", h2_style))
    cycle_table_data = [["Cycle #", "Start Date", "Period Length", "Cycle Interval"]]
    for idx, c in enumerate(cycles, 1):
        interval = f"{c.cycle_length} days" if c.cycle_length else "--"
        cycle_table_data.append([str(idx), c.start_date.strftime('%Y-%m-%d'), f"{c.period_length} d", interval])

    if len(cycle_table_data) == 1:
        cycle_table_data.append(["-", "No cycles logged yet", "-", "-"])

    t2 = Table(cycle_table_data, colWidths=[70, 160, 150, 160])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f8edf0')),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e8c5cf'))
    ]))
    story.append(t2)

    doc.build(story)
    buf.seek(0)
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=f"flowtrack_health_report_{datetime.now().strftime('%Y%m%d')}.pdf")

# --- Feature 3: AI Assistant API ---
@app.route('/api/assistant/chat', methods=['POST'])
def assistant_chat():
    data = request.get_json() or {}
    user_msg = data.get('message', '').strip().lower()

    if "cramp" in user_msg or "pain" in user_msg:
        reply = "For menstrual cramps (dysmenorrhea), topical heat (heating pad) and magnesium glycinate can relax uterine muscle contractions. Chamomile or ginger tea can also reduce inflammation. If pain is severe or prevents daily tasks, discuss it with a healthcare professional."
    elif "luteal" in user_msg or "pms" in user_msg or "mood" in user_msg:
        reply = "During the luteal phase (days 15–28), progesterone rises and then drops, which can trigger mood swings, cravings, and fatigue. Complex carbohydrates (sweet potatoes, oats), B6 vitamins, and light walking can help stabilize serotonin."
    elif "ovulat" in user_msg or "fertile" in user_msg:
        reply = "Ovulation typically occurs around 14 days before your next period starts. The fertile window spans the 5 days before ovulation plus ovulation day itself, because sperm can survive up to 5 days in fertile cervical fluid."
    elif "food" in user_msg or "diet" in user_msg or "eat" in user_msg:
        reply = "Cycle syncing nutrition:\n• Menstrual: Iron-rich foods, warm stews, dark chocolate\n• Follicular: Fermented foods, lean proteins, fresh veggies\n• Ovulatory: Berries, zinc, antioxidant-rich foods\n• Luteal: Magnesium, fiber (leafy greens), complex carbs"
    elif "delay" in user_msg or "late" in user_msg or "irregular" in user_msg:
        reply = "A period can shift due to stress, travel, changes in sleep, hormonal fluctuations, or illness. A variation of 2–7 days is common. If your period is over 10 days late or multiple cycles are irregular, a medical consult is recommended."
    else:
        reply = "I'm your FlowTrack assistant. You can ask me about symptom relief (e.g. cramps, headaches), cycle phases (follicular, ovulatory, luteal), nutrition tips, or interpreting your cycle length data."

    return jsonify({"reply": reply})

# --- Feature 4: Personalized Educational Content API ---
@app.route('/api/education')
def get_education_content():
    return jsonify({
        "menstrual": {
            "title": "Menstrual Phase (Days 1–5)",
            "hormones": "Estrogen and progesterone are at their lowest levels.",
            "energy": "Restorative, quiet, introspective.",
            "nutrition": "Warm soups, iron-rich spinach, lentils, and magnesium for muscle relaxation.",
            "movement": "Gentle stretching, restorative yoga, walks."
        },
        "follic
