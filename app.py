from flask import Flask, render_template, request, flash, redirect, url_for, send_file, session, jsonify
import sqlite3
from datetime import datetime, timedelta
import json
import pandas as pd
from io import BytesIO
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from dateutil.relativedelta import relativedelta

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY') or 'kayunga_gbv_hospital_2026_secure_key'
DB_NAME = 'gbv_kayunga_hospital.db'


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Patients - Changed patient_id to INTEGER for OPD numbers
    # Patients - Remove serial_no, make patient_id TEXT for flexibility
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT UNIQUE NOT NULL,  -- OPD NUMBER (20202, 23022, etc.)
        arrival_datetime TEXT NOT NULL,
        national_id TEXT,
        client_name TEXT NOT NULL,
        address TEXT,
        contact_no TEXT,
        next_of_kin TEXT,
        next_of_kin_contact TEXT,
        ovc TEXT,
        age INTEGER NOT NULL,
        sex TEXT NOT NULL,
        marital_status TEXT,
        incident_datetime TEXT,
        medical_form_filled TEXT,
        p3_form TEXT,
        disability TEXT,
        perpetrator_relation TEXT,
        type_violence TEXT NOT NULL,
        type_case TEXT,
        facility_name TEXT DEFAULT 'Kayunga Regional Referral Hospital',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
''')

    # Initial visits
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS initial_visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            visit_date TEXT,
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
            referral_facility TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients (patient_id)
        )
    ''')

    # Follow-ups
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS follow_ups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            followup_type TEXT CHECK(followup_type IN ('2weeks', '1month', '3months', '6months')),
            followup_date TEXT,
            actual_return_date TEXT,
            next_appointment TEXT,
            referral TEXT,
            trauma_counseling TEXT,
            adherence_counseling TEXT,
            pep_refill TEXT,
            hiv_test TEXT,
            pregnancy_test TEXT,
            hb_level REAL,
            alt_level INTEGER,
            hep_b_vaccine TEXT,
            tt_given TEXT,
            syphilis_test TEXT,
            referral_update TEXT,
            pep_completion TEXT,
            notes TEXT,
            staff_name TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients (patient_id),
            UNIQUE(patient_id, followup_type)
        )
    ''')

    # Outcomes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS client_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER UNIQUE,
            outcome TEXT,
            outcome_date TEXT,
            outcome_type TEXT CHECK(outcome_type IN ('completed', 'transferred', 'defaulted', 'died', 'other')),
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients (patient_id)
        )
    ''')

    # Users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            department TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Default admin
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        hashed = generate_password_hash('admin123')
        cursor.execute("INSERT INTO users (username, full_name, password, role) VALUES (?,?,?,?)",
                       ('admin', 'System Administrator', hashed, 'admin'))

    # Default nurse
    cursor.execute("SELECT * FROM users WHERE username = 'nurse'")
    if not cursor.fetchone():
        hashed = generate_password_hash('nurse123')
        cursor.execute("INSERT INTO users (username, full_name, password, role, department) VALUES (?,?,?,?,?)",
                       ('nurse', 'GBV Department Nurse', hashed, 'nurse', 'GBV Clinic'))

    conn.commit()
    conn.close()


init_db()


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def to_float(val, default=0.0):
    if val in (None, '', 'ND', 'NA', 'nd', 'na', 'Not Done', 'Not Applicable'):
        return default
    try:
        return float(val)
    except:
        return default


def to_int(val, default=0):
    if val in (None, '', 'ND', 'NA', 'nd', 'na', 'Not Done', 'Not Applicable'):
        return default
    try:
        return int(val)
    except:
        return default


# ─── Filters & Context ───────────────────────────────────────────────────────

@app.context_processor
def inject_now():
    return dict(now=datetime.now())


@app.template_filter('format_datetime')
def format_datetime(value, fmt='%Y-%m-%d %H:%M'):
    if not value:
        return ''
    try:
        # Try different date formats
        for date_fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d']:
            try:
                return datetime.strptime(value, date_fmt).strftime(fmt)
            except:
                continue
        return value
    except:
        return value


@app.template_filter('format_date')
def format_date(value):
    if not value:
        return ''
    try:
        return datetime.strptime(value, '%Y-%m-%d').strftime('%d/%m/%Y')
    except:
        return value


@app.template_filter('format_datetime_for_input')
def format_datetime_for_input(value):
    """Convert datetime to HTML input format (YYYY-MM-DDTHH:MM)"""
    if not value:
        return ''
    try:
        # Try different date formats
        for date_fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d']:
            try:
                dt = datetime.strptime(value, date_fmt)
                return dt.strftime('%Y-%m-%dT%H:%M')
            except:
                continue
        return value
    except:
        return value


