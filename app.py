from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
import sqlite3
from datetime import datetime, timedelta
import json

app = Flask(__name__)
app.secret_key = 'gbv_secret_key'  # Change in production

# DB Setup
DB_NAME = 'gbv.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Schema based on PDF form (key fields for analytics)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gbv_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serial_no TEXT,
            national_id TEXT,
            gender TEXT,  -- M/F/O
            age INTEGER,
            arrival_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            client_name TEXT,
            address TEXT,
            contact_no TEXT,
            next_of_kin TEXT,
            marital_status TEXT,
            report_date DATETIME,
            police_report TEXT,  -- Y/N
            incident_date DATE,
            type_violence TEXT,  -- Physical/Sexual/Emotional/Economic/Other
            perpetrator_relation TEXT,
            type_case TEXT,
            hiv_test_initial TEXT,  -- Neg/KP/ND
            pregnancy_test TEXT,  -- Pos/Neg/ND
            pep_given TEXT,  -- Y/N
            referral TEXT,  -- Y/N
            facility_name TEXT
        )
    ''')
    # Insert sample data for demo (10 records; using 2026 dates to match current year)
    sample_data = [
        ('001', 'UG123456', 'F', 25, '2026-01-01 10:00', 'Jane Doe', 'Kampala', '0771234567', 'John Doe: 0777654321', 'Married', '2026-01-01 09:00', 'Y', '2025-12-31', 'Sexual', 'Partner', 'Rape', 'Neg', 'Neg', 'Y', 'Y', 'Kayunga Hospital'),
        ('002', 'UG789012', 'M', 15, '2026-01-02 14:30', 'John Smith', 'Nakasongola', '0789876543', 'Mary Smith: 0783456789', 'Single', '2026-01-02 13:00', 'N', '2026-01-01', 'Physical', 'Stranger', 'Assault', 'ND', 'Neg', 'N', 'N', 'Kayunga Hospital'),
        ('003', 'UG345678', 'F', 30, '2026-01-03 08:15', 'Alice Johnson', 'Kayunga', '0778765432', 'Bob Johnson: 0772345678', 'Married', '2026-01-03 07:45', 'Y', '2026-01-02', 'Emotional', 'Family', 'Harassment', 'Neg', 'ND', 'N', 'Y', 'Kayunga Hospital'),
        ('004', 'UG901234', 'F', 12, '2026-01-04 16:20', 'Child Victim', 'Mukono', '0781234567', 'Guardian: 0787654321', 'Single', '2026-01-04 15:50', 'Y', '2026-01-03', 'Sexual', 'Relative', 'Abuse', 'KP', 'Pos', 'Y', 'Y', 'Kayunga Hospital'),
        ('005', 'UG567890', 'O', 40, '2026-01-05 11:00', 'Alex Nonbinary', 'Entebbe', '0774567890', 'Friend: 0778901234', 'Divorced', '2026-01-05 10:30', 'N', '2026-01-04', 'Economic', 'Employer', 'Exploitation', 'Neg', 'Neg', 'N', 'N', 'Kayunga Hospital'),
        ('006', 'UG234567', 'M', 22, '2026-01-06 09:45', 'Mike Lee', 'Jinja', '0785678901', 'Sister: 0780123456', 'Single', '2026-01-06 09:15', 'Y', '2026-01-05', 'Physical', 'Acquaintance', 'Battery', 'ND', 'Neg', 'N', 'Y', 'Kayunga Hospital'),
        ('007', 'UG890123', 'F', 18, '2026-01-07 13:30', 'Sara Kim', 'Wakiso', '0773456789', 'Mother: 0776789012', 'Single', '2026-01-07 13:00', 'N', '2026-01-06', 'Sexual', 'Stranger', 'Assault', 'Neg', 'Neg', 'Y', 'Y', 'Kayunga Hospital'),
        ('008', 'UG456789', 'M', 35, '2026-01-08 17:10', 'Tom Brown', 'Luweero', '0782345678', 'Wife: 0789012345', 'Married', '2026-01-08 16:40', 'Y', '2026-01-07', 'Emotional', 'Partner', 'Abuse', 'Neg', 'ND', 'N', 'N', 'Kayunga Hospital'),
        ('009', 'UG123789', 'F', 28, '2026-01-09 12:00', 'Eva Green', 'Nairobi', '0775678901', 'Brother: 0771234567', 'Widowed', '2026-01-09 11:30', 'Y', '2026-01-08', 'Economic', 'Family', 'Neglect', 'KP', 'Neg', 'N', 'Y', 'Kayunga Hospital'),
        ('010', 'UG678901', 'O', 16, '2026-01-10 15:45', 'Riley Taylor', 'Kampala', '0783456789', 'Parent: 0787890123', 'Single', '2026-01-10 15:15', 'N', '2026-01-09', 'Physical', 'Schoolmate', 'Bullying', 'ND', 'Neg', 'N', 'Y', 'Kayunga Hospital'),
    ]
    cursor.executemany('''
        INSERT OR IGNORE INTO gbv_records (serial_no, national_id, gender, age, arrival_date, client_name, address, contact_no, next_of_kin, marital_status, report_date, police_report, incident_date, type_violence, perpetrator_relation, type_case, hiv_test_initial, pregnancy_test, pep_given, referral, facility_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', sample_data)
    conn.commit()
    conn.close()

init_db()

# Helper: Get DB connection
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# Route 1: Data Entry Form
@app.route('/', methods=['GET', 'POST'])
def data_entry():
    if request.method == 'POST':
        conn = get_db()
        cursor = conn.cursor()
        # Auto-fill current date/time for arrival and report
        now = datetime.now()
        try:
            cursor.execute('''
                INSERT INTO gbv_records (serial_no, national_id, gender, age, arrival_date, client_name, address, contact_no, next_of_kin, marital_status,
                                         report_date, police_report, incident_date, type_violence, perpetrator_relation, type_case, hiv_test_initial,
                                         pregnancy_test, pep_given, referral, facility_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                request.form['serial_no'], request.form['national_id'], request.form['gender'], int(request.form['age']) if request.form['age'] else 0,
                now, request.form['client_name'], request.form['address'], request.form['contact_no'], request.form['next_of_kin'],
                request.form['marital_status'], now, request.form['police_report'], request.form['incident_date'], request.form['type_violence'],
                request.form['perpetrator_relation'], request.form['type_case'], request.form['hiv_test_initial'], request.form['pregnancy_test'],
                request.form['pep_given'], request.form['referral'], request.form['facility_name']
            ))
            conn.commit()
            flash('Record added successfully!')
        except Exception as e:
            flash(f'Error adding record: {str(e)}')
        finally:
            conn.close()
        return redirect(url_for('data_entry'))
    return render_template('form.html')

# Route 2: Records Management
@app.route('/records')
def records():
    search = request.args.get('search', '')
    gender_filter = request.args.get('gender', '')
    conn = get_db()
    cursor = conn.cursor()
    query = '''
        SELECT * FROM gbv_records 
        WHERE client_name LIKE ? OR national_id LIKE ?
    '''
    params = [f'%{search}%', f'%{search}%']
    if gender_filter:
        query += ' AND gender = ?'
        params.append(gender_filter)
    query += ' ORDER BY arrival_date DESC'
    cursor.execute(query, params)
    records_list = cursor.fetchall()
    conn.close()
    return render_template('records.html', records=records_list, search=search, gender_filter=gender_filter)

# Route 3: Reports (Dynamic by period)
@app.route('/reports')
def reports():
    period = request.args.get('period', 'daily')  # daily/weekly/monthly/quarterly/yearly
    end_date = datetime.now()
    if period == 'daily':
        start_date = end_date - timedelta(days=1)
    elif period == 'weekly':
        start_date = end_date - timedelta(weeks=1)
    elif period == 'monthly':
        start_date = end_date.replace(day=1)
    elif period == 'quarterly':
        quarter_start_month = ((end_date.month - 1) // 3 * 3) + 1
        start_date = end_date.replace(month=quarter_start_month, day=1)
    elif period == 'yearly':
        start_date = end_date.replace(month=1, day=1)
    else:
        start_date = end_date - timedelta(days=30)  # Default

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM gbv_records 
        WHERE arrival_date BETWEEN ? AND ?
        ORDER BY arrival_date
    ''', (start_date, end_date))
    report_records = cursor.fetchall()
    conn.close()
    return render_template('reports.html', records=report_records, period=period, start_date=start_date.strftime('%Y-%m-%d'), end_date=end_date.strftime('%Y-%m-%d'))

# Route 4: Analytics Dashboard (KPIs + Charts Data)
@app.route('/dashboard')
def dashboard():
    start_date_str = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

    conn = get_db()
    cursor = conn.cursor()

    # KPIs
    cursor.execute('SELECT COUNT(*) FROM gbv_records WHERE arrival_date BETWEEN ? AND ?', (start_date, end_date))
    total_cases = cursor.fetchone()[0] or 0

    cursor.execute('SELECT COUNT(*) FROM gbv_records WHERE gender = "F" AND arrival_date BETWEEN ? AND ?', (start_date, end_date))
    female_count = cursor.fetchone()[0] or 0
    female_pct = round((female_count / total_cases * 100) if total_cases else 0, 1)

    cursor.execute('SELECT COUNT(*) FROM gbv_records WHERE age < 18 AND arrival_date BETWEEN ? AND ?', (start_date, end_date))
    minors_count = cursor.fetchone()[0] or 0
    minors_pct = round((minors_count / total_cases * 100) if total_cases else 0, 1)

    cursor.execute('SELECT COUNT(*) FROM gbv_records WHERE referral = "Y" AND arrival_date BETWEEN ? AND ?', (start_date, end_date))
    referred_count = cursor.fetchone()[0] or 0
    referred_pct = round((referred_count / total_cases * 100) if total_cases else 0, 1)

    # Most affected day of week (0=Sun, 1=Mon, etc.)
    cursor.execute('SELECT strftime("%w", arrival_date) as day_num, COUNT(*) FROM gbv_records WHERE arrival_date BETWEEN ? AND ? GROUP BY day_num ORDER BY COUNT(*) DESC LIMIT 1', (start_date, end_date))
    most_affected = cursor.fetchone()
    most_affected_day = most_affected[0] if most_affected else 'N/A'

    # Chart Data (JSON-ready)
    # 1. Cases Over Time (Monthly)
    cursor.execute('SELECT strftime("%Y-%m", arrival_date) as month, COUNT(*) FROM gbv_records WHERE arrival_date BETWEEN ? AND ? GROUP BY month ORDER BY month', (start_date, end_date))
    time_data = cursor.fetchall()
    time_labels = [row[0] for row in time_data]
    time_values = [row[1] for row in time_data]

    # 2. By Gender
    cursor.execute('SELECT gender, COUNT(*) FROM gbv_records WHERE arrival_date BETWEEN ? AND ? GROUP BY gender', (start_date, end_date))
    gender_data = cursor.fetchall()
    gender_labels = [row[0] or 'Unknown' for row in gender_data]
    gender_values = [row[1] for row in gender_data]

    # 3. Type of Violence
    cursor.execute('SELECT type_violence, COUNT(*) FROM gbv_records WHERE arrival_date BETWEEN ? AND ? GROUP BY type_violence', (start_date, end_date))
    violence_data = cursor.fetchall()
    violence_labels = [row[0] or 'Unknown' for row in violence_data]
    violence_values = [row[1] for row in violence_data]

    # 4. Age Groups
    cursor.execute('''
        SELECT 
            CASE 
                WHEN age < 10 THEN '0-9'
                WHEN age < 18 THEN '10-17'
                WHEN age < 25 THEN '18-24'
                WHEN age < 50 THEN '25-49'
                ELSE '50+'
            END as age_group, COUNT(*)
        FROM gbv_records WHERE arrival_date BETWEEN ? AND ? GROUP BY age_group
    ''', (start_date, end_date))
    age_data = cursor.fetchall()
    age_labels = [row[0] or 'Unknown' for row in age_data]
    age_values = [row[1] for row in age_data]

    # 5. Referrals
    cursor.execute('SELECT referral, COUNT(*) FROM gbv_records WHERE arrival_date BETWEEN ? AND ? GROUP BY referral', (start_date, end_date))
    referral_data = cursor.fetchall()
    referral_labels = [row[0] or 'Unknown' for row in referral_data]
    referral_values = [row[1] for row in referral_data]

    conn.close()

    # Pass to template as JSON
    chart_data = {
        'time': {'labels': time_labels, 'values': time_values},
        'gender': {'labels': gender_labels, 'values': gender_values},
        'violence': {'labels': violence_labels, 'values': violence_values},
        'age': {'labels': age_labels, 'values': age_values},
        'referral': {'labels': referral_labels, 'values': referral_values}
    }

    return render_template('dashboard.html', 
                          total_cases=total_cases, female_pct=female_pct, minors_pct=minors_pct, 
                          referred_pct=referred_pct, most_affected_day=most_affected_day,
                          chart_data=json.dumps(chart_data), start_date=start_date_str, end_date=end_date_str)

if __name__ == '__main__':
    app.run(debug=True)