# app.py
import os
import re
import json
import base64
import pytz
import csv
from datetime import datetime
from dotenv import load_dotenv
from io import StringIO
from flask import Flask, render_template, request, jsonify, session, redirect, Response
import gspread
from google.oauth2.credentials import Credentials 
from drive_manager import upload_photo_to_drive 

# Load env vars before anything else
load_dotenv() 

app = Flask(__name__)

# [SECURE] Load Configuration
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback_dev_key")
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Visitor_Database")

# Define Timezone
IST = pytz.timezone('Asia/Kolkata')

ws_users = None
ws_visitors = None
ws_bookings = None

def connect_to_db():
    global ws_users, ws_visitors, ws_bookings
    try:
        creds = None
        if os.getenv('GOOGLE_TOKEN'):
            token_info = json.loads(os.getenv('GOOGLE_TOKEN'))
            creds = Credentials.from_authorized_user_info(token_info, ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        elif os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])

        if creds:
            gc = gspread.authorize(creds)
            if SHEET_ID:
                sh = gc.open_by_key(SHEET_ID)
            else:
                sh = gc.open(SHEET_NAME)
                
            ws_users = sh.worksheet("Users")
            ws_visitors = sh.worksheet("Visitors")
            ws_bookings = sh.worksheet("Bookings")
            print("✅ Connected to Google Database.")
            return True
        else:
            print("❌ No credentials found.")
            return False
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return False

connect_to_db()

# --- ROUTES ---

@app.route('/')
def index():
    firebase_config = {
        'apiKey': os.getenv('FIREBASE_API_KEY'),
        'authDomain': os.getenv('FIREBASE_AUTH_DOMAIN'),
        'projectId': os.getenv('FIREBASE_PROJECT_ID'),
        'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET'),
        'messagingSenderId': os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
        'appId': os.getenv('FIREBASE_APP_ID')
    }
    return render_template('login.html', firebase_config=firebase_config)

@app.route('/api/login', methods=['POST'])
def api_login():
    if not ws_users: connect_to_db()
    data = request.json
    email = data.get('email', '').lower().strip()
    name = data.get('name')

    # UNIFIED LOOKUP: Checks Users sheet for Admin, Security, or Faculty
    try:
        cell = ws_users.find(email)
        row_vals = ws_users.row_values(cell.row)
        
        # Column B (Index 1) = Role ('Admin', 'Security', 'Faculty')
        role = row_vals[1] if len(row_vals) > 1 and row_vals[1].strip() else 'Faculty'
        
        # Column D (Index 3) = Department
        if len(row_vals) > 3 and row_vals[3].strip():
            dept = row_vals[3].strip()
        else:
            dept = 'ADMIN' if role == 'Admin' else ('SECURITY' if role == 'Security' else 'STAFF')

        session['user'] = email
        session['role'] = role
        session['name'] = name or (row_vals[2] if len(row_vals) > 2 and row_vals[2].strip() else email.split('@')[0])
        session['dept'] = dept

        return jsonify({'status': 'success', 'redirect': '/dashboard'})
    except Exception as e:
        print(f"Login lookup failed: {e}") 

    return jsonify({'status': 'error', 'message': 'Access Denied: User not registered in database.'})

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect('/')
    role = session['role']
    if not ws_visitors: connect_to_db()

    if role == 'Security': 
        return render_template('security_dashboard.html')
    elif role == 'Faculty': 
        return render_template('faculty_dashboard.html')
    elif role == 'Admin':
        active_visitors = []
        past_visitors = []
        upcoming_bookings = []
        past_bookings = []
        
        # Stats Counters
        total_entries_count = 0
        today_entries_count = 0
        
        try:
            v_rows = ws_visitors.get_all_values()
            normalized_rows = []
            
            # Standardize column structure (skip header row 0)
            for idx, r in enumerate(v_rows[1:]):
                row = list(r)
                while len(row) < 13:
                    row.append("")
                # Pass ID / Row number
                row.append(idx + 1)
                normalized_rows.append(row)
            
            normalized_rows.reverse() # Newest first
            total_entries_count = len(normalized_rows)
            
            # Calculate Today's Count
            today_str = datetime.now(IST).strftime("%d-%m-%Y")
            today_entries_count = sum(1 for row in normalized_rows if row[0] == today_str)

            # Strictly separate: Active Visitors (currently inside) vs Past Visitors (logged out)
            for row in normalized_rows:
                out_time = str(row[10]).strip()
                if out_time == "":
                    active_visitors.append(row)
                else:
                    past_visitors.append(row)

            # Bookings Logic
            b_rows = ws_bookings.get_all_values()
            for row in b_rows[1:]:
                if len(row) > 7:
                    if row[7] == "Pending": upcoming_bookings.append(row)
                    else: past_bookings.append(row)
            upcoming_bookings.reverse()
            past_bookings.reverse()
            
        except Exception as e: 
             print(f"Dashboard Data Error: {e}")

        return render_template('admin_dashboard.html', 
                             active_visitors=active_visitors,
                             past_visitors=past_visitors,
                             bookings=upcoming_bookings,
                             past_bookings=past_bookings,
                             total_entries=total_entries_count,
                             today_count=today_entries_count,
                             sheet_id=SHEET_ID, 
                             drive_id=DRIVE_FOLDER_ID)
    
    return "Unknown Role"

