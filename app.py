from flask import Flask, render_template, request, flash, redirect, url_for, send_file, session, jsonify, g
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

# Database connection functions
def get_db():
    """Get database connection"""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_NAME)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    """Close database connection"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

# Database helper function
def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

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

def init_db():
    """Initialize the database with tables"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT,
            email TEXT,
            role TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            last_login TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Patients table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT UNIQUE NOT NULL,
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

    # Initial visits table
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

    # Follow-ups table
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

    # Client outcomes table
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

    conn.commit()

    # Create default admin user
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        hashed = generate_password_hash('admin123')
        cursor.execute("""
            INSERT INTO users (username, full_name, password, role, is_active) 
            VALUES (?, ?, ?, ?, ?)
        """, ('admin', 'System Administrator', hashed, 'super_admin', 1))
        print("Default admin user created: admin / admin123")

    # Create default medical personnel user
    cursor.execute("SELECT * FROM users WHERE username = 'nurse'")
    if not cursor.fetchone():
        hashed = generate_password_hash('nurse123')
        cursor.execute("""
            INSERT INTO users (username, full_name, password, role, is_active) 
            VALUES (?, ?, ?, ?, ?)
        """, ('nurse', 'GBV Department Nurse', hashed, 'medical_personnel', 1))
        print("Default nurse user created: nurse / nurse123")

    conn.commit()
    conn.close()

# Initialize database
init_db()

# Template filters
@app.template_filter('format_date')
def format_date(value):
    if value and len(value) >= 10:
        return value[:10]
    return value

@app.template_filter('format_datetime')
def format_datetime(value, format='%Y-%m-%d %H:%M'):
    if value:
        return value[:16]
    return value

@app.template_filter('format_datetime_for_input')
def format_datetime_for_input(value):
    """Convert datetime to HTML input format (YYYY-MM-DDTHH:MM)"""
    if not value:
        return ''
    try:
        for date_fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d']:
            try:
                dt = datetime.strptime(value, date_fmt)
                return dt.strftime('%Y-%m-%dT%H:%M')
            except:
                continue
        return value
    except:
        return value

