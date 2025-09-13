from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit, join_room, leave_room
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import os
from dotenv import load_dotenv
import phonenumbers
import uuid

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_VERIFY_SERVICE_SID = os.getenv('TWILIO_VERIFY_SERVICE_SID')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    mobile_number = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    contacts = db.relationship('Contact', backref='owner', lazy=True, cascade="all, delete-orphan")
    call_history = db.relationship('CallHistory', backref='caller', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"User('{self.mobile_number}', '{self.name}')"

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    mobile_number = db.Column(db.String(20), nullable=False)

    def __repr__(self):
        return f"Contact('{self.name}', '{self.mobile_number}')"

class CallHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    contact_number = db.Column(db.String(20), nullable=False)
    call_type = db.Column(db.String(10), nullable=False) # e.g., 'outgoing', 'incoming', 'missed'
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

    def __repr__(self):
        return f"CallHistory('{self.user_id}', '{self.contact_number}', '{self.call_type}')"

# Helper function to format phone numbers
def format_phone_number(number):
    try:
        parsed_number = phonenumbers.parse(number, "US") # Assume US for now, could be dynamic
        if not phonenumbers.is_valid_number(parsed_number):
            return None
        return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        return None

# Routes
@app.before_request
def create_tables():
    db.create_all()

@app.route('/')
def index():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user and user.is_verified:
            return redirect(url_for('dashboard'))
        elif user and not user.is_verified:
            flash('Please verify your mobile number to continue.', 'warning')
            return redirect(url_for('verify_otp'))
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name = request.form.get('name')
        mobile_number = request.form.get('mobile_number')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not name or not mobile_number or not password or not confirm_password:
            flash('All fields are required.', 'danger')
            return render_template('signup.html', name=name, mobile_number=mobile_number)

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('signup.html', name=name, mobile_number=mobile_number)

        formatted_number = format_phone_number(mobile_number)
        if not formatted_number:
            flash('Invalid mobile number format.', 'danger')
            return render_template('signup.html', name=name, mobile_number=mobile_number)

        existing_user = User.query.filter_by(mobile_number=formatted_number).first()
        if existing_user:
            flash('Mobile number already registered.', 'danger')
            return render_template('signup.html', name=name, mobile_number=mobile_number)

        new_user = User(name=name, mobile_number=formatted_number)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        session['user_id'] = new_user.id
        session['temp_mobile_number'] = formatted_number # Store for OTP verification

        # Send OTP
        try:
            verification = twilio_client.verify.v2.services(TWILIO_VERIFY_SERVICE_SID) \
                .verifications.create(to=formatted_number, channel='sms')
            flash(f'Verification code sent to {formatted_number}', 'success')
            return redirect(url_for('verify_otp'))
        except TwilioRestException as e:
            flash(f'Failed to send OTP: {e}', 'danger')
            db.session.delete(new_user) # Rollback user creation
            db.session.commit()
            return render_template('signup.html', name=name, mobile_number=mobile_number)

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        mobile_number = request.form.get('mobile_number')
        password = request.form.get('password')

        if not mobile_number or not password:
            flash('Both mobile number and password are required.', 'danger')
            return render_template('login.html', mobile_number=mobile_number)

        formatted_number = format_phone_number(mobile_number)
        if not formatted_number:
            flash('Invalid mobile number format.', 'danger')
            return render_template('login.html', mobile_number=mobile_number)

        user = User.query.filter_by(mobile_number=formatted_number).first()

        if not user or not user.check_password(password):
            flash('Invalid mobile number or password.', 'danger')
            return render_template('login.html', mobile_number=mobile_number)

        if not user.is_verified:
            session['user_id'] = user.id
            session['temp_mobile_number'] = formatted_number
            flash('Please verify your mobile number to continue.', 'warning')
            # Resend OTP if not verified
            try:
                verification = twilio_client.verify.v2.services(TWILIO_VERIFY_SERVICE_SID) \
                    .verifications.create(to=formatted_number, channel='sms')
                flash(f'Verification code sent to {formatted_number}', 'success')
            except TwilioRestException as e:
                flash(f'Failed to send OTP: {e}', 'danger')
            return redirect(url_for('verify_otp'))

        session['user_id'] = user.id
        flash('Logged in successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('login.html')

@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    if 'user_id' not in session or 'temp_mobile_number' not in session:
        flash('Please sign up or log in first.', 'warning')
        return redirect(url_for('index'))

    user_id = session['user_id']
    mobile_number = session['temp_mobile_number']
    user = User.query.get(user_id)

    if not user or user.mobile_number != mobile_number:
        flash('User or mobile number mismatch.', 'danger')
        return redirect(url_for('index'))

    if user.is_verified:
        flash('Your account is already verified.', 'info')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        otp_code = request.form.get('otp_code')

        if not otp_code:
            flash('OTP code is required.', 'danger')
            return render_template('verify_otp.html', mobile_number=mobile_number)

        try:
            verification_check = twilio_client.verify.v2.services(TWILIO_VERIFY_SERVICE_SID) \
                .verification_checks.create(to=mobile_number, code=otp_code)

            if verification_check.status == 'approved':
                user.is_verified = True
                db.session.commit()
                session.pop('temp_mobile_number', None) # Remove temp mobile number
                flash('Mobile number successfully verified!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid OTP code. Please try again.', 'danger')
        except TwilioRestException as e:
            flash(f'Error verifying OTP: {e}', 'danger')

    return render_template('verify_otp.html', mobile_number=mobile_number)

@app.route('/resend_otp', methods=['POST'])
def resend_otp():
    if 'user_id' not in session or 'temp_mobile_number' not in session:
        return jsonify({'success': False, 'message': 'Session expired or invalid.'}), 400

    mobile_number = session['temp_mobile_number']
    user_id = session['user_id']
    user = User.query.get(user_id)

    if not user or user.mobile_number != mobile_number or user.is_verified:
        return jsonify({'success': False, 'message': 'Invalid request or already verified.'}), 400

    try:
        verification = twilio_client.verify.v2.services(TWILIO_VERIFY_SERVICE_SID) \
            .verifications.create(to=mobile_number, channel='sms')
        return jsonify({'success': True, 'message': f'New verification code sent to {mobile_number}.'}), 200
    except TwilioRestException as e:
        return jsonify({'success': False, 'message': f'Failed to resend OTP: {e}'}), 500


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please log in to access the dashboard.', 'warning')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user or not user.is_verified:
        flash('Please verify your mobile number.', 'warning')
        return redirect(url_for('verify_otp'))

    contacts = Contact.query.filter_by(user_id=user.id).order_by(Contact.name).all()
    call_history = CallHistory.query.filter_by(user_id=user.id).order_by(CallHistory.timestamp.desc()).limit(10).all()

    return render_template('dashboard.html', user=user, contacts=contacts, call_history=call_history)

@app.route('/add_contact', methods=['POST'])
def add_contact():
    if 'user_id' not in session:
        flash('Please log in to add contacts.', 'danger')
        return redirect(url_for('login'))

    name = request.form.get('contact_name')
    mobile_number = request.form.get('contact_mobile_number')

    if not name or not mobile_number:
        flash('Contact name and mobile number are required.', 'danger')
        return redirect(url_for('dashboard'))

    formatted_number = format_phone_number(mobile_number)
    if not formatted_number:
        flash('Invalid mobile number format for contact.', 'danger')
        return redirect(url_for('dashboard'))

    user_id = session['user_id']
    existing_contact = Contact.query.filter_by(user_id=user_id, mobile_number=formatted_number).first()
    if existing_contact:
        flash('Contact with this number already exists.', 'warning')
        return redirect(url_for('dashboard'))

    new_contact = Contact(user_id=user_id, name=name, mobile_number=formatted_number)
    db.session.add(new_contact)
    db.session.commit()
    flash('Contact added successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/delete_contact/<int:contact_id>', methods=['POST'])
def delete_contact(contact_id):
    if 'user_id' not in session:
        flash('Please log in to manage contacts.', 'danger')
        return redirect(url_for('login'))

    contact = Contact.query.filter_by(id=contact_id, user_id=session['user_id']).first()

    if not contact:
        flash('Contact not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('dashboard'))

    db.session.delete(contact)
    db.session.commit()
    flash('Contact deleted successfully.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('temp_mobile_number', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# WebRTC signaling and SocketIO events
active_users = {}

@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user and user.is_verified:
            active_users[user.mobile_number] = request.sid
            print(f"User {user.mobile_number} connected with SID {request.sid}")
            emit('user_status', {'mobile_number': user.mobile_number, 'status': 'online'}, broadcast=True)
            # send existing active users to the newly connected user
            online_users = [{'mobile_number': num, 'status': 'online'} for num in active_users.keys()]
            emit('online_users_list', online_users)
        else:
            # If user is not logged in or not verified, disconnect them
            print(f"Unauthorized connection attempt from SID {request.sid}. Disconnecting.")
            emit('unauthorized', {'message': 'Please login and verify your account.'})
            return False # Reject connection
    else:
        print(f"Anonymous connection attempt from SID {request.sid}. Disconnecting.")
        emit('unauthorized', {'message': 'Please login to use the service.'})
        return False # Reject connection

@socketio.on('disconnect')
def handle_disconnect():
    user_mobile_number = None
    for num, sid in active_users.items():
        if sid == request.sid:
            user_mobile_number = num
            break

    if user_mobile_number:
        del active_users[user_mobile_number]
        print(f"User {user_mobile_number} disconnected from SID {request.sid}")
        emit('user_status', {'mobile_number': user_mobile_number, 'status': 'offline'}, broadcast=True)

@socketio.on('call_user')
def call_user(data):
    caller_id = session.get('user_id')
    caller = User.query.get(caller_id)
    if not caller or not caller.is_verified:
        emit('call_failed', {'message': 'Unauthorized to make calls.'}, room=request.sid)
        return

    target_number = data.get('target_number')
    offer = data.get('offer')

    if not target_number or not offer:
        emit('call_failed', {'message': 'Invalid call request.'}, room=request.sid)
        return

    target_sid = active_users.get(target_number)

    if target_sid:
        print(f"Calling {target_number} from {caller.mobile_number}")
        # Add to call history for caller
        call_record = CallHistory(user_id=caller.id, contact_number=target_number, call_type='outgoing')
        db.session.add(call_record)
        db.session.commit()
        emit('incoming_call', {'caller_number': caller.mobile_number, 'offer': offer}, room=target_sid)
        emit('call_initiated', {'target_number': target_number, 'message': 'Calling...'}, room=request.sid)
    else:
        print(f"User {target_number} is offline or not found.")
        # Log missed call for the target if they exist in the DB
        target_user_obj = User.query.filter_by(mobile_number=target_number).first()
        if target_user_obj:
            missed_call = CallHistory(user_id=target_user_obj.id, contact_number=caller.mobile_number, call_type='missed')
            db.session.add(missed_call)
            db.session.commit()

        emit('call_failed', {'message': f'User {target_number} is offline or not found.'}, room=request.sid)

@socketio.on('answer_call')
def answer_call(data):
    current_user_id = session.get('user_id')
    current_user = User.query.get(current_user_id)
    if not current_user or not current_user.is_verified:
        emit('call_failed', {'message': 'Unauthorized to answer calls.'}, room=request.sid)
        return

    caller_number = data.get('caller_number')
    answer = data.get('answer')

    caller_sid = active_users.get(caller_number)

    if caller_sid:
        print(f"User {current_user.mobile_number} answering call from {caller_number}")
        # Add to call history for current user (receiver)
        call_record = CallHistory(user_id=current_user.id, contact_number=caller_number, call_type='incoming')
        db.session.add(call_record)
        db.session.commit()
        emit('call_accepted', {'answer': answer, 'answerer_number': current_user.mobile_number}, room=caller_sid)
    else:
        emit('call_failed', {'message': 'Caller disconnected.'}, room=request.sid)

@socketio.on('reject_call')
def reject_call(data):
    current_user_id = session.get('user_id')
    current_user = User.query.get(current_user_id)
    if not current_user or not current_user.is_verified:
        emit('call_failed', {'message': 'Unauthorized action.'}, room=request.sid)
        return

    caller_number = data.get('caller_number')

    caller_sid = active_users.get(caller_number)

    if caller_sid:
        print(f"User {current_user.mobile_number} rejecting call from {caller_number}")
        emit('call_rejected', {'rejecter_number': current_user.mobile_number}, room=caller_sid)
        # Log missed call for the caller
        caller_user_obj = User.query.filter_by(mobile_number=caller_number).first()
        if caller_user_obj:
            missed_call = CallHistory(user_id=caller_user_obj.id, contact_number=current_user.mobile_number, call_type='missed')
            db.session.add(missed_call)
            db.session.commit()


@socketio.on('ice_candidate')
def ice_candidate(data):
    target_number = data.get('target_number')
    candidate = data.get('candidate')
    sender_number = data.get('sender_number') # The number of the user sending the ICE candidate

    target_sid = active_users.get(target_number)
    if target_sid:
        emit('ice_candidate', {'candidate': candidate, 'sender_number': sender_number}, room=target_sid)

@socketio.on('end_call')
def end_call(data):
    current_user_id = session.get('user_id')
    current_user = User.query.get(current_user_id)
    if not current_user or not current_user.is_verified:
        emit('call_failed', {'message': 'Unauthorized action.'}, room=request.sid)
        return

    target_number = data.get('target_number')
    target_sid = active_users.get(target_number)

    if target_sid:
        emit('call_ended', {'ender_number': current_user.mobile_number}, room=target_sid)
    emit('call_ended', {'ender_number': current_user.mobile_number}, room=request.sid)
    print(f"Call between {current_user.mobile_number} and {target_number} ended.")

@socketio.on('error')
def handle_error(e):
    print(f"SocketIO Error: {e}")
    flash(f"A real-time communication error occurred: {e}", 'danger')


if __name__ == '__main__':
    # Run with `flask run` or `python app.py`
    # For development, you can use app.run(), but socketio.run() is preferred for SocketIO apps.
    # socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
    # For production, use a WSGI server like Gunicorn + Eventlet/Gevent.
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True, port=5000)
