document.addEventListener('DOMContentLoaded', () => {
    // --- Constants and Variables ---
    const socket = io();
    let localStream;
    let peerConnection;
    let remoteMobileNumber;

    const servers = {
        iceServers: [
            {
                urls: ['stun:stun1.l.google.com:19302', 'stun:stun2.l.google.com:19302']
            }
        ]
    };

    // --- DOM Elements ---
    const localVideo = document.getElementById('local-video');
    const remoteVideo = document.getElementById('remote-video');
    const dialerInput = document.getElementById('dialer-input');
    const callBtn = document.getElementById('call-btn');
    const hangupBtn = document.getElementById('hangup-btn');
    const videoCallContainer = document.getElementById('video-call-container');
    const placeholderContainer = document.getElementById('placeholder-container');
    const incomingCallModal = new bootstrap.Modal(document.getElementById('incomingCallModal'));
    const addContactModal = new bootstrap.Modal(document.getElementById('addContactModal'));
    const incomingCallFrom = document.getElementById('incoming-call-from');
    const answerBtn = document.getElementById('answer-btn');
    const declineBtn = document.getElementById('decline-btn');
    const contactsList = document.getElementById('contacts-list');
    const callHistoryList = document.getElementById('call-history-list');
    const saveContactBtn = document.getElementById('save-contact-btn');
    const micBtn = document.getElementById('mic-btn');
    const videoBtn = document.getElementById('video-btn');


    // --- Initialization ---
    const init = async () => {
        try {
            localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
            localVideo.srcObject = localStream;
        } catch (error) {
            console.error('Error accessing media devices.', error);
            alert('Could not access your camera and microphone. Please check permissions and try again.');
        }

        socket.emit('register', { mobile: currentUser.mobile });
        setupDialerListeners();
        setupCallControlListeners();
        loadContacts();
        loadCallHistory();
        setupContactFormListener();
    };

    // --- UI & Event Listeners ---
    function setupDialerListeners() {
        const dialpadButtons = document.querySelectorAll('.dialpad .btn');
        dialpadButtons.forEach(button => {
            button.addEventListener('click', () => {
                dialerInput.value += button.textContent;
            });
        });

        document.getElementById('backspace-btn').addEventListener('click', () => {
            dialerInput.value = dialerInput.value.slice(0, -1);
        });

        callBtn.addEventListener('click', () => {
            const targetMobile = dialerInput.value;
            if (targetMobile && targetMobile !== currentUser.mobile) {
                makeCall(targetMobile);
            }
        });
    }

    function setupCallControlListeners() {
        hangupBtn.addEventListener('click', endCall);
        micBtn.addEventListener('click', toggleAudio);
        videoBtn.addEventListener('click', toggleVideo);
        answerBtn.addEventListener('click', handleAnswer);
        declineBtn.addEventListener('click', handleDecline);
    }
    
    function setupContactFormListener() {
        saveContactBtn.addEventListener('click', async () => {
            const name = document.getElementById('contact-name').value;
            const mobile = document.getElementById('contact-mobile').value;
            if (name && mobile) {
                await addContact(name, mobile);
                addContactModal.hide();
                document.getElementById('add-contact-form').reset();
                loadContacts();
            }
        });
    }

    function toggleAudio() {
        if (!localStream) return;
        const audioTrack = localStream.getAudioTracks()[0];
        audioTrack.enabled = !audioTrack.enabled;
        micBtn.innerHTML = `<span class="material-icons">${audioTrack.enabled ? 'mic' : 'mic_off'}</span>`;
    }

    function toggleVideo() {
        if (!localStream) return;
        const videoTrack = localStream.getVideoTracks()[0];
        videoTrack.enabled = !videoTrack.enabled;
        videoBtn.innerHTML = `<span class="material-icons">${videoTrack.enabled ? 'videocam' : 'videocam_off'}</span>`;
    }

    function showVideoCallUI() {
        videoCallContainer.classList.remove('d-none');
        placeholderContainer.classList.add('d-none');
    }

    function hideVideoCallUI() {
        videoCallContainer.classList.add('d-none');
        placeholderContainer.classList.remove('d-none');
        if(remoteVideo.srcObject){
            remoteVideo.srcObject.getTracks().forEach(track => track.stop());
            remoteVideo.srcObject = null;
        }
    }


    // --- WebRTC Logic ---
    const createPeerConnection = () => {
        peerConnection = new RTCPeerConnection(servers);

        localStream.getTracks().forEach(track => {
            peerConnection.addTrack(track, localStream);
        });

        peerConnection.onicecandidate = event => {
            if (event.candidate) {
                socket.emit('ice-candidate', { 
                    target_mobile: remoteMobileNumber, 
                    candidate: event.candidate 
                });
            }
        };

        peerConnection.ontrack = event => {
            remoteVideo.srcObject = event.streams[0];
        };
    };

    const makeCall = async (targetMobile) => {
        remoteMobileNumber = targetMobile;
        createPeerConnection();
        const offer = await peerConnection.createOffer();
        await peerConnection.setLocalDescription(offer);

        socket.emit('call-user', { 
            caller_mobile: currentUser.mobile, 
            target_mobile: targetMobile,
            offer: offer
        });
        showVideoCallUI();
    };

    const handleAnswer = async () => {
        incomingCallModal.hide();
        createPeerConnection();
        
        const offer = JSON.parse(sessionStorage.getItem('webrtcOffer'));
        await peerConnection.setRemoteDescription(new RTCSessionDescription(offer));
        
        const answer = await peerConnection.createAnswer();
        await peerConnection.setLocalDescription(answer);

        socket.emit('answer-call', { target_mobile: remoteMobileNumber, answer: answer });
        showVideoCallUI();
    };

    const handleDecline = () => {
        // Optionally, send a 'call-declined' signal to the caller
        incomingCallModal.hide();
        sessionStorage.removeItem('webrtcOffer');
    }

    const endCall = () => {
        if (peerConnection) {
            peerConnection.close();
            peerConnection = null;
        }
        socket.emit('hang-up', { target_mobile: remoteMobileNumber });
        remoteMobileNumber = null;
        hideVideoCallUI();
        logCallHistory('outgoing', 0); // Assuming duration calculation is needed
        loadCallHistory();
    };
    

    // --- Socket.IO Listeners ---
    socket.on('incoming-call', data => {
        remoteMobileNumber = data.from;
        incomingCallFrom.textContent = data.from;
        sessionStorage.setItem('webrtcOffer', JSON.stringify(data.offer));
        incomingCallModal.show();
    });

    socket.on('call-answered', async data => {
        await peerConnection.setRemoteDescription(new RTCSessionDescription(data.answer));
    });

    socket.on('ice-candidate', async data => {
        if (peerConnection && data.candidate) {
            try {
                 await peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
            } catch (e) {
                console.error('Error adding received ice candidate', e);
            }
        }
    });

    socket.on('hang-up', () => {
        if (peerConnection) {
            peerConnection.close();
            peerConnection = null;
        }
        remoteMobileNumber = null;
        hideVideoCallUI();
    });
    
    socket.on('call-failed', data => {
        alert(data.message);
        endCall();
    });


    // --- API Calls & Data Management ---
    async function loadContacts() {
        const response = await fetch('/api/contacts');
        const contacts = await response.json();
        contactsList.innerHTML = '';
        if (contacts.length === 0) {
            contactsList.innerHTML = '<li class="list-group-item text-muted">No contacts yet.</li>';
        }
        contacts.forEach(contact => {
            const li = document.createElement('li');
            li.className = 'list-group-item d-flex justify-content-between align-items-center';
            li.innerHTML = `
                <div>
                    <strong>${contact.name}</strong>
                    <div class="text-muted small">${contact.mobile}</div>
                </div>
                <div class="actions">
                    <button class="btn btn-sm btn-success call-contact-btn" data-mobile="${contact.mobile}"><span class="material-icons">call</span></button>
                    <button class="btn btn-sm btn-danger delete-contact-btn" data-id="${contact.id}"><span class="material-icons">delete</span></button>
                </div>
            `;
            contactsList.appendChild(li);
        });

        document.querySelectorAll('.call-contact-btn').forEach(btn => {
            btn.addEventListener('click', (e) => makeCall(e.currentTarget.dataset.mobile));
        });
        document.querySelectorAll('.delete-contact-btn').forEach(btn => {
            btn.addEventListener('click', (e) => deleteContact(e.currentTarget.dataset.id));
        });
    }

    async function addContact(name, mobile) {
        await fetch('/api/contacts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, mobile })
        });
    }

    async function deleteContact(id) {
        if(confirm('Are you sure you want to delete this contact?')) {
            await fetch(`/api/contacts/${id}`, { method: 'DELETE' });
            loadContacts();
        }
    }

    async function loadCallHistory() {
        const response = await fetch('/api/call-history');
        const history = await response.json();
        callHistoryList.innerHTML = '';
        if (history.length === 0) {
            callHistoryList.innerHTML = '<li class="list-group-item text-muted">No call history.</li>';
        }
        history.forEach(log => {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            const date = new Date(log.timestamp).toLocaleString();
            const icon = log.status.includes('outgoing') ? 'call_made' : 'call_received';
            li.innerHTML = `
                <div class="d-flex w-100 justify-content-between">
                    <h6 class="mb-1"><span class="material-icons align-middle me-2">${icon}</span>${log.receiver_mobile}</h6>
                    <small>${date}</small>
                </div>
                <p class="mb-1">Status: ${log.status}, Duration: ${log.duration}s</p>
            `;
            callHistoryList.appendChild(li);
        });
    }

    async function logCallHistory(status, duration) {
        await fetch('/api/call-history', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                caller_mobile: currentUser.mobile,
                receiver_mobile: remoteMobileNumber,
                status: status,
                duration: duration
            })
        });
    }

    // --- Start the application ---
    init();
});