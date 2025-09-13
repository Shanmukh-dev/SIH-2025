document.addEventListener('DOMContentLoaded', () => {
    const socket = io();

    const localVideo = document.getElementById('localVideo');
    const remoteVideo = document.getElementById('remoteVideo');
    const dialerInput = document.getElementById('dialerInput');
    const startCallButton = document.getElementById('startCallButton');
    const endCallBtn = document.getElementById('endCallBtn');
    const acceptCallBtn = document.getElementById('acceptCallBtn');
    const declineCallBtn = document.getElementById('declineCallBtn');
    const toggleAudioBtn = document.getElementById('toggleAudioBtn');
    const toggleVideoBtn = document.getElementById('toggleVideoBtn');
    const callStatusText = document.getElementById('callStatusText');
    const remoteUserDisplay = document.getElementById('remoteUserDisplay');
    const incomingCallButtons = document.getElementById('incomingCallButtons');
    const callModal = new bootstrap.Modal(document.getElementById('callModal'), { keyboard: false, backdrop: 'static' });

    let peerConnection;
    let localStream;
    let currentCallerNumber = null; // Stores number of the user initiating the current incoming call
    let currentCallTargetNumber = null; // Stores number of the user being called/currently in call with

    const iceServers = {
        'iceServers': [
            { 'urls': 'stun:stun.l.google.com:19302' },
            // Add TURN servers for production if needed
            // { 'urls': 'turn:your_turn_server_ip:3478', 'username': 'user', 'credential': 'password' }
        ]
    };

    // --- Utility Functions ---
    function showAlert(message, type = 'info') {
        const alertPlaceholder = document.querySelector('main .container');
        const wrapper = document.createElement('div');
        wrapper.innerHTML = [
            `<div class="alert alert-${type} alert-dismissible fade show" role="alert">`,
            `   <div>${message}</div>`,
            '   <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>',
            '</div>'
        ].join('');
        alertPlaceholder.prepend(wrapper);
        setTimeout(() => wrapper.remove(), 5000); // Auto-dismiss after 5 seconds
    }

    function resetCallState() {
        if (localStream) {
            localStream.getTracks().forEach(track => track.stop());
        }
        if (peerConnection) {
            peerConnection.close();
        }
        localStream = null;
        peerConnection = null;
        localVideo.srcObject = null;
        remoteVideo.srcObject = null;
        currentCallerNumber = null;
        currentCallTargetNumber = null;

        callModal.hide();
        callStatusText.textContent = 'Connecting...';
        remoteUserDisplay.textContent = '';
        incomingCallButtons.style.display = 'none';
        document.getElementById('startCallButton').style.display = 'block'; // Show call button after call ends
        toggleAudioBtn.innerHTML = '<i class="material-icons">mic</i>';
        toggleVideoBtn.innerHTML = '<i class="material-icons">videocam</i>';
        toggleAudioBtn.classList.remove('btn-secondary');
        toggleVideoBtn.classList.remove('btn-secondary');
        toggleAudioBtn.classList.add('btn-secondary'); // Reset to active visual state
        toggleVideoBtn.classList.add('btn-secondary');
    }

    // --- WebRTC Functions ---
    async function startLocalStream() {
        try {
            localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
            localVideo.srcObject = localStream;
            return true;
        } catch (error) {
            console.error('Error accessing media devices.', error);
            showAlert('Could not access your camera and microphone. Please ensure permissions are granted.', 'danger');
            return false;
        }
    }

    function createPeerConnection() {
        peerConnection = new RTCPeerConnection(iceServers);

        localStream.getTracks().forEach(track => {
            peerConnection.addTrack(track, localStream);
        });

        peerConnection.ontrack = (event) => {
            console.log('Received remote stream', event.streams[0]);
            if (remoteVideo.srcObject !== event.streams[0]) {
                remoteVideo.srcObject = event.streams[0];
                callStatusText.textContent = 'Call Connected';
                incomingCallButtons.style.display = 'none'; // Hide accept/decline buttons once call connected
            }
        };

        peerConnection.onicecandidate = (event) => {
            if (event.candidate) {
                console.log('Sending ICE candidate:', event.candidate);
                socket.emit('ice_candidate', {
                    target_number: currentCallTargetNumber, // Send to the person we are calling or who called us
                    candidate: event.candidate,
                    sender_number: '{{ user.mobile_number }}'
                });
            }
        };

        peerConnection.oniceconnectionstatechange = (event) => {
            console.log('ICE connection state:', peerConnection.iceConnectionState);
            if (peerConnection.iceConnectionState === 'disconnected' || peerConnection.iceConnectionState === 'failed') {
                showAlert('Call disconnected unexpectedly.', 'warning');
                endCall();
            }
        };

        return peerConnection;
    }

    async function makeCall(targetNumber) {
        currentCallTargetNumber = targetNumber;
        if (!await startLocalStream()) return;
        callModal.show();
        remoteUserDisplay.textContent = targetNumber;
        callStatusText.textContent = 'Calling...';
        document.getElementById('startCallButton').style.display = 'none'; // Hide call button when initiating

        peerConnection = createPeerConnection();

        try {
            const offer = await peerConnection.createOffer();
            await peerConnection.setLocalDescription(offer);
            console.log('Sending offer:', offer);
            socket.emit('call_user', { target_number: targetNumber, offer: offer });
        } catch (error) {
            console.error('Error creating offer:', error);
            showAlert('Failed to initiate call.', 'danger');
            endCall();
        }
    }

    async function handleIncomingCall(callerNumber, offer) {
        currentCallerNumber = callerNumber;
        currentCallTargetNumber = callerNumber;
        if (!await startLocalStream()) return;
        callModal.show();
        remoteUserDisplay.textContent = callerNumber;
        callStatusText.textContent = `Incoming Call from ${callerNumber}`;
        incomingCallButtons.style.display = 'block'; // Show accept/decline buttons
        document.getElementById('startCallButton').style.display = 'none'; // Hide call button when receiving

        peerConnection = createPeerConnection();

        try {
            await peerConnection.setRemoteDescription(new RTCSessionDescription(offer));
            console.log('Received offer, creating answer.');
        } catch (error) {
            console.error('Error setting remote description for incoming call:', error);
            showAlert('Failed to process incoming call.', 'danger');
            endCall();
        }
    }

    async function acceptCall() {
        try {
            const answer = await peerConnection.createAnswer();
            await peerConnection.setLocalDescription(answer);
            console.log('Sending answer:', answer);
            socket.emit('answer_call', { caller_number: currentCallerNumber, answer: answer });
            callStatusText.textContent = 'Connecting...';
            incomingCallButtons.style.display = 'none';
        } catch (error) {
            console.error('Error creating answer:', error);
            showAlert('Failed to accept call.', 'danger');
            endCall();
        }
    }

    function rejectCall() {
        socket.emit('reject_call', { caller_number: currentCallerNumber });
        showAlert(`Call from ${currentCallerNumber} rejected.`, 'info');
        endCall();
    }

    function endCall() {
        if (currentCallTargetNumber) {
            socket.emit('end_call', { target_number: currentCallTargetNumber });
        }
        resetCallState();
    }

    // --- Event Listeners ---
    startCallButton.addEventListener('click', () => {
        const targetNumber = dialerInput.value.trim();
        if (targetNumber) {
            makeCall(targetNumber);
        } else {
            showAlert('Please enter a mobile number to call.', 'warning');
        }
    });

    acceptCallBtn.addEventListener('click', acceptCall);
    declineCallBtn.addEventListener('click', rejectCall);
    endCallBtn.addEventListener('click', endCall);

    toggleAudioBtn.addEventListener('click', () => {
        if (localStream) {
            const audioTrack = localStream.getAudioTracks()[0];
            if (audioTrack) {
                audioTrack.enabled = !audioTrack.enabled;
                toggleAudioBtn.innerHTML = audioTrack.enabled ? '<i class="material-icons">mic</i>' : '<i class="material-icons">mic_off</i>';
                toggleAudioBtn.classList.toggle('btn-secondary');
                toggleAudioBtn.classList.toggle('btn-warning');
            }
        }
    });

    toggleVideoBtn.addEventListener('click', () => {
        if (localStream) {
            const videoTrack = localStream.getVideoTracks()[0];
            if (videoTrack) {
                videoTrack.enabled = !videoTrack.enabled;
                toggleVideoBtn.innerHTML = videoTrack.enabled ? '<i class="material-icons">videocam</i>' : '<i class="material-icons">videocam_off</i>';
                toggleVideoBtn.classList.toggle('btn-secondary');
                toggleVideoBtn.classList.toggle('btn-warning');
            }
        }
    });

    // Event listener for calling contacts directly from the list
    document.querySelectorAll('.call-contact-btn').forEach(button => {
        button.addEventListener('click', function() {
            const contactNumber = this.getAttribute('data-number');
            makeCall(contactNumber);
        });
    });


    // --- Socket.IO Events ---
    socket.on('connect', () => {
        console.log('Connected to Socket.IO server.');
        // The server will handle sending 'unauthorized' if session is not valid
    });

    socket.on('disconnect', () => {
        console.log('Disconnected from Socket.IO server.');
        showAlert('Disconnected from the call service.', 'danger');
        resetCallState();
    });

    socket.on('unauthorized', (data) => {
        console.error('Unauthorized:', data.message);
        showAlert(data.message + ' Redirecting to login...', 'danger');
        // Optionally redirect to login or show a prominent message
        setTimeout(() => window.location.href = '/login', 3000);
    });

    socket.on('user_status', (data) => {
        console.log(`User ${data.mobile_number} is ${data.status}`);
        const statusIndicator = document.getElementById(`status-${data.mobile_number.replace('+', '')}`);
        if (statusIndicator) {
            if (data.status === 'online') {
                statusIndicator.classList.add('online');
                statusIndicator.setAttribute('data-bs-original-title', 'Online');
            } else {
                statusIndicator.classList.remove('online');
                statusIndicator.setAttribute('data-bs-original-title', 'Offline');
            }
            // Update tooltip immediately
            const tooltip = bootstrap.Tooltip.getInstance(statusIndicator);
            if (tooltip) {
                tooltip.hide();
                tooltip.dispose();
            }
            new bootstrap.Tooltip(statusIndicator);
        }
    });

    socket.on('online_users_list', (users) => {
        console.log('Online users:', users);
        users.forEach(user => {
            const statusIndicator = document.getElementById(`status-${user.mobile_number.replace('+', '')}`);
            if (statusIndicator) {
                if (user.status === 'online') {
                    statusIndicator.classList.add('online');
                    statusIndicator.setAttribute('data-bs-original-title', 'Online');
                } else {
                    statusIndicator.classList.remove('online');
                    statusIndicator.setAttribute('data-bs-original-title', 'Offline');
                }
                const tooltip = bootstrap.Tooltip.getInstance(statusIndicator);
                if (tooltip) {
                    tooltip.hide();
                    tooltip.dispose();
                }
                new bootstrap.Tooltip(statusIndicator);
            }
        });
    });

    socket.on('call_initiated', (data) => {
        console.log('Call initiated message:', data.message);
        callStatusText.textContent = `Calling ${data.target_number}...`;
        showAlert(`Calling ${data.target_number}...`, 'info');
    });

    socket.on('incoming_call', async (data) => {
        console.log('Incoming call from:', data.caller_number);
        showAlert(`Incoming call from ${data.caller_number}`, 'info');
        await handleIncomingCall(data.caller_number, data.offer);
    });

    socket.on('call_accepted', async (data) => {
        console.log('Call accepted by:', data.answerer_number);
        showAlert(`Call accepted by ${data.answerer_number}. Connecting...`, 'success');
        try {
            await peerConnection.setRemoteDescription(new RTCSessionDescription(data.answer));
            callStatusText.textContent = 'Call Connected';
        } catch (error) {
            console.error('Error setting remote description for accepted call:', error);
            showAlert('Failed to establish call connection.', 'danger');
            endCall();
        }
    });

    socket.on('call_rejected', (data) => {
        console.log('Call rejected by:', data.rejecter_number);
        showAlert(`Call rejected by ${data.rejecter_number}.`, 'warning');
        endCall();
    });

    socket.on('call_failed', (data) => {
        console.error('Call failed:', data.message);
        showAlert(`Call failed: ${data.message}`, 'danger');
        endCall();
    });

    socket.on('call_ended', (data) => {
        console.log('Call ended by:', data.ender_number);
        const message = data.ender_number === '{{ user.mobile_number }}' ? 'Call ended.' : `Call ended by ${data.ender_number}.`;
        showAlert(message, 'info');
        endCall();
    });

    socket.on('ice_candidate', async (data) => {
        console.log('Received ICE candidate from:', data.sender_number, data.candidate);
        try {
            if (peerConnection && data.candidate) {
                await peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
            }
        } catch (error) {
            console.error('Error adding received ICE candidate:', error);
        }
    });
});