@app.route('/api/book_visitor', methods=['POST'])
def book_visitor():
    if session.get('role') not in ['Faculty', 'Admin']: return jsonify({'error': 'Unauthorized'})
    data = request.json
    
    try:
        mobile_to_check = str(data.get('mobile')).strip()
        all_bookings = ws_bookings.get_all_values()
        for row in all_bookings[1:]:
            if len(row) > 7:
                existing_mobile = str(row[4]).strip()
                status = row[7]
                if existing_mobile == mobile_to_check and status == "Pending":
                    return jsonify({'status': 'error', 'message': 'Duplicate: Visitor has pending booking.'})
    except: pass

    host_name = data.get('to_meet', session['name'])
    host_dept = data.get('department', session.get('dept', 'STAFF'))
    booked_by_email = session['user']

    row = [
        datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
        booked_by_email,
        host_name,
        host_dept,
        data['mobile'],
        data['name'],
        data['purpose'],
        "Pending",
        data.get('company', '-'),
        data.get('vehicle', '-')
    ]
    try:
        ws_bookings.append_row(row)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})
    
@app.route('/api/get_today_bookings', methods=['GET'])
def get_today_bookings():
    if session.get('role') != 'Security': return jsonify([])
    try:
        if not ws_bookings: connect_to_db()
        all_bookings = ws_bookings.get_all_values()
        pending_list = []
        for row in all_bookings[1:]:
            if len(row) > 7 and row[7] == "Pending":
                vehicle_val = row[9] if len(row) > 9 else "-"
                pending_list.append({
                    'time': row[0],
                    'booked_by': row[2],
                    'dept': row[3],
                    'mobile': row[4],
                    'visitor': row[5],
                    'purpose': row[6],
                    'company': row[8] if len(row) > 8 else "-",
                    'vehicle_number': vehicle_val
                })
        return jsonify(pending_list)
    except: return jsonify([])

@app.route('/api/get_user_bookings', methods=['GET'])
def get_user_bookings():
    if 'user' not in session: return jsonify([])
    try:
        if not ws_bookings: connect_to_db()
        all_rows = ws_bookings.get_all_values()
        my_bookings = []
        user_email = session['user']
        
        for row in all_rows[1:]:
            if len(row) > 1 and row[1] == user_email:
                my_bookings.append({
                    'time': row[0],
                    'visitor': row[5],
                    'mobile': row[4],
                    'purpose': row[6],
                    'status': row[7]
                })
        return jsonify(list(reversed(my_bookings)))
    except Exception as e:
        return jsonify([])

@app.route('/api/get_active_visitors', methods=['GET'])
def get_active_visitors():
    if session.get('role') != 'Security': return jsonify([])
    try:
        if not ws_visitors: connect_to_db()
        all_rows = ws_visitors.get_all_values()
        active_list = []
        
        for row in all_rows[1:]:
            r = list(row)
            while len(r) < 13:
                r.append("")
            out_time = str(r[10]).strip()
            # ONLY include visitor if out_time is completely blank
            if out_time == "":
                active_list.append({
                    'in_time': r[1],
                    'mobile': r[2],
                    'name': r[3],
                    'vehicle': r[12] if len(r) > 12 and r[12] else "-",
                    'to_meet': r[7],
                    'dept': r[8],
                    'photo': r[9]
                })
        return jsonify(list(reversed(active_list)))
    except: return jsonify([])