# ─── Decorators ──────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('user_role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def download_required(f):
    """Only admin can download data"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('user_role') != 'admin':
            flash('Only administrators can download data.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


# ─── Public routes ───────────────────────────────────────────────────────────

@app.route('/')
@app.route('/home')
@app.route('/landing')
def landing():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Please enter username and password.', 'warning')
            return render_template('login.html')

        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session.update({
                'user_id': user['id'],
                'user_role': user['role'],
                'username': user['username'],
                'full_name': user['full_name']
            })
            flash(f'Welcome back, {user["full_name"]}!', 'success')
            return redirect(url_for('dashboard'))

        flash('Invalid username or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    name = session.pop('full_name', session.pop('username', 'User'))
    session.clear()
    flash(f'Goodbye, {name}. You have been logged out.', 'info')
    return redirect(url_for('landing'))


# ─── Protected routes ────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    with get_db() as conn:
        # Get counts
        cursor = conn.cursor()
        
        # Total patients
        cursor.execute('SELECT COUNT(*) FROM patients')
        total = cursor.fetchone()[0] or 0
        
        # Female patients
        cursor.execute('SELECT COUNT(*) FROM patients WHERE sex = "F"')
        females = cursor.fetchone()[0] or 0
        
        # Child patients (under 18)
        cursor.execute('SELECT COUNT(*) FROM patients WHERE age < 18')
        children = cursor.fetchone()[0] or 0
        
        # Today's patients
        today_date = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('SELECT COUNT(*) FROM patients WHERE DATE(arrival_datetime) = ?', (today_date,))
        today = cursor.fetchone()[0] or 0
        
        # Recent cases (last 7 days)
        week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        cursor.execute('SELECT COUNT(*) FROM patients WHERE DATE(arrival_datetime) >= ?', (week_ago,))
        recent_cases = cursor.fetchone()[0] or 0
        
        # PEP cases
        cursor.execute('''
            SELECT COUNT(DISTINCT p.patient_id) 
            FROM patients p 
            LEFT JOIN initial_visits iv ON p.patient_id = iv.patient_id
            WHERE iv.pep_given = "Y"
        ''')
        pep_cases = cursor.fetchone()[0] or 0
        
        # Cases by violence type
        cursor.execute('''
            SELECT type_violence, COUNT(*) as count 
            FROM patients 
            GROUP BY type_violence
        ''')
        violence_types = cursor.fetchall()
        
        # Monthly statistics for chart
        cursor.execute('''
            SELECT 
                strftime('%Y-%m', arrival_datetime) as month,
                COUNT(*) as count
            FROM patients
            WHERE arrival_datetime >= date('now', '-6 months')
            GROUP BY strftime('%Y-%m', arrival_datetime)
            ORDER BY month DESC
            LIMIT 6
        ''')
        monthly_data = cursor.fetchall()
        
        # Age distribution
        cursor.execute('''
            SELECT 
                CASE 
                    WHEN age < 18 THEN 'Children (<18)'
                    WHEN age BETWEEN 18 AND 35 THEN 'Youth (18-35)'
                    WHEN age BETWEEN 36 AND 50 THEN 'Adults (36-50)'
                    ELSE 'Older Adults (50+)'
                END as age_group,
                COUNT(*) as count
            FROM patients
            GROUP BY 
                CASE 
                    WHEN age < 18 THEN 'Children (<18)'
                    WHEN age BETWEEN 18 AND 35 THEN 'Youth (18-35)'
                    WHEN age BETWEEN 36 AND 50 THEN 'Adults (36-50)'
                    ELSE 'Older Adults (50+)'
                END
        ''')
        age_distribution = cursor.fetchall()
    
    return render_template('dashboard.html',
                           total_patients=total,
                           female_patients=females,
                           child_patients=children,
                           today_patients=today,
                           recent_cases=recent_cases,
                           pep_cases=pep_cases,
                           violence_types=violence_types,
                           monthly_data=monthly_data,
                           age_distribution=age_distribution)

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current = request.form.get('current_password')
        new_pw = request.form.get('new_password')
        confirm = request.form.get('confirm_password')

        if new_pw != confirm:
            flash('New passwords do not match.', 'danger')
            return redirect(url_for('change_password'))

        if len(new_pw) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return redirect(url_for('change_password'))

        with get_db() as conn:
            user = conn.execute('SELECT password FROM users WHERE id = ?', (session['user_id'],)).fetchone()
            if not check_password_hash(user['password'], current):
                flash('Current password is incorrect.', 'danger')
                return redirect(url_for('change_password'))

            hashed = generate_password_hash(new_pw)
            conn.execute('UPDATE users SET password = ? WHERE id = ?', (hashed, session['user_id']))
            conn.commit()

        flash('Password changed successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('change_password.html')


@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_users():
    conn = get_db()

    if request.method == 'POST':
        fields = ['username', 'full_name', 'password', 'role', 'department']
        data = {k: request.form.get(k, '').strip() for k in fields}
        if not all(data[k] for k in ['username', 'full_name', 'password']):
            flash('Please fill all required fields.', 'danger')
            return redirect(url_for('manage_users'))

        try:
            hashed = generate_password_hash(data['password'])
            conn.execute('''
                INSERT INTO users (username, full_name, password, role, department)
                VALUES (?, ?, ?, ?, ?)
            ''', (data['username'], data['full_name'], hashed, data['role'] or 'nurse', data['department'] or 'GBV Clinic'))
            conn.commit()
            flash(f'User {data["full_name"]} created.', 'success')
        except sqlite3.IntegrityError:
            flash(f'Username {data["username"]} already exists.', 'danger')
        return redirect(url_for('manage_users'))

    users = conn.execute('''
        SELECT id, username, full_name, role, department, created_at
        FROM users ORDER BY role, username
    ''').fetchall()
    conn.close()

    return render_template('manage_users.html', users=users)


@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == session['user_id']:
        flash("You can't delete your own account.", 'danger')
        return redirect(url_for('manage_users'))

    with get_db() as conn:
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()

    flash('User deleted.', 'success')
    return redirect(url_for('manage_users'))


# ──────────────────────────────────────────────────────────────────────────────
#   PATIENT REGISTRATION ───────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
@app.route('/register_patient', methods=['GET', 'POST'])
@login_required
def register_patient():
    if request.method == 'POST':
        # Get OPD number from form
        opd_number = request.form.get('patient_id', '').strip()
        
        if not opd_number:
            flash('Please enter OPD Number', 'danger')
            return redirect(url_for('register_patient'))
        
        fields = [
            'arrival_datetime', 'national_id', 'client_name', 'address',
            'contact_no', 'next_of_kin', 'next_of_kin_contact', 'ovc', 'age', 'sex',
            'marital_status', 'incident_datetime', 'medical_form_filled', 'p3_form',
            'disability', 'perpetrator_relation', 'type_violence', 'type_case'
        ]

        values = [request.form.get(f, '').strip() for f in fields]
        values.insert(0, opd_number)  # patient_id (OPD number) first

        with get_db() as conn:
            try:
                # Check if OPD number already exists
                existing = conn.execute('SELECT * FROM patients WHERE patient_id = ?', 
                                       (opd_number,)).fetchone()
                if existing:
                    flash(f'OPD Number {opd_number} already exists for patient: {existing["client_name"]}', 'danger')
                    return redirect(url_for('register_patient'))

                conn.execute('''
                    INSERT INTO patients (
                        patient_id, arrival_datetime, national_id, client_name,
                        address, contact_no, next_of_kin, next_of_kin_contact, ovc, age, sex,
                        marital_status, incident_datetime, medical_form_filled, p3_form,
                        disability, perpetrator_relation, type_violence, type_case, facility_name
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''', tuple(values + ['Kayunga Regional Referral Hospital']))

                # Optional initial visit
                if any(request.form.get(k) for k in ['pep_given', 'ecp_given', 'hiv_test_initial']):
                    iv_fields = [
                        'hiv_test_initial', 'pregnancy_test', 'anal_swab', 'hvs', 'spermatozoa',
                        'urinalysis', 'hep_b_initial', 'syphilis_initial', 'ecp_given', 'pep_given',
                        'sti_treatment', 'trauma_counseling_initial', 'adherence_counseling_initial',
                        'tt_given_initial', 'hep_b_vaccine_initial', 'syphilis_treatment',
                        'referral_initial', 'referral_facility', 'initial_notes'
                    ]
                    iv_values = [request.form.get(k) for k in iv_fields]
                    conn.execute('''
                        INSERT INTO initial_visits (
                            patient_id, visit_date, hiv_test_initial, pregnancy_test, anal_swab, hvs,
                            spermatozoa, urinalysis, hep_b_initial, syphilis_initial, ecp_given, pep_given,
                            sti_treatment, trauma_counseling_initial, adherence_counseling_initial,
                            tt_given_initial, hep_b_vaccine_initial, syphilis_treatment, referral_initial,
                            referral_facility, notes
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ''', (opd_number, request.form.get('arrival_datetime'), *iv_values))

                conn.commit()

                next_app = ''
                try:
                    arr = datetime.strptime(request.form.get('arrival_datetime'), '%Y-%m-%dT%H:%M')
                    next_app = (arr + timedelta(days=14)).strftime('%Y-%m-%d')
                except:
                    pass

                flash(f'''
                    <div class="alert alert-success">
                        <h4><i class="fas fa-check-circle"></i> Patient Registered Successfully!</h4>
                        <p><strong>OPD Number:</strong> <span class="badge bg-primary fs-5">{opd_number}</span></p>
                        <p><strong>Patient Name:</strong> {request.form.get('client_name')}</p>
                        <p><strong>Recommended Next Appointment:</strong> {next_app or '—'}</p>
                    </div>
                ''', 'success')

            except sqlite3.Error as e:
                flash(f'<div class="alert alert-danger"><i class="fas fa-exclamation-circle"></i> Database error: {e}</div>', 'danger')

        return redirect(url_for('register_patient'))

    now = datetime.now()
    return render_template('register_patient.html',
                           today=now.strftime('%Y-%m-%d'),
                           arrival_datetime=now.strftime('%Y-%m-%dT%H:%M'))





# ──────────────────────────────────────────────────────────────────────────────
#   PATIENT LOOKUP & MANAGEMENT ────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────

@app.route('/patient_lookup', methods=['GET', 'POST'])
@login_required
def patient_lookup():
    patient = None
    initial_visit = None
    follow_ups = []
    outcome = None
    available_types = []
    
    if request.method == 'POST':
        search_term = request.form.get('search_term', '').strip()
        search_by = request.form.get('search_by', 'patient_id')
        
        if not search_term:
            flash('Please enter a search term', 'warning')
            return render_template('patient_lookup.html')
        
        conn = get_db()
        
        try:
            query_map = {
                'patient_id': 'patient_id = ?',
                'national_id': 'national_id = ?',
                'serial_no': 'serial_no = ?',
                'name': 'client_name LIKE ?',
                'contact': 'contact_no LIKE ?'
            }
            
            if search_by not in query_map:
                flash('Invalid search type', 'danger')
                return redirect(url_for('patient_lookup'))
            
            query = f'SELECT * FROM patients WHERE {query_map[search_by]}'
            
            # For patient_id search, convert to integer if it's numeric
            if search_by == 'patient_id' and search_term.isdigit():
                params = [int(search_term)]
            elif search_by == 'name' or search_by == 'contact':
                params = [f'%{search_term}%']
            else:
                params = [search_term]
            
            patient = conn.execute(query, params).fetchone()
            
            if patient:
                initial_visit = conn.execute('SELECT * FROM initial_visits WHERE patient_id = ?', 
                                           (patient['patient_id'],)).fetchone()
                follow_ups = conn.execute('''
                    SELECT * FROM follow_ups 
                    WHERE patient_id = ? 
                    ORDER BY CASE followup_type
                        WHEN '2weeks' THEN 1
                        WHEN '1month' THEN 2
                        WHEN '3months' THEN 3
                        WHEN '6months' THEN 4
                        ELSE 5
                    END
                ''', (patient['patient_id'],)).fetchall()
                outcome = conn.execute('SELECT * FROM client_outcomes WHERE patient_id = ?', 
                                     (patient['patient_id'],)).fetchone()
                
                # Calculate available follow-up types
                all_types = ['2weeks', '1month', '3months', '6months']
                existing_types = [fu['followup_type'] for fu in follow_ups]
                available_types = [t for t in all_types if t not in existing_types]
                
            else:
                flash(f'No patient found with {search_by}: {search_term}', 'warning')
                
        except Exception as e:
            flash(f'Search error: {str(e)}', 'danger')
        finally:
            conn.close()
    
    return render_template('patient_lookup.html',
                         patient=patient,
                         initial_visit=initial_visit,
                         follow_ups=follow_ups,
                         outcome=outcome,
                         available_types=available_types)


@app.route('/add_followup/<int:patient_id>', methods=['GET', 'POST'])
@login_required
def add_followup(patient_id):
    conn = get_db()
    patient = conn.execute('SELECT * FROM patients WHERE patient_id = ?', (patient_id,)).fetchone()
    
    if not patient:
        flash('Patient not found', 'danger')
        conn.close()
        return redirect(url_for('patient_lookup'))
    
    # Get existing follow-ups
    existing_followups = conn.execute('SELECT followup_type FROM follow_ups WHERE patient_id = ?', 
                                    (patient_id,)).fetchall()
    existing_types = [fu['followup_type'] for fu in existing_followups]
    
    # Calculate next follow-up type
    all_types = ['2weeks', '1month', '3months', '6months']
    available_types = [t for t in all_types if t not in existing_types]
    
    if not available_types:
        flash('All follow-ups have been completed for this patient', 'warning')
        conn.close()
        return redirect(url_for('patient_lookup', search_term=patient_id, search_by='patient_id'))
    
    # Get last follow-up date to suggest next date
    last_followup = conn.execute('''
        SELECT MAX(followup_date) as last_date FROM follow_ups 
        WHERE patient_id = ?
    ''', (patient_id,)).fetchone()
    
    # Calculate suggested date
    suggested_date = datetime.now().strftime('%Y-%m-%d')
    if available_types:
        next_type = available_types[0]
        try:
            arrival_date = datetime.strptime(patient['arrival_datetime'], '%Y-%m-%d %H:%M:%S')
            if next_type == '2weeks':
                suggested_date = (arrival_date + timedelta(days=14)).strftime('%Y-%m-%d')
            elif next_type == '1month':
                suggested_date = (arrival_date + relativedelta(months=1)).strftime('%Y-%m-%d')
            elif next_type == '3months':
                suggested_date = (arrival_date + relativedelta(months=3)).strftime('%Y-%m-%d')
            elif next_type == '6months':
                suggested_date = (arrival_date + relativedelta(months=6)).strftime('%Y-%m-%d')
        except:
            pass
    
    if request.method == 'POST':
        followup_type = request.form.get('followup_type')
        
        if not followup_type:
            flash('Please select follow-up type', 'warning')
            conn.close()
            return render_template('add_followup.html',
                                 patient=patient,
                                 available_types=available_types,
                                 existing_types=existing_types,
                                 suggested_date=suggested_date)
        
        if followup_type in existing_types:
            flash(f'{followup_type} follow-up already exists', 'warning')
            conn.close()
            return redirect(url_for('patient_lookup', search_term=patient_id, search_by='patient_id'))
        
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO follow_ups 
                (patient_id, followup_type, followup_date, actual_return_date, next_appointment,
                 referral, trauma_counseling, adherence_counseling, pep_refill, hiv_test,
                 pregnancy_test, hb_level, alt_level, hep_b_vaccine, tt_given, syphilis_test,
                 referral_update, pep_completion, notes, staff_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                patient_id,
                followup_type,
                request.form.get('followup_date'),
                request.form.get('actual_return_date'),
                request.form.get('next_appointment'),
                request.form.get('referral'),
                request.form.get('trauma_counseling'),
                request.form.get('adherence_counseling'),
                request.form.get('pep_refill'),
                request.form.get('hiv_test'),
                request.form.get('pregnancy_test'),
                to_float(request.form.get('hb_level')),
                to_int(request.form.get('alt_level')),
                request.form.get('hep_b_vaccine'),
                request.form.get('tt_given'),
                request.form.get('syphilis_test'),
                request.form.get('referral_update'),
                request.form.get('pep_completion'),
                request.form.get('notes'),
                session.get('full_name', 'Unknown Staff')
            ))
            
            conn.commit()
            
            # Get follow-up name for display
            followup_names = {
                '2weeks': '2 Weeks',
                '1month': '1 Month', 
                '3months': '3 Months',
                '6months': '6 Months'
            }
            
            flash(f'''
                <div class="alert alert-success">
                    <i class="fas fa-calendar-check"></i> {followup_names.get(followup_type, followup_type)} 
                    Follow-up added successfully for {patient["client_name"]}!
                </div>
            ''', 'success')
            
        except sqlite3.Error as e:
            conn.rollback()
            flash(f'<div class="alert alert-danger"><i class="fas fa-exclamation-circle"></i> Error: {str(e)}</div>', 'danger')
        finally:
            conn.close()
        
        return redirect(url_for('patient_lookup', search_term=patient_id, search_by='patient_id'))
    
    conn.close()
    
    return render_template('add_followup.html',
                         patient=patient,
                         available_types=available_types,
                         existing_types=existing_types,
                         suggested_date=suggested_date,
                         today=datetime.now().strftime('%Y-%m-%d'))


@app.route('/edit_followup/<int:followup_id>', methods=['GET', 'POST'])
@login_required
def edit_followup(followup_id):
    conn = get_db()
    followup = conn.execute('SELECT * FROM follow_ups WHERE id = ?', (followup_id,)).fetchone()
    
    if not followup:
        flash('Follow-up not found', 'danger')
        conn.close()
        return redirect(url_for('patient_lookup'))
    
    patient = conn.execute('SELECT * FROM patients WHERE patient_id = ?', 
                         (followup['patient_id'],)).fetchone()
    
    if request.method == 'POST':
        try:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE follow_ups SET
                    followup_date = ?,
                    actual_return_date = ?,
                    next_appointment = ?,
                    referral = ?,
                    trauma_counseling = ?,
                    adherence_counseling = ?,
                    pep_refill = ?,
                    hiv_test = ?,
                    pregnancy_test = ?,
                    hb_level = ?,
                    alt_level = ?,
                    hep_b_vaccine = ?,
                    tt_given = ?,
                    syphilis_test = ?,
                    referral_update = ?,
                    pep_completion = ?,
                    notes = ?,
                    staff_name = ?
                WHERE id = ?
            ''', (
                request.form.get('followup_date'),
                request.form.get('actual_return_date'),
                request.form.get('next_appointment'),
                request.form.get('referral'),
                request.form.get('trauma_counseling'),
                request.form.get('adherence_counseling'),
                request.form.get('pep_refill'),
                request.form.get('hiv_test'),
                request.form.get('pregnancy_test'),
                to_float(request.form.get('hb_level')),
                to_int(request.form.get('alt_level')),
                request.form.get('hep_b_vaccine'),
                request.form.get('tt_given'),
                request.form.get('syphilis_test'),
                request.form.get('referral_update'),
                request.form.get('pep_completion'),
                request.form.get('notes'),
                session.get('full_name', 'Unknown Staff'),
                followup_id
            ))
            
            conn.commit()
            flash('<div class="alert alert-success"><i class="fas fa-check-circle"></i> Follow-up updated successfully!</div>', 'success')
            
        except sqlite3.Error as e:
            conn.rollback()
            flash(f'<div class="alert alert-danger"><i class="fas fa-exclamation-circle"></i> Error: {str(e)}</div>', 'danger')
        finally:
            conn.close()
        
        return redirect(url_for('patient_lookup', search_term=patient['patient_id'], search_by='patient_id'))
    
    conn.close()
    
    return render_template('edit_followup.html', followup=followup, patient=patient)


@app.route('/edit_initial_visit/<int:patient_id>', methods=['GET', 'POST'])
@login_required
def edit_initial_visit(patient_id):
    conn = get_db()
    patient = conn.execute('SELECT * FROM patients WHERE patient_id = ?', (patient_id,)).fetchone()
    
    if not patient:
        flash('Patient not found', 'danger')
        conn.close()
        return redirect(url_for('patient_lookup'))
    
    initial_visit = conn.execute('SELECT * FROM initial_visits WHERE patient_id = ?', 
                               (patient_id,)).fetchone()
    
    if request.method == 'POST':
        try:
            cursor = conn.cursor()
            
            if initial_visit:
                cursor.execute('''
                    UPDATE initial_visits SET
                        visit_date = ?,
                        hiv_test_initial = ?,
                        pregnancy_test = ?,
                        anal_swab = ?,
                        hvs = ?,
                        spermatozoa = ?,
                        urinalysis = ?,
                        hep_b_initial = ?,
                        syphilis_initial = ?,
                        ecp_given = ?,
                        pep_given = ?,
                        sti_treatment = ?,
                        trauma_counseling_initial = ?,
                        adherence_counseling_initial = ?,
                        tt_given_initial = ?,
                        hep_b_vaccine_initial = ?,
                        syphilis_treatment = ?,
                        referral_initial = ?,
                        referral_facility = ?,
                        notes = ?
                    WHERE patient_id = ?
                ''', (
                    request.form.get('visit_date'),
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
                    request.form.get('referral_facility'),
                    request.form.get('notes'),
                    patient_id
                ))
            else:
                cursor.execute('''
                    INSERT INTO initial_visits 
                    (patient_id, visit_date, hiv_test_initial, pregnancy_test, anal_swab, hvs, 
                     spermatozoa, urinalysis, hep_b_initial, syphilis_initial, ecp_given, pep_given, 
                     sti_treatment, trauma_counseling_initial, adherence_counseling_initial, 
                     tt_given_initial, hep_b_vaccine_initial, syphilis_treatment, referral_initial,
                     referral_facility, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    patient_id,
                    request.form.get('visit_date'),
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
                    request.form.get('referral_facility'),
                    request.form.get('notes')
                ))
            
            conn.commit()
            flash('<div class="alert alert-success"><i class="fas fa-check-circle"></i> Initial visit updated successfully!</div>', 'success')
            
        except sqlite3.Error as e:
            conn.rollback()
            flash(f'<div class="alert alert-danger"><i class="fas fa-exclamation-circle"></i> Error: {str(e)}</div>', 'danger')
        finally:
            conn.close()
        
        return redirect(url_for('patient_lookup', search_term=patient_id, search_by='patient_id'))
    
    conn.close()
    
    return render_template('edit_initial_visit.html', 
                         patient=patient, 
                         initial_visit=initial_visit,
                         today=datetime.now().strftime('%Y-%m-%d'))


@app.route('/edit_patient/<int:patient_id>', methods=['GET', 'POST'])
@login_required
def edit_patient(patient_id):
    conn = get_db()
    patient = conn.execute('SELECT * FROM patients WHERE patient_id = ?', (patient_id,)).fetchone()
    
    if not patient:
        flash('Patient not found', 'danger')
        conn.close()
        return redirect(url_for('patient_lookup'))
    
    if request.method == 'POST':
        try:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE patients SET
                    serial_no = ?,
                    arrival_datetime = ?,
                    national_id = ?,
                    client_name = ?,
                    address = ?,
                    contact_no = ?,
                    next_of_kin = ?,
                    next_of_kin_contact = ?,
                    ovc = ?,
                    age = ?,
                    sex = ?,
                    marital_status = ?,
                    incident_datetime = ?,
                    medical_form_filled = ?,
                    p3_form = ?,
                    disability = ?,
                    perpetrator_relation = ?,
                    type_violence = ?,
                    type_case = ?,
                    facility_name = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE patient_id = ?
            ''', (
                request.form.get('serial_no'),
                request.form.get('arrival_datetime'),
                request.form.get('national_id'),
                request.form.get('client_name'),
                request.form.get('address'),
                request.form.get('contact_no'),
                request.form.get('next_of_kin'),
                request.form.get('next_of_kin_contact'),
                request.form.get('ovc'),
                to_int(request.form.get('age')),
                request.form.get('sex'),
                request.form.get('marital_status'),
                request.form.get('incident_datetime'),
                request.form.get('medical_form_filled'),
                request.form.get('p3_form'),
                request.form.get('disability'),
                request.form.get('perpetrator_relation'),
                request.form.get('type_violence'),
                request.form.get('type_case'),
                request.form.get('facility_name', 'Kayunga Regional Referral Hospital'),
                patient_id
            ))
            
            conn.commit()
            flash('<div class="alert alert-success"><i class="fas fa-check-circle"></i> Patient information updated successfully!</div>', 'success')
            
        except sqlite3.Error as e:
            conn.rollback()
            flash(f'<div class="alert alert-danger"><i class="fas fa-exclamation-circle"></i> Error: {str(e)}</div>', 'danger')
        finally:
            conn.close()
        
        return redirect(url_for('patient_lookup', search_term=patient_id, search_by='patient_id'))
    
    conn.close()
    
    return render_template('edit_patient.html', patient=patient)


@app.route('/add_outcome/<int:patient_id>', methods=['GET', 'POST'])
@login_required
def add_outcome(patient_id):
    conn = get_db()
    patient = conn.execute('SELECT * FROM patients WHERE patient_id = ?', (patient_id,)).fetchone()
    
    if not patient:
        flash('Patient not found', 'danger')
        conn.close()
        return redirect(url_for('patient_lookup'))
    
    existing_outcome = conn.execute('SELECT * FROM client_outcomes WHERE patient_id = ?', 
                                  (patient_id,)).fetchone()
    
    if request.method == 'POST':
        try:
            cursor = conn.cursor()
            
            if existing_outcome:
                cursor.execute('''
                    UPDATE client_outcomes 
                    SET outcome = ?, outcome_date = ?, outcome_type = ?, notes = ?
                    WHERE patient_id = ?
                ''', (
                    request.form.get('outcome'),
                    request.form.get('outcome_date'),
                    request.form.get('outcome_type'),
                    request.form.get('notes'),
                    patient_id
                ))
            else:
                cursor.execute('''
                    INSERT INTO client_outcomes (patient_id, outcome, outcome_date, outcome_type, notes)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    patient_id,
                    request.form.get('outcome'),
                    request.form.get('outcome_date'),
                    request.form.get('outcome_type'),
                    request.form.get('notes')
                ))
            
            conn.commit()
            flash('<div class="alert alert-success"><i class="fas fa-check-circle"></i> Outcome recorded successfully!</div>', 'success')
            
        except sqlite3.Error as e:
            conn.rollback()
            flash(f'<div class="alert alert-danger"><i class="fas fa-exclamation-circle"></i> Error: {str(e)}</div>', 'danger')
        finally:
            conn.close()
        
        return redirect(url_for('patient_lookup', search_term=patient_id, search_by='patient_id'))
    
    conn.close()
    
    return render_template('add_outcome.html', 
                         patient=patient, 
                         existing_outcome=existing_outcome,
                         today=datetime.now().strftime('%Y-%m-%d'))


@app.route('/delete_followup/<int:followup_id>', methods=['POST'])
@login_required
def delete_followup(followup_id):
    conn = get_db()
    
    try:
        # Get patient ID before deleting
        followup = conn.execute('SELECT patient_id FROM follow_ups WHERE id = ?', (followup_id,)).fetchone()
        
        if not followup:
            flash('Follow-up not found', 'danger')
            conn.close()
            return redirect(url_for('patient_lookup'))
        
        patient_id = followup['patient_id']
        
        # Delete the follow-up
        conn.execute('DELETE FROM follow_ups WHERE id = ?', (followup_id,))
        conn.commit()
        
        flash('<div class="alert alert-success"><i class="fas fa-check-circle"></i> Follow-up deleted successfully!</div>', 'success')
        
    except sqlite3.Error as e:
        conn.rollback()
        flash(f'<div class="alert alert-danger"><i class="fas fa-exclamation-circle"></i> Error: {str(e)}</div>', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('patient_lookup', search_term=patient_id, search_by='patient_id'))


# ──────────────────────────────────────────────────────────────────────────────
#   RECORDS & REPORTS ──────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────

@app.route('/all_records')
@login_required
def all_records():
    search = request.args.get('search', '').strip()
    sex = request.args.get('sex', '')
    violence = request.args.get('violence', '')
    age_group = request.args.get('age_group', '')
    followup_filter = request.args.get('followup', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    show_completed = request.args.get('show_completed', 'false') == 'true'
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Build query - FIXED: Using arrival_datetime
    query = '''
        SELECT p.*, 
               iv.hiv_test_initial, iv.pep_given,
               (SELECT COUNT(*) FROM follow_ups f WHERE f.patient_id = p.patient_id) as followup_count,
               co.outcome, co.outcome_date,
               CASE 
                   WHEN co.outcome IS NOT NULL THEN 'Completed'
                   WHEN (SELECT COUNT(*) FROM follow_ups f WHERE f.patient_id = p.patient_id) >= 4 THEN 'All Follow-ups Done'
                   ELSE 'In Progress'
               END as status
        FROM patients p
        LEFT JOIN initial_visits iv ON p.patient_id = iv.patient_id
        LEFT JOIN client_outcomes co ON p.patient_id = co.patient_id
        WHERE 1=1
    '''
    
    params = []
    
    if search:
        query += ' AND (p.client_name LIKE ? OR p.patient_id LIKE ? OR p.national_id LIKE ?)'
        like_term = f'%{search}%'
        params.extend([like_term, like_term, like_term])
    
    if sex:
        query += ' AND p.sex = ?'
        params.append(sex)
    
    if violence:
        query += ' AND p.type_violence = ?'
        params.append(violence)
    
    if age_group == 'child':
        query += ' AND p.age < 18'
    elif age_group == 'adult':
        query += ' AND p.age >= 18'
    
    if followup_filter:
        if followup_filter == 'none':
            query += ' AND (SELECT COUNT(*) FROM follow_ups f WHERE f.patient_id = p.patient_id) = 0'
        elif followup_filter == 'partial':
            query += ' AND (SELECT COUNT(*) FROM follow_ups f WHERE f.patient_id = p.patient_id) BETWEEN 1 AND 3'
        elif followup_filter == 'complete':
            query += ' AND (SELECT COUNT(*) FROM follow_ups f WHERE f.patient_id = p.patient_id) >= 4'
    
    if start_date:
        query += ' AND DATE(p.arrival_datetime) >= ?'
        params.append(start_date)
    
    if end_date:
        query += ' AND DATE(p.arrival_datetime) <= ?'
        params.append(end_date)
    
    if not show_completed:
        query += ' AND co.outcome IS NULL'
    
    query += ' ORDER BY p.arrival_datetime DESC'
    
    cursor.execute(query, params)
    records = cursor.fetchall()
    
    cursor.execute('SELECT COUNT(*) FROM patients')
    total_count = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT COUNT(*) FROM patients WHERE sex = "F"')
    female_count = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT COUNT(*) FROM patients WHERE age < 18')
    child_count = cursor.fetchone()[0] or 0
    
    cursor.execute('''
        SELECT COUNT(DISTINCT p.patient_id) 
        FROM patients p 
        LEFT JOIN initial_visits iv ON p.patient_id = iv.patient_id 
        WHERE iv.pep_given = "Y"
    ''')
    pep_count = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return render_template('all_records.html',
                         records=records,
                         total_count=total_count,
                         female_count=female_count,
                         child_count=child_count,
                         pep_count=pep_count,
                         search=search,
                         sex=sex,
                         violence=violence,
                         age_group=age_group,
                         followup_filter=followup_filter,
                         start_date=start_date,
                         end_date=end_date,
                         show_completed=show_completed)

@app.route('/reports')
@login_required
def reports():
    period = request.args.get('period', 'all')
    search = request.args.get('search', '').strip()
    sex = request.args.get('sex', '')
    violence = request.args.get('violence', '')
    age_group = request.args.get('age_group', '')
    followup_filter = request.args.get('followup', '')
    custom_start = request.args.get('start_date', '')
    custom_end = request.args.get('end_date', '')
    
    end_date = datetime.now()
    start_date = None
    period_name = 'All Time'
    
    if period != 'all':
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
    cursor = conn.cursor()
    
    # Build query - FIXED: Using arrival_datetime instead of created_at
    query = '''
        SELECT p.*, iv.pep_given, iv.hiv_test_initial,
               (SELECT COUNT(*) FROM follow_ups f WHERE f.patient_id = p.patient_id) as followup_count,
               co.outcome
        FROM patients p
        LEFT JOIN initial_visits iv ON p.patient_id = iv.patient_id
        LEFT JOIN client_outcomes co ON p.patient_id = co.patient_id
        WHERE 1=1
    '''
    count_query = 'SELECT COUNT(*) FROM patients p WHERE 1=1'
    params = []
    
    if period != 'all' and start_date:
        query += ' AND DATE(p.arrival_datetime) BETWEEN ? AND ?'
        count_query += ' AND DATE(p.arrival_datetime) BETWEEN ? AND ?'
        params.extend([start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')])
    elif custom_start or custom_end:
        if custom_start:
            query += ' AND DATE(p.arrival_datetime) >= ?'
            count_query += ' AND DATE(p.arrival_datetime) >= ?'
            params.append(custom_start)
        if custom_end:
            query += ' AND DATE(p.arrival_datetime) <= ?'
            count_query += ' AND DATE(p.arrival_datetime) <= ?'
            params.append(custom_end)
    
    if search:
        like = f'%{search}%'
        query += ' AND (p.patient_id LIKE ? OR p.national_id LIKE ? OR p.client_name LIKE ?)'
        count_query += ' AND (p.patient_id LIKE ? OR p.national_id LIKE ? OR p.client_name LIKE ?)'
        params.extend([like, like, like])
    
    if sex:
        query += ' AND p.sex = ?'
        count_query += ' AND p.sex = ?'
        params.append(sex)
    
    if violence:
        query += ' AND p.type_violence = ?'
        count_query += ' AND p.type_violence = ?'
        params.append(violence)
    
    if age_group == 'child':
        query += ' AND p.age < 18'
        count_query += ' AND p.age < 18'
    elif age_group == 'adult':
        query += ' AND p.age >= 18'
        count_query += ' AND p.age >= 18'
    
    if followup_filter:
        if followup_filter == 'none':
            query += ' AND (SELECT COUNT(*) FROM follow_ups f WHERE f.patient_id = p.patient_id) = 0'
        elif followup_filter == 'partial':
            query += ' AND (SELECT COUNT(*) FROM follow_ups f WHERE f.patient_id = p.patient_id) BETWEEN 1 AND 3'
        elif followup_filter == 'complete':
            query += ' AND (SELECT COUNT(*) FROM follow_ups f WHERE f.patient_id = p.patient_id) >= 4'
        elif followup_filter == '2weeks':
            query += ' AND EXISTS (SELECT 1 FROM follow_ups f WHERE f.patient_id = p.patient_id AND f.followup_type = "2weeks")'
        elif followup_filter == '1month':
            query += ' AND EXISTS (SELECT 1 FROM follow_ups f WHERE f.patient_id = p.patient_id AND f.followup_type = "1month")'
        elif followup_filter == '3months':
            query += ' AND EXISTS (SELECT 1 FROM follow_ups f WHERE f.patient_id = p.patient_id AND f.followup_type = "3months")'
        elif followup_filter == '6months':
            query += ' AND EXISTS (SELECT 1 FROM follow_ups f WHERE f.patient_id = p.patient_id AND f.followup_type = "6months")'
    
    query += ' ORDER BY p.arrival_datetime DESC'
    
    # Execute main query
    cursor.execute(query, params)
    records = cursor.fetchall()
    
    # Execute count query
    cursor.execute(count_query, params)
    total_cases = cursor.fetchone()[0] or 0
    
    # Female count
    female_query = count_query.replace('WHERE 1=1', 'WHERE 1=1 AND p.sex = "F"')
    cursor.execute(female_query, params)
    female_cases = cursor.fetchone()[0] or 0
    
    # Child count
    child_query = count_query.replace('WHERE 1=1', 'WHERE 1=1 AND p.age < 18')
    cursor.execute(child_query, params)
    child_cases = cursor.fetchone()[0] or 0
    
    # PEP count - FIXED: Use proper date filtering
    pep_query = '''
        SELECT COUNT(DISTINCT p.patient_id) 
        FROM patients p 
        LEFT JOIN initial_visits iv ON p.patient_id = iv.patient_id
        WHERE 1=1 AND iv.pep_given = "Y"
    '''
    pep_params = []
    
    if period != 'all' and start_date:
        pep_query += ' AND DATE(p.arrival_datetime) BETWEEN ? AND ?'
        pep_params.extend([start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')])
    elif custom_start or custom_end:
        if custom_start:
            pep_query += ' AND DATE(p.arrival_datetime) >= ?'
            pep_params.append(custom_start)
        if custom_end:
            pep_query += ' AND DATE(p.arrival_datetime) <= ?'
            pep_params.append(custom_end)
    
    if search:
        like = f'%{search}%'
        pep_query += ' AND (p.patient_id LIKE ? OR p.national_id LIKE ? OR p.client_name LIKE ?)'
        pep_params.extend([like, like, like])
    
    if sex:
        pep_query += ' AND p.sex = ?'
        pep_params.append(sex)
    
    if violence:
        pep_query += ' AND p.type_violence = ?'
        pep_params.append(violence)
    
    if age_group == 'child':
        pep_query += ' AND p.age < 18'
    elif age_group == 'adult':
        pep_query += ' AND p.age >= 18'
    
    cursor.execute(pep_query, pep_params)
    pep_cases = cursor.fetchone()[0] or 0
    
    # Get additional statistics for charts
    # Monthly breakdown for chart
    monthly_query = '''
        SELECT strftime('%Y-%m', p.arrival_datetime) as month, COUNT(*) as count
        FROM patients p
        WHERE 1=1
    '''
    monthly_params = []
    
    if period != 'all' and start_date:
        monthly_query += ' AND DATE(p.arrival_datetime) BETWEEN ? AND ?'
        monthly_params.extend([start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')])
    elif custom_start or custom_end:
        if custom_start:
            monthly_query += ' AND DATE(p.arrival_datetime) >= ?'
            monthly_params.append(custom_start)
        if custom_end:
            monthly_query += ' AND DATE(p.arrival_datetime) <= ?'
            monthly_params.append(custom_end)
    
    monthly_query += ' GROUP BY strftime("%Y-%m", p.arrival_datetime) ORDER BY month'
    cursor.execute(monthly_query, monthly_params)
    monthly_data = cursor.fetchall()
    
    # Violence type breakdown
    violence_query = '''
        SELECT p.type_violence, COUNT(*) as count
        FROM patients p
        WHERE 1=1
    '''
    violence_params = []
    
    if period != 'all' and start_date:
        violence_query += ' AND DATE(p.arrival_datetime) BETWEEN ? AND ?'
        violence_params.extend([start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')])
    elif custom_start or custom_end:
        if custom_start:
            violence_query += ' AND DATE(p.arrival_datetime) >= ?'
            violence_params.append(custom_start)
        if custom_end:
            violence_query += ' AND DATE(p.arrival_datetime) <= ?'
            violence_params.append(custom_end)
    
    if sex:
        violence_query += ' AND p.sex = ?'
        violence_params.append(sex)
    
    if age_group == 'child':
        violence_query += ' AND p.age < 18'
    elif age_group == 'adult':
        violence_query += ' AND p.age >= 18'
    
    violence_query += ' GROUP BY p.type_violence ORDER BY count DESC'
    cursor.execute(violence_query, violence_params)
    violence_data = cursor.fetchall()
    
    # Age distribution
    age_query = '''
        SELECT 
            CASE 
                WHEN p.age < 18 THEN 'Children (<18)'
                WHEN p.age BETWEEN 18 AND 35 THEN 'Youth (18-35)'
                WHEN p.age BETWEEN 36 AND 50 THEN 'Adults (36-50)'
                ELSE 'Older Adults (50+)'
            END as age_group,
            COUNT(*) as count
        FROM patients p
        WHERE 1=1
    '''
    age_params = []
    
    if period != 'all' and start_date:
        age_query += ' AND DATE(p.arrival_datetime) BETWEEN ? AND ?'
        age_params.extend([start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')])
    elif custom_start or custom_end:
        if custom_start:
            age_query += ' AND DATE(p.arrival_datetime) >= ?'
            age_params.append(custom_start)
        if custom_end:
            age_query += ' AND DATE(p.arrival_datetime) <= ?'
            age_params.append(custom_end)
    
    if sex:
        age_query += ' AND p.sex = ?'
        age_params.append(sex)
    
    if violence:
        age_query += ' AND p.type_violence = ?'
        age_params.append(violence)
    
    age_query += '''
        GROUP BY 
            CASE 
                WHEN p.age < 18 THEN 'Children (<18)'
                WHEN p.age BETWEEN 18 AND 35 THEN 'Youth (18-35)'
                WHEN p.age BETWEEN 36 AND 50 THEN 'Adults (36-50)'
                ELSE 'Older Adults (50+)'
            END
    '''
    cursor.execute(age_query, age_params)
    age_distribution = cursor.fetchall()
    
    # Follow-up completion status
    followup_query = '''
        SELECT 
            CASE 
                WHEN co.outcome IS NOT NULL THEN 'Completed'
                WHEN (SELECT COUNT(*) FROM follow_ups f WHERE f.patient_id = p.patient_id) >= 4 THEN 'All Follow-ups Done'
                WHEN (SELECT COUNT(*) FROM follow_ups f WHERE f.patient_id = p.patient_id) > 0 THEN 'In Progress'
                ELSE 'Not Started'
            END as status,
            COUNT(*) as count
        FROM patients p
        LEFT JOIN client_outcomes co ON p.patient_id = co.patient_id
        WHERE 1=1
    '''
    followup_params = []
    
    if period != 'all' and start_date:
        followup_query += ' AND DATE(p.arrival_datetime) BETWEEN ? AND ?'
        followup_params.extend([start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')])
    elif custom_start or custom_end:
        if custom_start:
            followup_query += ' AND DATE(p.arrival_datetime) >= ?'
            followup_params.append(custom_start)
        if custom_end:
            followup_query += ' AND DATE(p.arrival_datetime) <= ?'
            followup_params.append(custom_end)
    
    if sex:
        followup_query += ' AND p.sex = ?'
        followup_params.append(sex)
    
    if violence:
        followup_query += ' AND p.type_violence = ?'
        followup_params.append(violence)
    
    if age_group == 'child':
        followup_query += ' AND p.age < 18'
    elif age_group == 'adult':
        followup_query += ' AND p.age >= 18'
    
    followup_query += ' GROUP BY status'
    cursor.execute(followup_query, followup_params)
    followup_status = cursor.fetchall()
    
    conn.close()
    
    return render_template('reports.html',
                           records=records,
                           total_cases=total_cases,
                           female_cases=female_cases,
                           female_pct=round(female_cases/total_cases*100, 1) if total_cases else 0,
                           child_cases=child_cases,
                           child_pct=round(child_cases/total_cases*100, 1) if total_cases else 0,
                           pep_cases=pep_cases,
                           pep_pct=round(pep_cases/total_cases*100, 1) if total_cases else 0,
                           period=period_name,
                           start_date=start_date.strftime('%Y-%m-%d') if start_date else '',
                           end_date=end_date.strftime('%Y-%m-%d') if end_date else '',
                           current_period=period,
                           search=search,
                           sex=sex,
                           violence=violence,
                           age_group=age_group,
                           followup_filter=followup_filter,
                           custom_start=custom_start,
                           custom_end=custom_end,
                           monthly_data=monthly_data,
                           violence_data=violence_data,
                           age_distribution=age_distribution,
                           followup_status=followup_status)


# ──────────────────────────────────────────────────────────────────────────────
#   EXPORT FUNCTIONALITY (ADMIN ONLY) ──────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────

@app.route('/export_csv')
@login_required
@download_required
def export_csv():
    period = request.args.get('period', 'all')
    search = request.args.get('search', '').strip()
    sex = request.args.get('sex', '')
    violence = request.args.get('violence', '')
    age_group = request.args.get('age_group', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    
    end_dt = datetime.now()
    start_dt = None
    
    if period != 'all':
        if period == 'daily':
            start_dt = end_dt - timedelta(days=1)
        elif period == 'weekly':
            start_dt = end_dt - timedelta(weeks=1)
        elif period == 'monthly':
            start_dt = end_dt.replace(day=1)
        elif period == 'quarterly':
            q_month = ((end_dt.month - 1) // 3 * 3) + 1
            start_dt = end_dt.replace(month=q_month, day=1)
        elif period == 'yearly':
            start_dt = end_dt.replace(month=1, day=1)
    
    conn = get_db()
    
    query = '''
        SELECT p.*, 
               iv.hiv_test_initial, iv.pregnancy_test, iv.pep_given, iv.ecp_given,
               (SELECT COUNT(*) FROM follow_ups f WHERE f.patient_id = p.patient_id) as followup_count,
               co.outcome, co.outcome_date
        FROM patients p
        LEFT JOIN initial_visits iv ON p.patient_id = iv.patient_id
        LEFT JOIN client_outcomes co ON p.patient_id = co.patient_id
        WHERE 1=1
    '''
    params = []
    
    if period != 'all' and start_dt:
        query += ' AND p.created_at BETWEEN ? AND ?'
        params.extend([start_dt, end_dt])
    elif start_date or end_date:
        if start_date:
            query += ' AND p.created_at >= ?'
            params.append(f'{start_date} 00:00:00')
        if end_date:
            query += ' AND p.created_at <= ?'
            params.append(f'{end_date} 23:59:59')
    
    if search:
        like = f'%{search}%'
        query += ' AND (p.serial_no LIKE ? OR p.national_id LIKE ? OR p.client_name LIKE ?)'
        params.extend([like, like, like])
    
    if sex:
        query += ' AND p.sex = ?'
        params.append(sex)
    
    if violence:
        query += ' AND p.type_violence = ?'
        params.append(violence)
    
    if age_group == 'child':
        query += ' AND p.age < 18'
    elif age_group == 'adult':
        query += ' AND p.age >= 18'
    
    query += ' ORDER BY p.created_at DESC'
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    # Rename columns
    column_map = {
        'patient_id': 'OPD Number',
        'serial_no': 'Serial No',
        'arrival_datetime': 'Arrival Date',
        'national_id': 'National ID',
        'client_name': 'Client Name',
        'age': 'Age',
        'sex': 'Sex',
        'type_violence': 'Violence Type',
        'pep_given': 'PEP Given',
        'hiv_test_initial': 'Initial HIV Test',
        'followup_count': 'Follow-up Count',
        'outcome': 'Outcome',
        'created_at': 'Registration Date'
    }
    df.rename(columns=column_map, inplace=True)
    
    # Select only important columns
    important_cols = ['OPD Number', 'Serial No', 'Client Name', 'Age', 'Sex', 'Violence Type', 
                     'Arrival Date', 'PEP Given', 'Initial HIV Test', 'Follow-up Count', 
                     'Outcome', 'Registration Date']
    df = df[[col for col in important_cols if col in df.columns]]
    
    output = BytesIO()
    df.to_csv(output, index=False, encoding='utf-8-sig')
    output.seek(0)
    
    filename = f"gbv_kayunga_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )


@app.route('/export_patient/<patient_id>')
@login_required
def export_patient(patient_id):
    conn = get_db()
    
    try:
        # Get patient data
        patient = conn.execute('SELECT * FROM patients WHERE patient_id = ?', (patient_id,)).fetchone()
        if not patient:
            flash('Patient not found', 'danger')
            return redirect(url_for('patient_lookup'))
        
        initial_visit = conn.execute('SELECT * FROM initial_visits WHERE patient_id = ?', 
                                   (patient_id,)).fetchone()
        follow_ups = conn.execute('SELECT * FROM follow_ups WHERE patient_id = ? ORDER BY followup_date', 
                                (patient_id,)).fetchall()
        outcome = conn.execute('SELECT * FROM client_outcomes WHERE patient_id = ?', 
                             (patient_id,)).fetchone()
        
        # Create HTML report
        html_content = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>GBV Patient Report - OPD {patient_id}: {patient.get('client_name', 'N/A')}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .header {{ text-align: center; margin-bottom: 30px; border-bottom: 2px solid #333; padding-bottom: 10px; }}
                .section {{ margin-bottom: 25px; page-break-inside: avoid; }}
                .section-title {{ background-color: #f5f5f5; padding: 8px 15px; font-weight: bold; border-left: 4px solid #007bff; margin-bottom: 15px; }}
                table {{ width: 100%; border-collapse: collapse; margin-bottom: 15px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f8f9fa; }}
                .footer {{ margin-top: 40px; text-align: center; font-size: 12px; color: #666; border-top: 1px solid #ddd; padding-top: 10px; }}
                .opd-badge {{ background-color: #007bff; color: white; padding: 5px 10px; border-radius: 4px; font-weight: bold; display: inline-block; margin: 5px 0; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Kayunga Regional Referral Hospital</h1>
                <h2>Gender-Based Violence Patient Report</h2>
                <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <div class="opd-badge">OPD NUMBER: {patient_id}</div>
            </div>
            
            <div class="section">
                <div class="section-title">Patient Information</div>
                <table>
                    <tr><th>OPD Number:</th><td>{patient_id}</td></tr>
                    <tr><th>Name:</th><td>{patient.get('client_name', 'N/A')}</td></tr>
                    <tr><th>Age/Sex:</th><td>{patient.get('age', 'N/A')} / {patient.get('sex', 'N/A')}</td></tr>
                    <tr><th>Arrival Date:</th><td>{patient.get('arrival_datetime', 'N/A')}</td></tr>
                    <tr><th>Contact:</th><td>{patient.get('contact_no', 'N/A')}</td></tr>
                    <tr><th>Violence Type:</th><td>{patient.get('type_violence', 'N/A')}</td></tr>
                </table>
            </div>
        '''
        
        if initial_visit:
            html_content += f'''
            <div class="section">
                <div class="section-title">Initial Visit</div>
                <table>
                    <tr><th>HIV Test:</th><td>{initial_visit.get('hiv_test_initial', 'N/A')}</td></tr>
                    <tr><th>PEP Given:</th><td>{initial_visit.get('pep_given', 'N/A')}</td></tr>
                    <tr><th>Trauma Counseling:</th><td>{initial_visit.get('trauma_counseling_initial', 'N/A')}</td></tr>
                </table>
            </div>
            '''
        
        if follow_ups:
            html_content += '''
            <div class="section">
                <div class="section-title">Follow-ups</div>
                <table>
                    <tr>
                        <th>Type</th><th>Date</th><th>HIV Test</th><th>PEP Refill</th><th>Counseling</th>
                    </tr>
            '''
            for fu in follow_ups:
                html_content += f'''
                    <tr>
                        <td>{fu.get('followup_type', 'N/A').replace('2weeks', '2 Weeks').replace('1month', '1 Month').replace('3months', '3 Months').replace('6months', '6 Months')}</td>
                        <td>{fu.get('followup_date', 'N/A')}</td>
                        <td>{fu.get('hiv_test', 'N/A')}</td>
                        <td>{fu.get('pep_refill', 'N/A')}</td>
                        <td>{fu.get('trauma_counseling', 'N/A')}</td>
                    </tr>
                '''
            html_content += '</table></div>'
        
        if outcome:
            html_content += f'''
            <div class="section">
                <div class="section-title">Client Outcome</div>
                <table>
                    <tr><th>Outcome:</th><td>{outcome.get('outcome', 'N/A')}</td></tr>
                    <tr><th>Date:</th><td>{outcome.get('outcome_date', 'N/A')}</td></tr>
                    <tr><th>Notes:</th><td>{outcome.get('notes', 'N/A')}</td></tr>
                </table>
            </div>
            '''
        
        html_content += f'''
            <div class="footer">
                <p>Confidential Medical Record - For authorized personnel only</p>
                <p>Kayunga Regional Referral Hospital - GBV Department</p>
            </div>
        </body>
        </html>
        '''
        
        output = BytesIO()
        output.write(html_content.encode('utf-8'))
        output.seek(0)
        
        safe_name = patient.get('client_name', 'patient').replace(' ', '_').replace('/', '_')
        filename = f"gbv_opd_{patient_id}_{safe_name}_{datetime.now().strftime('%Y%m%d')}.html"
        
        return send_file(
            output,
            mimetype='text/html',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        print(f"Export error: {str(e)}")
        flash(f'Error exporting patient data: {str(e)}', 'danger')
        # FIXED: Redirect to view_patient endpoint which you created
        return redirect(url_for('view_patient', patient_id=patient_id))

@app.route('/patient/<patient_id>')
@login_required
def view_patient(patient_id):
    conn = get_db()
    
    patient = conn.execute('SELECT * FROM patients WHERE patient_id = ?', (patient_id,)).fetchone()
    if not patient:
        flash('Patient not found', 'danger')
        return redirect(url_for('patient_lookup'))
    
    initial_visit = conn.execute('SELECT * FROM initial_visits WHERE patient_id = ?', 
                               (patient_id,)).fetchone()
    follow_ups = conn.execute('SELECT * FROM follow_ups WHERE patient_id = ? ORDER BY followup_date', 
                            (patient_id,)).fetchall()
    outcome = conn.execute('SELECT * FROM client_outcomes WHERE patient_id = ?', 
                         (patient_id,)).fetchone()
    
    # Calculate available follow-up types
    all_types = ['2weeks', '1month', '3months', '6months']
    existing_types = [fu['followup_type'] for fu in follow_ups]
    available_types = [t for t in all_types if t not in existing_types]
    
    conn.close()
    
    return render_template('view_patient.html',
                         patient=patient,
                         initial_visit=initial_visit,
                         follow_ups=follow_ups,
                         outcome=outcome,
                         available_types=available_types)

@app.route('/delete_patient/<int:patient_id>', methods=['POST'])
@login_required
@admin_required
def delete_patient(patient_id):
    conn = get_db()
    
    try:
        # Check if patient exists
        patient = conn.execute('SELECT * FROM patients WHERE patient_id = ?', (patient_id,)).fetchone()
        
        if not patient:
            flash('Patient not found', 'danger')
            conn.close()
            return redirect(url_for('patient_lookup'))
        
        # Delete patient and related records
        conn.execute('DELETE FROM client_outcomes WHERE patient_id = ?', (patient_id,))
        conn.execute('DELETE FROM follow_ups WHERE patient_id = ?', (patient_id,))
        conn.execute('DELETE FROM initial_visits WHERE patient_id = ?', (patient_id,))
        conn.execute('DELETE FROM patients WHERE patient_id = ?', (patient_id,))
        
        conn.commit()
        
        flash(f'<div class="alert alert-success"><i class="fas fa-check-circle"></i> Patient OPD {patient_id} deleted successfully!</div>', 'success')
        
    except sqlite3.Error as e:
        conn.rollback()
        flash(f'<div class="alert alert-danger"><i class="fas fa-exclamation-circle"></i> Error deleting patient: {str(e)}</div>', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('patient_lookup'))


# ─── Dashboard Statistics API ────────────────────────────────────────────────

@app.route('/api/dashboard_stats')
@login_required
def dashboard_stats():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get counts
        cursor.execute('SELECT COUNT(*) FROM patients')
        total_patients = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COUNT(*) FROM patients WHERE sex = "F"')
        female_patients = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COUNT(*) FROM patients WHERE age < 18')
        child_patients = cursor.fetchone()[0] or 0
        
        # Today's patients
        today_date = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('SELECT COUNT(*) FROM patients WHERE DATE(arrival_datetime) = ?', (today_date,))
        today_patients = cursor.fetchone()[0] or 0
        
        # Weekly trend
        cursor.execute('''
            SELECT 
                DATE(arrival_datetime) as date,
                COUNT(*) as count
            FROM patients
            WHERE arrival_datetime >= date('now', '-7 days')
            GROUP BY DATE(arrival_datetime)
            ORDER BY date
        ''')
        weekly_data = cursor.fetchall()
        
        # Monthly data for chart
        cursor.execute('''
            SELECT 
                strftime('%Y-%m', arrival_datetime) as month,
                COUNT(*) as count
            FROM patients
            WHERE arrival_datetime >= date('now', '-6 months')
            GROUP BY strftime('%Y-%m', arrival_datetime)
            ORDER BY month
        ''')
        monthly_data = cursor.fetchall()
        
        # Violence type breakdown
        cursor.execute('''
            SELECT type_violence, COUNT(*) as count
            FROM patients
            GROUP BY type_violence
            ORDER BY count DESC
        ''')
        violence_data = cursor.fetchall()
        
        # Age distribution
        cursor.execute('''
            SELECT 
                CASE 
                    WHEN age < 18 THEN 'Children (<18)'
                    WHEN age BETWEEN 18 AND 35 THEN 'Youth (18-35)'
                    WHEN age BETWEEN 36 AND 50 THEN 'Adults (36-50)'
                    ELSE 'Older Adults (50+)'
                END as age_group,
                COUNT(*) as count
            FROM patients
            GROUP BY 
                CASE 
                    WHEN age < 18 THEN 'Children (<18)'
                    WHEN age BETWEEN 18 AND 35 THEN 'Youth (18-35)'
                    WHEN age BETWEEN 36 AND 50 THEN 'Adults (36-50)'
                    ELSE 'Older Adults (50+)'
                END
        ''')
        age_data = cursor.fetchall()
        
        # PEP statistics
        cursor.execute('''
            SELECT 
                CASE 
                    WHEN iv.pep_given = 'Y' THEN 'PEP Given'
                    WHEN iv.pep_given = 'N' THEN 'No PEP'
                    ELSE 'Not Recorded'
                END as pep_status,
                COUNT(*) as count
            FROM patients p
            LEFT JOIN initial_visits iv ON p.patient_id = iv.patient_id
            GROUP BY iv.pep_given
        ''')
        pep_data = cursor.fetchall()
    
    return jsonify({
        'total': total_patients,
        'female': female_patients,
        'child': child_patients,
        'today': today_patients,
        'weekly_trend': [{'date': row[0], 'count': row[1]} for row in weekly_data],
        'monthly': [{'month': row[0], 'count': row[1]} for row in monthly_data],
        'violence_types': [{'type': row[0], 'count': row[1]} for row in violence_data],
        'age_distribution': [{'group': row[0], 'count': row[1]} for row in age_data],
        'pep_stats': [{'status': row[0], 'count': row[1]} for row in pep_data]
    })


# ─── Error handlers ──────────────────────────────────────────────────────────

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)