@app.context_processor
def inject_now():
    return dict(now=datetime.now())

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
        if session.get('user_role') != 'super_admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def download_required(f):
    """Only super_admin can download data"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('user_role') != 'super_admin':
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
        username = request.form['username']
        password = request.form['password']
        
        user = query_db('SELECT * FROM users WHERE username = ? AND is_active = 1', [username], one=True)
        
        if user:
            if check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['user_role'] = user['role']
                session['logged_in'] = True
                
                # Update last login
                db = get_db()
                db.execute('UPDATE users SET last_login = datetime("now") WHERE id = ?', [user['id']])
                db.commit()
                
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
        
        flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('landing'))

# ─── User Management Routes ─────────────────────────────────────────────────

@app.route('/manage_users')
@login_required
def manage_users():
    """Manage users page"""
    if session.get('user_role') != 'super_admin':
        flash('You do not have permission to access user management', 'error')
        return redirect(url_for('dashboard'))
    
    # Get all users
    users = query_db('''
        SELECT id, username, full_name, email, role, is_active, last_login, created_at
        FROM users 
        ORDER BY created_at DESC
    ''')
    
    return render_template('manage_users.html', users=users)

@app.route('/add_user', methods=['POST'])
@login_required
def add_user():
    """Add a new user"""
    if session.get('user_role') != 'super_admin':
        flash('You do not have permission to add users', 'error')
        return redirect(url_for('manage_users'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        role = request.form.get('role')
        is_active = 1 if request.form.get('is_active') else 0
        
        # Validate input
        if not username or not password or not role:
            flash('Username, password, and role are required', 'error')
            return redirect(url_for('manage_users'))
        
        # Check if username already exists
        existing = query_db('SELECT id FROM users WHERE username = ?', [username], one=True)
        if existing:
            flash('Username already exists', 'error')
            return redirect(url_for('manage_users'))
        
        # Hash password
        hashed_password = generate_password_hash(password)
        
        # Insert user
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO users (username, password, full_name, email, role, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        ''', (username, hashed_password, full_name, email, role, is_active))
        db.commit()
        
        flash(f'User {username} created successfully', 'success')
    
    return redirect(url_for('manage_users'))

@app.route('/edit_user', methods=['POST'])
@login_required
def edit_user():
    """Edit an existing user"""
    if session.get('user_role') != 'super_admin':
        flash('You do not have permission to edit users', 'error')
        return redirect(url_for('manage_users'))
    
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        role = request.form.get('role')
        is_active = 1 if request.form.get('is_active') else 0
        password = request.form.get('password')
        
        if not user_id or not role:
            flash('User ID and role are required', 'error')
            return redirect(url_for('manage_users'))
        
        db = get_db()
        cursor = db.cursor()
        
        # Update user info
        if password and len(password) >= 6:
            # Update with new password
            hashed_password = generate_password_hash(password)
            cursor.execute('''
                UPDATE users 
                SET full_name = ?, email = ?, role = ?, is_active = ?, password = ?
                WHERE id = ?
            ''', (full_name, email, role, is_active, hashed_password, user_id))
        else:
            # Update without password
            cursor.execute('''
                UPDATE users 
                SET full_name = ?, email = ?, role = ?, is_active = ?
                WHERE id = ?
            ''', (full_name, email, role, is_active, user_id))
        
        db.commit()
        
        flash('User updated successfully', 'success')
    
    return redirect(url_for('manage_users'))

@app.route('/delete_user', methods=['POST'])
@login_required
def delete_user():
    """Delete a user"""
    if session.get('user_role') != 'super_admin':
        flash('You do not have permission to delete users', 'error')
        return redirect(url_for('manage_users'))
    
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        
        # Don't allow deleting yourself
        if int(user_id) == session.get('user_id'):
            flash('You cannot delete your own account', 'error')
            return redirect(url_for('manage_users'))
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute('DELETE FROM users WHERE id = ?', [user_id])
        db.commit()
        
        flash('User deleted successfully', 'success')
    
    return redirect(url_for('manage_users'))

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

        user = query_db('SELECT password FROM users WHERE id = ?', [session['user_id']], one=True)
        if not check_password_hash(user['password'], current):
            flash('Current password is incorrect.', 'danger')
            return redirect(url_for('change_password'))

        hashed = generate_password_hash(new_pw)
        db = get_db()
        db.execute('UPDATE users SET password = ? WHERE id = ?', (hashed, session['user_id']))
        db.commit()

        flash('Password changed successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('change_password.html')

# ─── Dashboard ───────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Total patients
        cursor.execute('SELECT COUNT(*) FROM patients')
        total = cursor.fetchone()[0] or 0
        
        # Female patients (handle both 'F' and 'Female')
        cursor.execute('SELECT COUNT(*) FROM patients WHERE sex IN ("F", "Female")')
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
        
        # PEP cases - Check for 'Yes', 'Y', 'yes' etc.
        cursor.execute('''
            SELECT COUNT(DISTINCT p.patient_id) 
            FROM patients p 
            LEFT JOIN initial_visits iv ON p.patient_id = iv.patient_id
            WHERE UPPER(iv.pep_given) IN ('YES', 'Y')
        ''')
        pep_cases = cursor.fetchone()[0] or 0
        
        # Counseling counts
        cursor.execute('''
            SELECT 
                COUNT(DISTINCT CASE WHEN UPPER(iv.trauma_counseling_initial) IN ('YES', 'Y') THEN p.patient_id END) as initial_counseling,
                COUNT(DISTINCT fu.patient_id) as followup_counseling
            FROM patients p
            LEFT JOIN initial_visits iv ON p.patient_id = iv.patient_id
            LEFT JOIN follow_ups fu ON p.patient_id = fu.patient_id AND UPPER(fu.trauma_counseling) IN ('YES', 'Y')
        ''')
        counseling_row = cursor.fetchone()
        initial_counseling = counseling_row['initial_counseling'] or 0
        followup_counseling = counseling_row['followup_counseling'] or 0
        counseling_count = initial_counseling + followup_counseling
        
        # Cases by violence type - Return as list of dictionaries
        cursor.execute('''
            SELECT 
                COALESCE(type_violence, 'Not Specified') as type, 
                COUNT(*) as count 
            FROM patients 
            GROUP BY COALESCE(type_violence, 'Not Specified')
            ORDER BY count DESC
        ''')
        violence_rows = cursor.fetchall()
        violence_types = []
        for row in violence_rows:
            violence_types.append({
                'type': row['type'],
                'count': row['count']
            })
        
        # Monthly statistics for chart - Return as list of dictionaries
        cursor.execute('''
            SELECT 
                strftime('%Y-%m', arrival_datetime) as month,
                COUNT(*) as count
            FROM patients
            WHERE arrival_datetime IS NOT NULL
            GROUP BY strftime('%Y-%m', arrival_datetime)
            ORDER BY month DESC
            LIMIT 6
        ''')
        monthly_rows = cursor.fetchall()
        monthly_data = []
        for row in monthly_rows:
            monthly_data.append({
                'month': row['month'],
                'count': row['count']
            })
        
        # Age distribution - Return as list of dictionaries
        cursor.execute('''
            SELECT 
                CASE 
                    WHEN age < 18 THEN 'Children (<18)'
                    WHEN age BETWEEN 18 AND 35 THEN 'Youth (18-35)'
                    WHEN age BETWEEN 36 AND 50 THEN 'Adults (36-50)'
                    WHEN age > 50 THEN 'Older Adults (50+)'
                    ELSE 'Unknown'
                END as age_group,
                COUNT(*) as count
            FROM patients
            WHERE age IS NOT NULL
            GROUP BY age_group
            ORDER BY 
                CASE age_group
                    WHEN 'Children (<18)' THEN 1
                    WHEN 'Youth (18-35)' THEN 2
                    WHEN 'Adults (36-50)' THEN 3
                    WHEN 'Older Adults (50+)' THEN 4
                    ELSE 5
                END
        ''')
        age_rows = cursor.fetchall()
        age_distribution = []
        for row in age_rows:
            age_distribution.append({
                'group': row['age_group'],
                'count': row['count']
            })
        
        # Today's followups
        cursor.execute('''
            SELECT COUNT(*) FROM follow_ups 
            WHERE DATE(followup_date) = ?
        ''', (today_date,))
        today_followups = cursor.fetchone()[0] or 0
        
        # Pending followups
        cursor.execute('''
            SELECT COUNT(*) FROM follow_ups 
            WHERE next_appointment IS NOT NULL 
            AND DATE(next_appointment) >= ?
            AND DATE(next_appointment) <= DATE(?, '+7 days')
        ''', (today_date, today_date))
        pending_followups = cursor.fetchone()[0] or 0
    
    # Calculate percentages
    female_pct = round((females / total * 100), 1) if total > 0 else 0
    child_pct = round((children / total * 100), 1) if total > 0 else 0
    
    return render_template('dashboard.html',
                           total_patients=total,
                           female_patients=females,
                           female_pct=female_pct,
                           child_patients=children,
                           child_pct=child_pct,
                           today_patients=today,
                           recent_cases=recent_cases,
                           pep_cases=pep_cases,
                           counseling_count=counseling_count,
                           initial_counseling=initial_counseling,
                           followup_counseling=followup_counseling,
                           violence_types=violence_types,
                           monthly_data=monthly_data,
                           age_distribution=age_distribution,
                           today_followups=today_followups,
                           pending_followups=pending_followups)

# ─── Patient Registration ────────────────────────────────────────────────────

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

# ─── Patient Lookup & Management ────────────────────────────────────────────

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
                'name': 'client_name LIKE ?',
                'contact': 'contact_no LIKE ?'
            }
            
            if search_by not in query_map:
                flash('Invalid search type', 'danger')
                return redirect(url_for('patient_lookup'))
            
            query = f'SELECT * FROM patients WHERE {query_map[search_by]}'
            
            # For patient_id search, use as is (it's TEXT now)
            if search_by == 'name' or search_by == 'contact':
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

@app.route('/add_followup/<patient_id>', methods=['GET', 'POST'])
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
                session.get('username', 'Unknown Staff')
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
                session.get('username', 'Unknown Staff'),
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

@app.route('/edit_initial_visit/<patient_id>', methods=['GET', 'POST'])
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

@app.route('/edit_patient/<patient_id>', methods=['GET', 'POST'])
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

@app.route('/add_outcome/<patient_id>', methods=['GET', 'POST'])
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

@app.route('/delete_patient/<patient_id>', methods=['POST'])
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

# ─── Records & Reports ──────────────────────────────────────────────────────

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
    
    # Get unique violence types for filter dropdown
    cursor.execute('SELECT DISTINCT type_violence FROM patients WHERE type_violence IS NOT NULL ORDER BY type_violence')
    violence_rows = cursor.fetchall()
    violence_types = []
    for row in violence_rows:
        violence_types.append({
            'type': row['type_violence']
        })
    
    # Build query
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
    records_rows = cursor.fetchall()
    
    # Convert records to dictionaries for JSON serialization
    records = []
    for row in records_rows:
        record_dict = {}
        for key in row.keys():
            record_dict[key] = row[key]
        records.append(record_dict)
    
    # Get counts for stats
    cursor.execute('SELECT COUNT(*) FROM patients')
    total_count = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT COUNT(*) FROM patients WHERE sex IN ("F", "Female")')
    female_count = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT COUNT(*) FROM patients WHERE age < 18')
    child_count = cursor.fetchone()[0] or 0
    
    cursor.execute('''
        SELECT COUNT(DISTINCT p.patient_id) 
        FROM patients p 
        LEFT JOIN initial_visits iv ON p.patient_id = iv.patient_id 
        WHERE UPPER(iv.pep_given) IN ("YES", "Y")
    ''')
    pep_count = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return render_template('all_records.html',
                         records=records,
                         total_count=total_count,
                         female_count=female_count,
                         child_count=child_count,
                         pep_count=pep_count,
                         violence_types=violence_types,
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
    
    # Base query for records
    query = '''
        SELECT p.*, 
               iv.pep_given, iv.hiv_test_initial,
               (SELECT COUNT(*) FROM follow_ups f WHERE f.patient_id = p.patient_id) as followup_count,
               co.outcome
        FROM patients p
        LEFT JOIN initial_visits iv ON p.patient_id = iv.patient_id
        LEFT JOIN client_outcomes co ON p.patient_id = co.patient_id
        WHERE 1=1
    '''
    params = []
    
    # Date filtering
    if period != 'all' and start_date:
        query += ' AND DATE(p.arrival_datetime) BETWEEN ? AND ?'
        params.extend([start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')])
    elif custom_start or custom_end:
        if custom_start:
            query += ' AND DATE(p.arrival_datetime) >= ?'
            params.append(custom_start)
        if custom_end:
            query += ' AND DATE(p.arrival_datetime) <= ?'
            params.append(custom_end)
    
    # Search filter
    if search:
        like = f'%{search}%'
        query += ' AND (p.patient_id LIKE ? OR p.national_id LIKE ? OR p.client_name LIKE ?)'
        params.extend([like, like, like])
    
    # Sex filter
    if sex:
        query += ' AND p.sex = ?'
        params.append(sex)
    
    # Violence type filter
    if violence:
        query += ' AND p.type_violence = ?'
        params.append(violence)
    
    # Age group filter
    if age_group == 'child':
        query += ' AND p.age < 18'
    elif age_group == 'adult':
        query += ' AND p.age >= 18'
    
    # Follow-up filter
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
    
    # Get records
    cursor.execute(query, params)
    records_rows = cursor.fetchall()
    
    # Convert records to dictionaries for template
    records = []
    for row in records_rows:
        record_dict = {}
        for key in row.keys():
            record_dict[key] = row[key]
        records.append(record_dict)
    
    # Get total cases count
    total_cases = len(records)
    
    # Calculate female cases from records
    female_cases = 0
    for record in records:
        if record.get('sex') in ['F', 'Female']:
            female_cases += 1
    
    # Calculate child cases from records
    child_cases = 0
    for record in records:
        age = record.get('age', 0)
        if age and int(age) < 18:
            child_cases += 1
    
    # Calculate PEP cases from records
    pep_cases = 0
    for record in records:
        pep = record.get('pep_given', '')
        if pep and str(pep).upper() in ['YES', 'Y']:
            pep_cases += 1
    
    # Calculate percentages
    female_pct = round((female_cases / total_cases * 100), 1) if total_cases > 0 else 0
    child_pct = round((child_cases / total_cases * 100), 1) if total_cases > 0 else 0
    pep_pct = round((pep_cases / total_cases * 100), 1) if total_cases > 0 else 0
    
    # Get monthly trend data
    monthly_query = '''
        SELECT 
            strftime('%Y-%m', p.arrival_datetime) as month,
            COUNT(*) as count
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
    
    if search:
        like = f'%{search}%'
        monthly_query += ' AND (p.patient_id LIKE ? OR p.national_id LIKE ? OR p.client_name LIKE ?)'
        monthly_params.extend([like, like, like])
    
    if sex:
        monthly_query += ' AND p.sex = ?'
        monthly_params.append(sex)
    
    if violence:
        monthly_query += ' AND p.type_violence = ?'
        monthly_params.append(violence)
    
    if age_group == 'child':
        monthly_query += ' AND p.age < 18'
    elif age_group == 'adult':
        monthly_query += ' AND p.age >= 18'
    
    monthly_query += ' GROUP BY strftime("%Y-%m", p.arrival_datetime) ORDER BY month'
    
    cursor.execute(monthly_query, monthly_params)
    monthly_rows = cursor.fetchall()
    monthly_data = []
    for row in monthly_rows:
        monthly_data.append({
            'month': row['month'],
            'count': row['count']
        })
    
    # Get violence type data from records
    violence_counts = {}
    for record in records:
        v_type = record.get('type_violence', 'Not Specified')
        if not v_type:
            v_type = 'Not Specified'
        violence_counts[v_type] = violence_counts.get(v_type, 0) + 1
    
    violence_data = []
    for v_type, count in violence_counts.items():
        violence_data.append({
            'type': v_type,
            'count': count
        })
    
    # Get age distribution from records
    age_counts = {
        'Children (<18)': 0,
        'Youth (18-35)': 0,
        'Adults (36-50)': 0,
        'Older Adults (50+)': 0,
        'Unknown': 0
    }
    
    for record in records:
        age = record.get('age')
        if age:
            try:
                age_val = int(age)
                if age_val < 18:
                    age_counts['Children (<18)'] += 1
                elif 18 <= age_val <= 35:
                    age_counts['Youth (18-35)'] += 1
                elif 36 <= age_val <= 50:
                    age_counts['Adults (36-50)'] += 1
                elif age_val > 50:
                    age_counts['Older Adults (50+)'] += 1
                else:
                    age_counts['Unknown'] += 1
            except:
                age_counts['Unknown'] += 1
        else:
            age_counts['Unknown'] += 1
    
    age_distribution = []
    for group, count in age_counts.items():
        if count > 0:
            age_distribution.append({
                'group': group,
                'count': count
            })
    
    # Get gender distribution from records
    gender_counts = {}
    for record in records:
        gender = record.get('sex', 'Unknown')
        if not gender:
            gender = 'Unknown'
        gender_counts[gender] = gender_counts.get(gender, 0) + 1
    
    gender_data = []
    for gender, count in gender_counts.items():
        gender_data.append({
            'gender': gender,
            'count': count
        })
    
    # Get follow-up status from records
    status_counts = {
        'Not Started': 0,
        'In Progress': 0,
        'All Follow-ups Done': 0,
        'Completed': 0
    }
    
    for record in records:
        outcome = record.get('outcome')
        followup_count = record.get('followup_count', 0)
        
        if outcome:
            status_counts['Completed'] += 1
        elif followup_count and followup_count >= 4:
            status_counts['All Follow-ups Done'] += 1
        elif followup_count and followup_count > 0:
            status_counts['In Progress'] += 1
        else:
            status_counts['Not Started'] += 1
    
    followup_status = []
    for status, count in status_counts.items():
        if count > 0:
            followup_status.append({
                'status': status,
                'count': count
            })
    
    conn.close()
    
    return render_template('reports.html',
                           records=records,
                           total_cases=total_cases,
                           female_cases=female_cases,
                           child_cases=child_cases,
                           pep_cases=pep_cases,
                           female_pct=female_pct,
                           child_pct=child_pct,
                           pep_pct=pep_pct,
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
                           followup_status=followup_status,
                           gender_data=gender_data)

# ─── Export Functionality ───────────────────────────────────────────────────

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
    important_cols = ['OPD Number', 'Client Name', 'Age', 'Sex', 'Violence Type', 
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
@download_required  # Only super_admin can export
def export_patient(patient_id):
    try:
        # Get patient data
        patient = query_db('SELECT * FROM patients WHERE patient_id = ?', [patient_id], one=True)
        
        if not patient:
            flash('Patient not found', 'error')
            return redirect(url_for('patient_lookup'))
        
        # Convert sqlite3.Row to dictionary properly
        patient_dict = {}
        for key in patient.keys():
            patient_dict[key] = patient[key]
        
        # Get initial visit
        initial_visit = query_db('SELECT * FROM initial_visits WHERE patient_id = ?', [patient_id], one=True)
        initial_dict = {}
        if initial_visit:
            for key in initial_visit.keys():
                initial_dict[key] = initial_visit[key]
        
        # Get follow-ups
        follow_ups = query_db('SELECT * FROM follow_ups WHERE patient_id = ? ORDER BY followup_date', [patient_id])
        follow_ups_list = []
        for fu in follow_ups:
            fu_dict = {}
            for key in fu.keys():
                fu_dict[key] = fu[key]
            follow_ups_list.append(fu_dict)
        
        # Create a BytesIO object
        output = BytesIO()
        
        # Create Excel writer
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Patient info sheet
            patient_info = pd.DataFrame([patient_dict])
            patient_info.to_excel(writer, sheet_name='Patient Info', index=False)
            
            # Initial visit sheet
            if initial_dict:
                initial_df = pd.DataFrame([initial_dict])
                initial_df.to_excel(writer, sheet_name='Initial Visit', index=False)
            
            # Follow-ups sheet
            if follow_ups_list:
                follow_ups_df = pd.DataFrame(follow_ups_list)
                follow_ups_df.to_excel(writer, sheet_name='Follow-ups', index=False)
        
        # Set up response
        output.seek(0)
        
        return send_file(
            output,
            download_name=f'patient_{patient_id}_export.xlsx',
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        print(f"Error exporting patient data: {str(e)}")
        flash('Error exporting patient data', 'error')
        return redirect(url_for('view_patient', patient_id=patient_id))



# contact 
@app.route('/contact')
@login_required
def contact():
    return render_template('contact.html')
# ─── Dashboard Statistics API ───────────────────────────────────────────────

@app.route('/api/dashboard_stats')
@login_required
def dashboard_stats():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get counts with proper handling
        cursor.execute('SELECT COUNT(*) FROM patients')
        total_patients = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COUNT(*) FROM patients WHERE sex IN ("F", "Female")')
        female_patients = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COUNT(*) FROM patients WHERE age < 18')
        child_patients = cursor.fetchone()[0] or 0
        
        # Today's patients
        today_date = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('SELECT COUNT(*) FROM patients WHERE DATE(arrival_datetime) = ?', (today_date,))
        today_patients = cursor.fetchone()[0] or 0
        
        # PEP cases
        cursor.execute('''
            SELECT COUNT(DISTINCT p.patient_id) 
            FROM patients p 
            LEFT JOIN initial_visits iv ON p.patient_id = iv.patient_id
            WHERE UPPER(iv.pep_given) IN ('YES', 'Y')
        ''')
        pep_cases = cursor.fetchone()[0] or 0
        
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
        weekly_rows = cursor.fetchall()
        weekly_trend = [{'date': row['date'], 'count': row['count']} for row in weekly_rows]
        
        # Monthly data
        cursor.execute('''
            SELECT 
                strftime('%Y-%m', arrival_datetime) as month,
                COUNT(*) as count
            FROM patients
            WHERE arrival_datetime >= date('now', '-6 months')
            GROUP BY strftime('%Y-%m', arrival_datetime)
            ORDER BY month
        ''')
        monthly_rows = cursor.fetchall()
        monthly = [{'month': row['month'], 'count': row['count']} for row in monthly_rows]
        
        # Violence types
        cursor.execute('''
            SELECT 
                COALESCE(type_violence, 'Not Specified') as type,
                COUNT(*) as count
            FROM patients
            GROUP BY COALESCE(type_violence, 'Not Specified')
            ORDER BY count DESC
        ''')
        violence_rows = cursor.fetchall()
        violence_types = [{'type': row['type'], 'count': row['count']} for row in violence_rows]
        
        # Age distribution
        cursor.execute('''
            SELECT 
                CASE 
                    WHEN age < 18 THEN 'Children (<18)'
                    WHEN age BETWEEN 18 AND 35 THEN 'Youth (18-35)'
                    WHEN age BETWEEN 36 AND 50 THEN 'Adults (36-50)'
                    WHEN age > 50 THEN 'Older Adults (50+)'
                    ELSE 'Unknown'
                END as age_group,
                COUNT(*) as count
            FROM patients
            WHERE age IS NOT NULL
            GROUP BY age_group
        ''')
        age_rows = cursor.fetchall()
        age_distribution = [{'group': row['age_group'], 'count': row['count']} for row in age_rows]
        
        # PEP statistics for pie chart
        cursor.execute('''
            SELECT 
                CASE 
                    WHEN UPPER(iv.pep_given) IN ('YES', 'Y') THEN 'PEP Given'
                    WHEN iv.pep_given IS NOT NULL THEN 'No PEP'
                    ELSE 'Not Recorded'
                END as pep_status,
                COUNT(DISTINCT p.patient_id) as count
            FROM patients p
            LEFT JOIN initial_visits iv ON p.patient_id = iv.patient_id
            GROUP BY pep_status
        ''')
        pep_rows = cursor.fetchall()
        pep_stats = [{'status': row['pep_status'], 'count': row['count']} for row in pep_rows]
    
    return jsonify({
        'total': total_patients,
        'female': female_patients,
        'child': child_patients,
        'today': today_patients,
        'pep_cases': pep_cases,
        'weekly_trend': weekly_trend,
        'monthly': monthly,
        'violence_types': violence_types,
        'age_distribution': age_distribution,
        'pep_stats': pep_stats
    })

    # debug 

# Add this temporary route to debug
@app.route('/debug_stats')
@login_required
def debug_stats():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check PEP data
        cursor.execute('''
            SELECT p.patient_id, p.client_name, iv.pep_given 
            FROM patients p 
            LEFT JOIN initial_visits iv ON p.patient_id = iv.patient_id
        ''')
        pep_data = cursor.fetchall()
        
        # Check counseling data
        cursor.execute('''
            SELECT p.patient_id, p.client_name, 
                   iv.trauma_counseling_initial,
                   COUNT(fu.id) as followup_counseling
            FROM patients p 
            LEFT JOIN initial_visits iv ON p.patient_id = iv.patient_id
            LEFT JOIN follow_ups fu ON p.patient_id = fu.patient_id AND fu.trauma_counseling = 'Yes'
            GROUP BY p.patient_id
        ''')
        counseling_data = cursor.fetchall()
        
        return {
            'pep_data': [dict(row) for row in pep_data],
            'counseling_data': [dict(row) for row in counseling_data]
        }

# ─── Error handlers ──────────────────────────────────────────────────────────

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)