@app.route('/api/get_past_visitors', methods=['GET'])
def get_past_visitors():
    if session.get('role') not in ['Security', 'Admin']: 
        return jsonify([])
    try:
        if not ws_visitors: connect_to_db()
        all_rows = ws_visitors.get_all_values()
        past_list = []
        
        for idx, row in enumerate(all_rows[1:]):
            r = list(row)
            while len(r) < 13:
                r.append("")
            out_time = str(r[10]).strip()
            # ONLY include visitor if out_time is NOT blank
            if out_time != "":
                past_list.append({
                    'pass_id': idx + 2,
                    'date': r[0],
                    'in_time': r[1],
                    'out_time': out_time,
                    'mobile': r[2],
                    'name': r[3],
                    'designation': r[4] if len(r) > 4 else "-",
                    'company': r[5] if len(r) > 5 else "-",
                    'to_meet': r[7],
                    'dept': r[8],
                    'photo': r[9],
                    'vehicle': r[12] if len(r) > 12 and r[12] else "-"
                })
        return jsonify(list(reversed(past_list)))
    except Exception as e:
        print(f"Error fetching past visitors: {e}")
        return jsonify([])


@app.route('/api/check_visitor', methods=['GET'])
def check_visitor():
    mobile = request.args.get('mobile')
    try:
        cell_list = ws_bookings.findall(mobile)
        for cell in cell_list:
            if cell.col == 5: 
                row = ws_bookings.row_values(cell.row)
                if row[7] == "Pending":
                    vehicle = row[9] if len(row) > 9 else ""
                    return jsonify({'found': True, 'is_booking': True, 'name': row[5], 'purpose': row[6], 'booked_by': row[2], 'department': row[3], 'company': row[8], 'vehicle': vehicle, 'to_meet': row[2]})
    except: pass
    try:
        cells = ws_visitors.findall(mobile)
        if cells:
            row = ws_visitors.row_values(cells[-1].row)
            vehicle = row[12] if len(row) > 12 else ""
            return jsonify({
                'found': True, 'is_booking': False, 
                'name': row[3], 'designation': row[4], 
                'company': row[5], 'laptop': row[6], 
                'to_meet': row[7], 'department': row[8], 
                'vehicle': vehicle
            })
    except: pass
    return jsonify({'found': False})

@app.route('/api/get_next_id', methods=['GET'])
def get_next_id():
    try:
        if not ws_visitors: connect_to_db()
        current_count = len(ws_visitors.col_values(1)) 
        return jsonify({'next_id': current_count})
    except: return jsonify({'next_id': '---'})

@app.route('/api/entry', methods=['POST'])
def entry():
    if session.get('role') != 'Security': return jsonify({'error': 'Unauthorized'})
    try:
        data = request.json
        image_data = data['image']
        header, encoded = image_data.split(",", 1)
        image_bytes = base64.b64decode(encoded)
        
        now = datetime.now(IST)
        filename = f"{now.strftime('%d-%m-%Y')}_{data['mobile']}_{now.strftime('%H%M%S')}.jpg"
        photo_url = ""

        try:
            if not DRIVE_FOLDER_ID: raise Exception("GOOGLE_DRIVE_FOLDER_ID not set in Env")
            drive_link = upload_photo_to_drive(image_bytes, filename, DRIVE_FOLDER_ID)
            if drive_link: photo_url = drive_link
        except Exception as e:
            print(f"⚠️ Drive Failed: {e}")
            return jsonify({'status': 'error', 'message': 'Photo Upload Failed.'})

        new_row = [
            now.strftime("%d-%m-%Y"),
            now.strftime("%I:%M %p"),
            data['mobile'],
            data['name'],
            data['designation'],
            data['company'],
            data.get('laptop', '-'),
            data['to_meet'],
            data['department'],
            photo_url,
            "", 
            session['user'],
            data.get('vehicle', '-') 
        ]
        ws_visitors.append_row(new_row)
        
        try:
            cell_list = ws_bookings.findall(data['mobile'])
            for cell in cell_list:
                if cell.col == 5 and ws_bookings.cell(cell.row, 8).value == "Pending": 
                    ws_bookings.update_cell(cell.row, 8, "Arrived")
        except: pass

        return jsonify({'status': 'success', 'pass_id': len(ws_visitors.get_all_values()), 'date': new_row[0], 'in_time': new_row[1], 'photo': photo_url})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/exit', methods=['POST'])
