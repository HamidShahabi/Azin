document.addEventListener('DOMContentLoaded', function () {
    const chatMessages = document.getElementById('chat-messages');
    const messageInput = document.getElementById('message-input');
    const sendMessageButton = document.getElementById('send-message');
    const fileInput = document.getElementById('file-input');
    const roomName = "{{ room_name }}";
    let socket = null;

    // Open the WebSocket connection
    socket = new WebSocket(`ws://${window.location.host}/ws/chat/${roomName}/`);

    // Event listener for connection errors
    socket.onerror = function (error) {
        console.error("WebSocket Error: ", error);
        alert("An error occurred while connecting to the chat server.");
    };

    // Event listener for connection closure
    socket.onclose = function (event) {
        console.error("Chat socket closed unexpectedly: ", event);
        if (event.wasClean) {
            console.log(`Connection closed cleanly, code=${event.code}, reason=${event.reason}`);
        } else {
            console.error("Connection closed with an error or unexpectedly.");
        }
        alert("The chat connection was closed. Please refresh the page or try again later.");
    };

    // Event listener for incoming messages
    socket.onmessage = function (e) {
        const data = JSON.parse(e.data);
        const message = data['message'];
        chatMessages.innerHTML += `<div>${message}</div>`;
        chatMessages.scrollTop = chatMessages.scrollHeight;
    };

    // Event listener for connection success
    socket.onopen = function () {
        console.log("WebSocket connection established successfully.");
    };

    // Send message on button click
    sendMessageButton.addEventListener('click', function () {
        const message = messageInput.value;
        const file = fileInput.files[0];
        if (message && socket) {
            socket.send(JSON.stringify({
                'message': message
            }));
            messageInput.value = '';
        }
        if (file && socket) {
            const reader = new FileReader();
            reader.onload = function (e) {
                socket.send(JSON.stringify({
                    'file': e.target.result,
                    'filename': file.name
                }));
            };
            reader.readAsDataURL(file);
        }
    });
});