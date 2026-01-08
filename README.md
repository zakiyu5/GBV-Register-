# Digital GBV Register (HMIS MCH 061)

A complete offline digital version of the **Gender-Based Violence Register (HMIS MCH 061)** used in health facilities.

This is a standalone web application that runs on a local computer or local server. All data is stored locally — no internet connection or external server is required.

## Features

- Full data entry form matching the official HMIS MCH 061 register (initial visit, lab tests, treatments, and all follow-up visits: 2 weeks, 1 month, 3 months, 6 months)
- View all records
- Filtered reports (Daily, Weekly, Monthly, Quarterly, Yearly, All Time)
- Export reports to **CSV** and **Excel (.xlsx)**
- Print official-looking register pages (save as PDF using browser print)
- Works completely offline
- Simple and fast - designed for daily use by health workers

## Requirements

- Python 3.8 or higher
- Windows, Mac, or Linux computer

## Installation & Setup (Local Computer or Hospital Server)

### 1. Download the Application
- Obtain the folder containing all files (app.py, templates folder, requirements.txt, etc.)

### 2. Install Python Dependencies
Open Command Prompt (Windows) or Terminal (Mac/Linux) and navigate to the project folder:

```bash
cd path/to/digital-gbv-register
Install required packages:
Bashpip install -r requirements.txt
3. Run the Application
Bashpython app.py
4. Open in Browser
Visit: http://127.0.0.1:5000
The database file gbv.db will be created automatically on first run.
Usage Guide

Home Page → Data Entry Form (fill exactly like the paper register)
Records → View all entered cases
Reports →
Select time period (e.g., Monthly)
View filtered cases
Export to CSV or Excel
Click "Print Official Register" → Save as PDF or print directly

Dashboard → Quick statistics and charts

Important Notes

All data is stored locally in gbv.db (SQLite file) on the computer
Never share or upload the gbv.db file — it contains sensitive patient information
Make regular backups of the gbv.db file
For security: protect the computer with a password

requirements.txt
textFlask==3.0.3
pandas==2.2.2
openpyxl==3.1.5
Privacy & Security

No data leaves the computer
Designed for single-facility offline use
Sensitive data must remain confidential

Support
For technical issues or improvements, contact the system administrator.
