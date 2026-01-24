from flask import Flask, render_template, request, flash, redirect, url_for, send_file, session
import sqlite3
from datetime import datetime, timedelta
import json
import pandas as pd
from io import BytesIO
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'gbv_secret_key_2026'  # Changing  this in production!

# Database
DB_NAME = 'gbv.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # GBV Records Table (same as before)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gbv_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serial_no TEXT,
            arrival_datetime TEXT,
            national_id TEXT,
            client_name TEXT,
            address TEXT,
            contact_no TEXT,
            next_of_kin TEXT,
            ovc TEXT,
            age INTEGER,
            sex TEXT,
            marital_status TEXT,
            incident_datetime TEXT,
            medical_form_filled TEXT,
            p3_form TEXT,
            disability TEXT,
            perpetrator_relation TEXT,
            type_violence TEXT,
            type_case TEXT,
            hiv_test_initial TEXT,
            pregnancy_test TEXT,
            anal_swab TEXT,
            hvs TEXT,
            spermatozoa TEXT,
            urinalysis TEXT,
            hep_b_initial TEXT,
            syphilis_initial TEXT,
            ecp_given TEXT,
            pep_given TEXT,
            sti_treatment TEXT,
            trauma_counseling_initial TEXT,
            adherence_counseling_initial TEXT,
            tt_given_initial TEXT,
            hep_b_vaccine_initial TEXT,
            syphilis_treatment TEXT,
            referral_initial TEXT,
            facility_name TEXT,
            
            -- 2 Weeks Follow-up
            actual_return_2w TEXT,
            next_appointment_2w TEXT,
            referral_2w TEXT,
            trauma_2w TEXT,
            adherence_2w TEXT,
            pep_refill_2w TEXT,
            hiv_2w TEXT,
            pregnancy_2w TEXT,
            hb_2w REAL,
            alt_2w INTEGER,
            hep_b_1st_2w TEXT,
            tt_2w TEXT,
            syphilis_2w TEXT,
            referral_update_2w TEXT,
            -- 1 Month Follow-up
            actual_return_1m TEXT,
            next_appointment_1m TEXT,
            referral_1m TEXT,
            trauma_1m TEXT,
            adherence_1m TEXT,
            pep_refill_1m TEXT,
            pep_completion TEXT,
            hiv_1m TEXT,
            pregnancy_1m TEXT,
            hb_1m REAL,
            alt_1m INTEGER,
            hep_b_2nd_1m TEXT,
            tt_1m TEXT,
            syphilis_1m TEXT,
            referral_update_1m TEXT,
            -- 3 Months Follow-up
            actual_return_3m TEXT,
            next_appointment_3m TEXT,
            referral_3m TEXT,
            trauma_3m TEXT,
            adherence_3m TEXT,
            hiv_3m TEXT,
            hep_b_3m TEXT,
            syphilis_3m TEXT,
            hb_3m REAL,
            alt_3m INTEGER,
            hep_b_3rd_3m TEXT,
            pregnancy_3m TEXT,
            referral_update_3m TEXT,
            -- 6 Months Follow-up
            actual_return_6m TEXT,
            next_appointment_6m TEXT,
            referral_6m TEXT,
            trauma_6m TEXT,
            hiv_6m TEXT,
            hep_b_6m TEXT,
            syphilis_6m TEXT,
            referral_update_6m TEXT,
            client_outcome TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Users Table for Authentication
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL  -- 'admin' or 'nurse'
        )
    ''')
    
    # Create default admin if not exists
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        hashed_pw = generate_password_hash('adminpassword')  # Change this!
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ('admin', hashed_pw, 'admin'))
    
    conn.commit()
    conn.close()

init_db()  # Creates the tables on first run

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# Safe conversion helpers
def to_float(val, default=0.0):
    try:
        return float(val) if val not in (None, '', 'ND', 'NA') else default
    except:
        return default

def to_int(val, default=0):
    try:
        return int(val) if val not in (None, '', 'ND', 'NA') else default
    except:
        return default

# Login Required Decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Admin Required Decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_role' not in session or session['user_role'] != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_db()
        user = conn.execute(
            'SELECT * FROM users WHERE username = ?',
            (username,)
        ).fetchone()
        conn.close()

        # ────────────────────────────────────────────────
        # This is the safe check – never accessing  user['...'] if user is None
        if user is None or not check_password_hash(user['password'], password):
            flash('Invalid username or password.', 'danger')
            return render_template('login.html')

        # Success
        session['user_id'] = user['id']
        session['user_role'] = user['role']
        flash('Logged in successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/admin/users', methods=['GET', 'POST'])
@admin_required
def manage_users():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')  # 'admin' or 'nurse'

        if role not in ['admin', 'nurse']:
            flash('Invalid role selected.', 'danger')
            return redirect(url_for('manage_users'))

        hashed_pw = generate_password_hash(password)
        conn = get_db()
        try:
            conn.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
                        (username, hashed_pw, role))
            conn.commit()
            flash(f'{role.capitalize()} account created successfully!', 'success')
        except sqlite3.IntegrityError:
            flash('Username already exists.', 'danger')
        finally:
            conn.close()
        return redirect(url_for('manage_users'))

    conn = get_db()
    users = conn.execute('SELECT id, username, role FROM users ORDER BY role, username').fetchall()
    conn.close()
    return render_template('manage_users.html', users=users)

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    conn = get_db()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    flash('User deleted successfully.', 'success')
    return redirect(url_for('manage_users'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data_entry', methods=['GET', 'POST'])
@login_required
def data_entry():
    if request.method == 'POST':
        conn = get_db()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            data = (
                request.form.get('serial_no'),
                request.form.get('arrival_datetime') or None,
                request.form.get('national_id'),
                request.form.get('client_name'),
                request.form.get('address'),
                request.form.get('contact_no'),
                request.form.get('next_of_kin'),
                request.form.get('ovc'),
                to_int(request.form.get('age')),
                request.form.get('sex'),
                request.form.get('marital_status'),
                request.form.get('incident_datetime') or None,
                request.form.get('medical_form_filled') or None,
                request.form.get('p3_form'),
                request.form.get('disability'),
                request.form.get('perpetrator_relation'),
                request.form.get('type_violence'),
                request.form.get('type_case'),
                request.form.get('hiv_test_initial'),
                request.form.get('pregnancy_test'),
                request.form.get('anal_swab'),
                request.form.get('hvs'),
                request.form.get('spermatozoa'),
                request.form.get('urinalysis'),
                request.form.get('hep_b_initial'),
                request.form.get('syphilis_initial'),
                request.form.get('ecp_given'),
                request.form.get('pep_given'),
                request.form.get('sti_treatment'),
                request.form.get('trauma_counseling_initial'),
                request.form.get('adherence_counseling_initial'),
                request.form.get('tt_given_initial'),
                request.form.get('hep_b_vaccine_initial'),
                request.form.get('syphilis_treatment'),
                request.form.get('referral_initial'),
                request.form.get('facility_name'),
                # 2 Weeks
                request.form.get('actual_return_2w') or None,
                request.form.get('next_appointment_2w') or None,
                request.form.get('referral_2w'),
                request.form.get('trauma_2w'),
                request.form.get('adherence_2w'),
                request.form.get('pep_refill_2w'),
                request.form.get('hiv_2w'),
                request.form.get('pregnancy_2w'),
                to_float(request.form.get('hb_2w')),
                to_int(request.form.get('alt_2w')),
                request.form.get('hep_b_1st_2w'),
                request.form.get('tt_2w'),
                request.form.get('syphilis_2w'),
                request.form.get('referral_update_2w'),
                # 1 Month
                request.form.get('actual_return_1m') or None,
                request.form.get('next_appointment_1m') or None,
                request.form.get('referral_1m'),
                request.form.get('trauma_1m'),
                request.form.get('adherence_1m'),
                request.form.get('pep_refill_1m'),
                request.form.get('pep_completion'),
                request.form.get('hiv_1m'),
                request.form.get('pregnancy_1m'),
                to_float(request.form.get('hb_1m')),
                to_int(request.form.get('alt_1m')),
                request.form.get('hep_b_2nd_1m'),
                request.form.get('tt_1m'),
                request.form.get('syphilis_1m'),
                request.form.get('referral_update_1m'),
                # 3 Months
                request.form.get('actual_return_3m') or None,
                request.form.get('next_appointment_3m') or None,
                request.form.get('referral_3m'),
                request.form.get('trauma_3m'),
                request.form.get('adherence_3m'),
                request.form.get('hiv_3m'),
                request.form.get('hep_b_3m'),
                request.form.get('syphilis_3m'),
                to_float(request.form.get('hb_3m')),
                to_int(request.form.get('alt_3m')),
                request.form.get('hep_b_3rd_3m'),
                request.form.get('pregnancy_3m'),
                request.form.get('referral_update_3m'),
                # 6 Months
                request.form.get('actual_return_6m') or None,
                request.form.get('next_appointment_6m') or None,
                request.form.get('referral_6m'),
                request.form.get('trauma_6m'),
                request.form.get('hiv_6m'),
                request.form.get('hep_b_6m'),
                request.form.get('syphilis_6m'),
                request.form.get('referral_update_6m'),
                request.form.get('client_outcome'),
                now
            )
            cursor.execute('''
                INSERT INTO gbv_records (
                    serial_no, arrival_datetime, national_id, client_name, address, contact_no, next_of_kin, ovc, age, sex,
                    marital_status, incident_datetime, medical_form_filled, p3_form, disability, perpetrator_relation,
                    type_violence, type_case, hiv_test_initial, pregnancy_test, anal_swab, hvs, spermatozoa, urinalysis,
                    hep_b_initial, syphilis_initial, ecp_given, pep_given, sti_treatment, trauma_counseling_initial,
                    adherence_counseling_initial, tt_given_initial, hep_b_vaccine_initial, syphilis_treatment, referral_initial,
                    facility_name,
                    actual_return_2w, next_appointment_2w, referral_2w, trauma_2w, adherence_2w, pep_refill_2w, hiv_2w,
                    pregnancy_2w, hb_2w, alt_2w, hep_b_1st_2w, tt_2w, syphilis_2w, referral_update_2w,
                    actual_return_1m, next_appointment_1m, referral_1m, trauma_1m, adherence_1m, pep_refill_1m, pep_completion,
                    hiv_1m, pregnancy_1m, hb_1m, alt_1m, hep_b_2nd_1m, tt_1m, syphilis_1m, referral_update_1m,
                    actual_return_3m, next_appointment_3m, referral_3m, trauma_3m, adherence_3m, hiv_3m, hep_b_3m, syphilis_3m,
                    hb_3m, alt_3m, hep_b_3rd_3m, pregnancy_3m, referral_update_3m,
                    actual_return_6m, next_appointment_6m, referral_6m, trauma_6m, hiv_6m, hep_b_6m, syphilis_6m,
                    referral_update_6m, client_outcome, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', data)
            
            conn.commit()
            flash('Record added successfully!', 'success')
        except Exception as e:
            flash(f'Error adding record: {str(e)}', 'danger')
        finally:
            conn.close()
        
        return redirect(url_for('data_entry'))
    
    return render_template('form.html')

# Other routes remain the same, but we add @login_required to them
@app.route('/records')
@login_required
def records():
    conn = get_db()
    records_list = conn.execute('SELECT * FROM gbv_records ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('records.html', records=records_list)

@app.route('/reports')
@login_required
def reports():
    period = request.args.get('period', 'all') # all/daily/weekly/monthly/quarterly/yearly
    end_date = datetime.now()
    start_date = None
    period_name = 'All Time'
    if period == 'daily':
        start_date = end_date - timedelta(days=1)
        period_name = 'Daily'
    elif period == 'weekly':
        start_date = end_date - timedelta(weeks=1)
        period_name = 'Weekly'
    elif period == 'monthly':
        start_date = end_date.replace(day=1)
        period_name = 'Monthly'
    elif period == 'quarterly':
        quarter_start_month = ((end_date.month - 1) // 3 * 3) + 1
        start_date = end_date.replace(month=quarter_start_month, day=1)
        period_name = 'Quarterly'
    elif period == 'yearly':
        start_date = end_date.replace(month=1, day=1)
        period_name = 'Yearly'
    conn = get_db()
    if period == 'all':
        records_list = conn.execute('SELECT * FROM gbv_records ORDER BY created_at DESC').fetchall()
    else:
        records_list = conn.execute('''
            SELECT * FROM gbv_records
            WHERE created_at BETWEEN ? AND ?
            ORDER BY created_at DESC
        ''', (start_date, end_date)).fetchall()
    conn.close()
    return render_template('reports.html',
                           records=records_list,
                           period=period_name,
                           start_date=start_date.strftime('%Y-%m-%d') if start_date else '',
                           end_date=end_date.strftime('%Y-%m-%d'),
                           current_period=period)

@app.route('/dashboard')
@login_required
def dashboard():
    # Default: last 30 days
    start_date_str = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1) # inclusive
    except:
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now() + timedelta(days=1)
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = datetime.now().strftime('%Y-%m-%d')
    conn = get_db()
    cursor = conn.cursor()
    # === KPIs ===
    cursor.execute('SELECT COUNT(*) FROM gbv_records WHERE created_at BETWEEN ? AND ?', (start_date, end_date))
    total_cases = cursor.fetchone()[0] or 0
    cursor.execute('SELECT COUNT(*) FROM gbv_records WHERE sex = "F" AND created_at BETWEEN ? AND ?', (start_date, end_date))
    female_count = cursor.fetchone()[0] or 0
    female_pct = round((female_count / total_cases * 100) if total_cases > 0 else 0, 1)
    cursor.execute('SELECT COUNT(*) FROM gbv_records WHERE age < 18 AND created_at BETWEEN ? AND ?', (start_date, end_date))
    minors_count = cursor.fetchone()[0] or 0
    minors_pct = round((minors_count / total_cases * 100) if total_cases > 0 else 0, 1)
    cursor.execute('SELECT COUNT(*) FROM gbv_records WHERE pep_given = "Y" AND created_at BETWEEN ? AND ?', (start_date, end_date))
    pep_count = cursor.fetchone()[0] or 0
    pep_pct = round((pep_count / total_cases * 100) if total_cases > 0 else 0, 1)
    cursor.execute('SELECT COUNT(*) FROM gbv_records WHERE referral_initial IN ("1","2","3","4","5","6") AND created_at BETWEEN ? AND ?', (start_date, end_date))
    referred_count = cursor.fetchone()[0] or 0
    referred_pct = round((referred_count / total_cases * 100) if total_cases > 0 else 0, 1)
    # === Charts Data ===
    # 1. Cases over time (monthly)
    cursor.execute('''
        SELECT strftime('%Y-%m', created_at) as month, COUNT(*)
        FROM gbv_records
        WHERE created_at BETWEEN ? AND ?
        GROUP BY month ORDER BY month
    ''', (start_date, end_date))
    time_data = cursor.fetchall()
    time_labels = [row[0] for row in time_data]
    time_values = [row[1] for row in time_data]
    # 2. Type of Violence
    cursor.execute('''
        SELECT type_violence, COUNT(*)
        FROM gbv_records
        WHERE created_at BETWEEN ? AND ?
        GROUP BY type_violence
    ''', (start_date, end_date))
    violence_data = cursor.fetchall()
    violence_labels = [row[0] or 'Unknown' for row in violence_data]
    violence_values = [row[1] for row in violence_data]
    # 3. Age Groups
    cursor.execute('''
        SELECT
            CASE
                WHEN age < 10 THEN '0-9'
                WHEN age BETWEEN 10 AND 17 THEN '10-17'
                WHEN age BETWEEN 18 AND 24 THEN '18-24'
                WHEN age BETWEEN 25 AND 49 THEN '25-49'
                ELSE '50+'
            END as age_group,
            COUNT(*)
        FROM gbv_records
        WHERE created_at BETWEEN ? AND ?
        GROUP BY age_group
    ''', (start_date, end_date))
    age_data = cursor.fetchall()
    age_labels = [row[0] for row in age_data]
    age_values = [row[1] for row in age_data]
    conn.close()
    chart_data = {
        'time': {'labels': time_labels, 'values': time_values},
        'violence': {'labels': violence_labels, 'values': violence_values},
        'age': {'labels': age_labels, 'values': age_values}
    }
    return render_template('dashboard.html',
                           total_cases=total_cases,
                           female_pct=female_pct,
                           minors_pct=minors_pct,
                           pep_pct=pep_pct,
                           referred_pct=referred_pct,
                           chart_data=json.dumps(chart_data),
                           start_date=start_date_str,
                           end_date=end_date_str)

@app.route('/export/csv')
@login_required
def export_csv():
    period = request.args.get('period', 'all')
    # Reusing the same logic as reports to get the correct records
    end_date = datetime.now()
    start_date = None
    if period != 'all':
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
    conn = get_db()
    if period == 'all':
        df = pd.read_sql_query('SELECT * FROM gbv_records ORDER BY created_at DESC', conn)
    else:
        df = pd.read_sql_query('''
            SELECT * FROM gbv_records
            WHERE created_at BETWEEN ? AND ?
            ORDER BY created_at DESC
        ''', conn, params=(start_date, end_date))
    conn.close()
    output = BytesIO()
    df.to_csv(output, index=False, encoding='utf-8')
    output.seek(0)
    filename = f"gbv_report_{period}_{datetime.now().strftime('%Y%m%d')}.csv"
    return send_file(output, mimetype='text/csv', as_attachment=True, download_name=filename)

@app.route('/export/excel')
@login_required
def export_excel():
    period = request.args.get('period', 'all')
    end_date = datetime.now()
    start_date = None
    if period != 'all':
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
    conn = get_db()
    if period == 'all':
        df = pd.read_sql_query('SELECT * FROM gbv_records ORDER BY created_at DESC', conn)
    else:
        df = pd.read_sql_query('''
            SELECT * FROM gbv_records
            WHERE created_at BETWEEN ? AND ?
            ORDER BY created_at DESC
        ''', conn, params=(start_date, end_date))
    conn.close()
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='GBV Records')
    output.seek(0)
    filename = f"gbv_report_{period}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=filename)

@app.route('/print-report')
@login_required
def print_report():
    period = request.args.get('period', 'all')
    end_date = datetime.now()
    start_date = None
    period_name = 'All Time'
    if period == 'daily':
        start_date = end_date - timedelta(days=1)
        period_name = 'Daily'
    elif period == 'weekly':
        start_date = end_date - timedelta(weeks=1)
        period_name = 'Weekly'
    elif period == 'monthly':
        start_date = end_date.replace(day=1)
        period_name = 'Monthly'
    elif period == 'quarterly':
        quarter_start_month = ((end_date.month - 1) // 3 * 3) + 1
        start_date = end_date.replace(month=quarter_start_month, day=1)
        period_name = 'Quarterly'
    elif period == 'yearly':
        start_date = end_date.replace(month=1, day=1)
        period_name = 'Yearly'
    conn = get_db()
    if period == 'all':
        records_list = conn.execute('SELECT * FROM gbv_records ORDER BY created_at DESC').fetchall()
    else:
        records_list = conn.execute('''
            SELECT * FROM gbv_records
            WHERE created_at BETWEEN ? AND ?
            ORDER BY created_at DESC
        ''', (start_date, end_date)).fetchall()
    conn.close()
    # Formating dates in Python instead of Jinja
    printed_on = datetime.now().strftime('%d/%m/%Y %H:%M')
    start_date_str = start_date.strftime('%d/%m/%Y') if start_date else 'All Time'
    end_date_str = end_date.strftime('%d/%m/%Y')
    return render_template('print_report.html',
                           records=records_list,
                           period=period_name,
                           start_date=start_date_str,
                           end_date=end_date_str,
                           printed_on=printed_on)

if __name__ == '__main__':
    app.run(debug=True)