def exit_visitor():
    data = request.json
    mobile = str(data.get('mobile')).strip()
    custom_time = data.get('out_time')
    
    try:
        if not ws_visitors: connect_to_db()
        all_rows = ws_visitors.get_all_values()
        target_row_index = -1
        
        total_rows = len(all_rows)
        # Search backwards specifically for the ACTIVE entry of this visitor (where out_time is empty)
        for i in range(total_rows - 1, 0, -1): 
            row = all_rows[i]
            r = list(row)
            while len(r) < 13:
                r.append("")
            row_mobile = str(r[2]).strip() 
            out_val = str(r[10]).strip()
            
            if row_mobile == mobile and out_val == "":
                target_row_index = i + 1 
                break
        
        # If no active entry found, check if they were already marked OUT to give clear notification
        if target_row_index == -1:
            for i in range(total_rows - 1, 0, -1):
                row = all_rows[i]
                r = list(row)
                while len(r) < 13:
                    r.append("")
                if str(r[2]).strip() == mobile and str(r[10]).strip() != "":
                    return jsonify({'status': 'error', 'message': f'Visitor already marked OUT (Time: {r[10]})'})
            return jsonify({'status': 'error', 'message': 'Active visitor not found on campus'})
             
        if custom_time:
            try:
                t_obj = datetime.strptime(custom_time, "%H:%M")
                out_time = t_obj.strftime("%I:%M %p")
            except:
                out_time = datetime.now(IST).strftime("%I:%M %p")
        else:
            out_time = datetime.now(IST).strftime("%I:%M %p")

        ws_visitors.update_cell(target_row_index, 11, out_time)
        return jsonify({'status': 'success', 'out_time': out_time})

    except Exception as e:
        print(f"Exit Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)})

# --- ADMIN ROUTES ---

@app.route('/api/admin/filter_data', methods=['POST'])
def filter_data():
    if session.get('role') != 'Admin': 
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    
    data = request.json
    start_str = data.get('from')
    end_str = data.get('to')

    if not ws_visitors: connect_to_db()
    
    try:
        start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
        
        all_rows = ws_visitors.get_all_values()
        headers = all_rows[0]
        filtered_rows = []

        for idx, row in enumerate(all_rows[1:]): 
            try:
                sheet_row_number = idx + 2 
                row_date = datetime.strptime(row[0], "%d-%m-%Y").date()
                
                if start_date <= row_date <= end_date:
                    row.append(sheet_row_number)
                    filtered_rows.append(row)
            except (ValueError, IndexError):
                continue

        return jsonify({
            'status': 'success',
            'headers': headers,
            'data': filtered_rows
        })
    except Exception as e:
        print(f"Filter Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/download_report', methods=['GET'])
def download_report():
    if session.get('role') != 'Admin': return "Unauthorized", 403
    
    start_str = request.args.get('from')
    end_str = request.args.get('to')
    
    try:
        start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
        
        all_rows = ws_visitors.get_all_values()
        
        si = StringIO()
        cw = csv.writer(si)
        cw.writerow(all_rows[0]) # Header
        
        for row in all_rows[1:]:
            try:
                row_date = datetime.strptime(row[0], "%d-%m-%Y").date()
                if start_date <= row_date <= end_date:
                    cw.writerow(row)
            except: continue

        output = si.getvalue()
        
        filename = f"VISITOR_REPORT_{start_str}_{end_str}.csv"
        
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        return str(e), 500

@app.route('/api/admin/search_visitor', methods=['GET'])
def search_visitor():
    if session.get('role') != 'Admin': return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    
    mobile = request.args.get('mobile', '').strip()
    if not mobile:
        return jsonify({'status': 'error', 'message': 'Mobile number required'})

    if not ws_visitors: connect_to_db()

    try:
        all_rows = ws_visitors.get_all_values()
        visitor_history = []
        visitor_details = {}
        visit_count = 0
        
        clean_search_mobile = ''.join(filter(str.isdigit, mobile))

        for idx, row in enumerate(all_rows[1:]):
            if len(row) > 2:
                sheet_mobile = str(row[2]).strip()
                clean_sheet_mobile = ''.join(filter(str.isdigit, sheet_mobile))
                
                if clean_sheet_mobile == clean_search_mobile:
                    visit_count += 1
                    
                    visitor_details = {
                        'name': row[3] if len(row) > 3 else "-",
                        'company': row[5] if len(row) > 5 else "-",
                        'designation': row[4] if len(row) > 4 else "-",
                        'photo': row[9] if len(row) > 9 else ""
                    }
                    
                    row_copy = list(row)
                    row_copy.append(idx + 2)
                    visitor_history.append(row_copy)

        if visit_count == 0:
            return jsonify({'status': 'success', 'found': False})

        return jsonify({
            'status': 'success',
            'found': True,
            'details': visitor_details,
            'visit_count': visit_count,
            'history': list(reversed(visitor_history))
        })

    except Exception as e:
        print(f"Search Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
if __name__ == '__main__':
    app.run(debug=True, port=5000)
