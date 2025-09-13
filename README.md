# WebRTC Video Calling App

This is a simple video calling application built with Python, Flask, and WebRTC. It allows users to sign up, log in, manage contacts, and make peer-to-peer video calls directly in the browser.

## Features

- **User Authentication**: Secure sign-up and login system using mobile number and password.
- **WebRTC Video Calls**: Real-time, peer-to-peer video and audio communication.
- **Dialer**: Call any registered user via their mobile number.
- **Contact Management**: Save, view, and delete contacts.
- **Call History**: Automatically logs outgoing and incoming calls.
- **Real-time Signaling**: Uses Flask-SocketIO for WebRTC signaling (offers, answers, ICE candidates).
- **Modern UI**: Clean and responsive user interface built with Bootstrap 5.

## Tech Stack

**Backend:**
- Python 3
- Flask & Flask-SocketIO
- Flask-SQLAlchemy (with SQLite3)
- Flask-Login for session management
- Flask-Bcrypt for password hashing
- Gunicorn (recommended for production)

**Frontend:**
- HTML5 & CSS3
- JavaScript (ES6+)
- Bootstrap 5
- Socket.IO Client
- Google Material Icons

## How It Works

The application uses a Flask server as a signaling server for the WebRTC connections. When a user (Alice) wants to call another user (Bob):

1.  **Login & Registration**: Both users must have an account and be logged in. Upon login, their browser connects to the Flask-SocketIO server and registers their mobile number against their unique session ID (SID).
2.  **Initiating a Call**: Alice enters Bob's mobile number into the dialer and clicks the call button.
3.  **Offer Creation**: Alice's browser creates a WebRTC "offer" (a session description protocol or SDP) and sends it to the Flask server, specifying Bob's mobile number as the target.
4.  **Signaling**: The server looks up Bob's SID and forwards Alice's offer to him.
5.  **Incoming Call**: Bob's browser receives the offer and displays an "Incoming Call" notification.
6.  **Answer Creation**: If Bob answers, his browser creates an "answer" (another SDP) and sends it back to the server, targeted at Alice.
7.  **Connection Establishment**: The server forwards the answer to Alice. Now both browsers have exchanged session descriptions.
8.  **ICE Candidates**: To traverse NATs and firewalls, the browsers exchange network information (IP addresses, ports) via ICE candidates, which are also relayed through the signaling server.
9.  **Peer-to-Peer Connection**: Once the ICE process is complete, a direct peer-to-peer connection is established between Alice and Bob, and the video/audio streams are transmitted directly between them, not through the server.
10. **Hang Up**: When either user hangs up, a signal is sent to the other user to terminate the session.

## How to Run the App

### Prerequisites

- Python 3.6+
- A modern web browser that supports WebRTC (Chrome, Firefox, Safari, Edge).

### 1. Clone the Repository

```bash
git clone <repository-url>
cd <repository-directory>
```

### 2. Create a Virtual Environment

It's highly recommended to use a virtual environment.

**On macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows:**
```bash
python -m venv venv
.\venv\Scripts\activate
```

### 3. Install Dependencies

Install all the required Python packages using the `requirements.txt` file.

```bash
pip install -r requirements.txt
```

### 4. Run the Application

Start the Flask development server.

```bash
python app.py
```

You should see output indicating that the server is running, typically on `http://127.0.0.1:5000` or `http://0.0.0.0:5000`.

### 5. Using the App

1.  **Open Two Browser Windows/Tabs**: To test the video call functionality, you need two different clients. Open the application URL (e.g., `http://127.0.0.1:5000`) in two separate browser tabs or windows.
2.  **Create Two Accounts**: In each window, sign up with a different name and mobile number (e.g., User A with `1111111111` and User B with `2222222222`).
3.  **Log In**: Log in to each account in its respective window.
4.  **Make a Call**: From User A's window, enter User B's mobile number (`2222222222`) in the dialer and click the call button.
5.  **Accept the Call**: In User B's window, an incoming call modal will appear. Click "Answer".
6.  **Start Calling**: The video streams should now appear, and the call is connected!

**Note on Permissions**: Your browser will ask for permission to use your camera and microphone. You must allow this for the application to work.

**Note on HTTPS**: For WebRTC to work on a live server (not `localhost`), your site must be served over HTTPS. The `getUserMedia()` API is restricted to secure origins.