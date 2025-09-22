import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_cors import CORS
from openai import OpenAI

app = Flask(__name__)

# Configurations
app.config['SECRET_KEY'] = 'a_very_secret_key_that_should_be_changed'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
CORS(app)

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Database Models


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    mobile = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)


class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    mobile = db.Column(db.String(20), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class CallHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    caller_mobile = db.Column(db.String(20), nullable=False)
    receiver_mobile = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    duration = db.Column(db.Integer, default=0)  # Duration in seconds
    # e.g., 'outgoing', 'incoming_answered', 'incoming_missed'
    status = db.Column(db.String(20), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


# --- Routes ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        mobile = data.get('mobile')
        password = data.get('password')
        user = User.query.filter_by(mobile=mobile).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return jsonify({'success': True, 'message': 'Login successful!'})
        return jsonify({'success': False, 'message': 'Invalid mobile number or password.'}), 401
    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        data = request.get_json()
        name = data.get('name')
        mobile = data.get('mobile')
        password = data.get('password')

        if User.query.filter_by(mobile=mobile).first():
            return jsonify({'success': False, 'message': 'Mobile number already registered.'}), 409

        hashed_password = bcrypt.generate_password_hash(
            password).decode('utf-8')
        new_user = User(name=name, mobile=mobile, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        return jsonify({'success': True, 'message': 'User registered successfully!'}), 201
    return render_template('signup.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

# --- API Endpoints ---


@app.route('/api/contacts', methods=['GET', 'POST'])
@login_required
def manage_contacts():
    if request.method == 'POST':
        data = request.get_json()
        name = data.get('name')
        mobile = data.get('mobile')
        if not name or not mobile:
            return jsonify({'success': False, 'message': 'Name and mobile are required.'}), 400
        new_contact = Contact(name=name, mobile=mobile,
                              user_id=current_user.id)
        db.session.add(new_contact)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Contact added.', 'contact': {'id': new_contact.id, 'name': name, 'mobile': mobile}}), 201

    contacts = Contact.query.filter_by(user_id=current_user.id).all()
    return jsonify([{'id': c.id, 'name': c.name, 'mobile': c.mobile} for c in contacts])


@app.route('/api/contacts/<int:contact_id>', methods=['DELETE'])
@login_required
def delete_contact(contact_id):
    contact = Contact.query.filter_by(
        id=contact_id, user_id=current_user.id).first()
    if contact:
        db.session.delete(contact)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Contact deleted.'})
    return jsonify({'success': False, 'message': 'Contact not found.'}), 404


@app.route('/api/call-history', methods=['GET', 'POST'])
@login_required
def call_history():
    if request.method == 'POST':
        data = request.get_json()
        new_log = CallHistory(
            caller_mobile=data['caller_mobile'],
            receiver_mobile=data['receiver_mobile'],
            duration=data['duration'],
            status=data['status'],
            user_id=current_user.id
        )
        db.session.add(new_log)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Call history logged.'}), 201

    history = CallHistory.query.filter_by(user_id=current_user.id).order_by(
        CallHistory.timestamp.desc()).all()
    return jsonify([{
        'caller_mobile': h.caller_mobile,
        'receiver_mobile': h.receiver_mobile,
        'timestamp': h.timestamp.isoformat(),
        'duration': h.duration,
        'status': h.status
    } for h in history])


@app.route('/api/symptom-Checker', methods=['POST'])
@login_required
def symptom_checker():
    symptoms = request.args.get("symptoms")
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key="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",
    )

    completion = client.chat.completions.create(
        extra_body={},
        model="openai/gpt-oss-120b:free",
        messages=[
            {
                "role": "user",
                "content": f"""Symptoms:
{symptoms}

You are a Professional phamacist
Classify the possible diseases based on the above symptoms and provide a single answer in layman terms
optimize this input for tinyllama as a prompt"""
            }
        ]
    )

    return jsonify({"result": completion.choices[0].message.content})

# --- Socket.IO Events for WebRTC Signaling ---


# In-memory store for user session IDs
# In a real-world app, use Redis or another persistent store
online_users = {}


@socketio.on('connect')
def on_connect():
    print(f'Client connected: {request.sid}')


@socketio.on('register')
def on_register(data):
    mobile = data.get('mobile')
    if mobile:
        online_users[mobile] = request.sid
        print(f'User {mobile} registered with SID {request.sid}')
        print(f'Online users: {online_users}')


@socketio.on('disconnect')
def on_disconnect():
    print(f'Client disconnected: {request.sid}')
    for mobile, sid in list(online_users.items()):
        if sid == request.sid:
            del online_users[mobile]
            print(f'User {mobile} unregistered')
            break
    print(f'Online users: {online_users}')


@socketio.on('call-user')
def on_call_user(data):
    caller_mobile = data.get('caller_mobile')
    target_mobile = data.get('target_mobile')
    offer = data.get('offer')

    target_sid = online_users.get(target_mobile)
    if target_sid:
        print(
            f'Forwarding call from {caller_mobile} to {target_mobile} at SID {target_sid}')
        emit('incoming-call', {'from': caller_mobile,
             'offer': offer}, room=target_sid)
    else:
        print(f'Call failed: User {target_mobile} is not online.')
        emit('call-failed',
             {'message': f'User {target_mobile} is offline or does not exist.'}, room=request.sid)


@socketio.on('answer-call')
def on_answer_call(data):
    target_mobile = data.get('target_mobile')
    answer = data.get('answer')

    target_sid = online_users.get(target_mobile)
    if target_sid:
        print(f'Forwarding answer to {target_mobile}')
        emit('call-answered', {'answer': answer}, room=target_sid)


@socketio.on('ice-candidate')
def on_ice_candidate(data):
    target_mobile = data.get('target_mobile')
    candidate = data.get('candidate')

    target_sid = online_users.get(target_mobile)
    if target_sid:
        emit('ice-candidate', {'candidate': candidate}, room=target_sid)


@socketio.on('hang-up')
def on_hang_up(data):
    target_mobile = data.get('target_mobile')
    target_sid = online_users.get(target_mobile)
    if target_sid:
        emit('hang-up', {}, room=target_sid)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True, host='0.0.0.0')
