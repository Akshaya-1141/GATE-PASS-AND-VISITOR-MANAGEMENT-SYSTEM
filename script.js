// Webcam Setup
const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const context = canvas.getContext('2d');
let capturedImage = null;

navigator.mediaDevices.getUserMedia({ video: true })
    .then(stream => { video.srcObject = stream; })
    .catch(err => { console.error("Camera Error:", err); });

document.getElementById('snap-btn').addEventListener('click', () => {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    context.drawImage(video, 0, 0);
    capturedImage = canvas.toDataURL('image/jpeg');
    document.getElementById('photo-preview').src = capturedImage;
    document.getElementById('photo-preview').style.display = 'block';
    video.style.display = 'none';
});

// Helper Function: Validate Mobile Number
function isValidMobile(mobile) {
    // Check if it is a number and exactly 10 digits
    const regex = /^[0-9]{10}$/;
    return regex.test(mobile);
}

// Check Visitor
async function checkVisitor() {
    const mobile = document.getElementById('mobile').value;
    const msgElement = document.getElementById('status-msg');

    // Clear previous messages
    msgElement.innerText = "";

    // 1. Validation Step
    if (mobile.length === 0) return; // Do nothing if empty
    
    if (!isValidMobile(mobile)) {
        msgElement.innerText = "Error: Mobile number must be exactly 10 digits.";
        msgElement.style.color = "red";
        return;
    }

    // 2. API Call
    const res = await fetch(`/api/check_visitor?mobile=${mobile}`);
    const data = await res.json();

    if (data.found) {
        document.getElementById('name').value = data.name;
        document.getElementById('designation').value = data.designation;
        document.getElementById('company').value = data.company;
        document.getElementById('vehicle').value = data.vehicle || "";
        msgElement.innerText = "Visitor Found! Details Autofilled.";
        msgElement.style.color = "green";
    } else {
        msgElement.innerText = "New Visitor";
        msgElement.style.color = "blue";
    }
}

// Generate Pass
async function generatePass() {
    const mobile = document.getElementById('mobile').value;

    // 1. Strict Validation before generating pass
    if (!isValidMobile(mobile)) {
        alert("Invalid Mobile Number! It must be exactly 10 digits.");
        document.getElementById('mobile').focus();
        return;
    }

    // Collect Data
    const data = {
        mobile: mobile,
        name: document.getElementById('name').value,
        designation: document.getElementById('designation').value,
        company: document.getElementById('company').value,
        vehicle_number: document.getElementById('vehicle').value,
        laptop: document.getElementById('laptop').value || "None",
        to_meet: document.getElementById('to_meet').value,
        department: document.getElementById('department').value,
        image: capturedImage
    };

    if (!data.name || !data.to_meet || !capturedImage) {
        alert("Please fill Name, To Meet, and Capture Photo.");
        return;
    }

    const response = await fetch('/api/entry', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    });

    const result = await response.json();

    if (result.status === 'success') {
        // Fill Ticket
        document.getElementById('t-pass-id').innerText = result.pass_id;
        document.getElementById('t-date').innerText = result.date;
        document.getElementById('t-time').innerText = result.in_time;
        
        document.getElementById('t-name').innerText = data.name;
        document.getElementById('t-designation').innerText = data.designation;
        document.getElementById('t-company').innerText = data.company;
        document.getElementById('t-mobile').innerText = data.mobile;
        document.getElementById('t-laptop').innerText = data.laptop;
        document.getElementById('t-vehicle').innerText = data.vehicle_number;
        
        document.getElementById('t-meet').innerText = data.to_meet;
        document.getElementById('t-dept').innerText = data.department;

        const ticketPhoto = document.getElementById('t-photo');
        ticketPhoto.src = result.photo;

        ticketPhoto.onload = function() {
            window.print();
            setTimeout(() => { location.reload(); }, 500);
        };
    } else {
        alert("Error: " + result.message);
    }
}

async function markExit() {
    const mobile = document.getElementById('exit-mobile').value;
    
    if (!isValidMobile(mobile)) {
        alert("Please enter a valid 10-digit mobile number.");
        return;
    }

    const res = await fetch('/api/exit', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ mobile })
    });
    const data = await res.json();
    if (data.status === 'success') {
        alert(`Out Time Recorded: ${data.out_time}`);
        document.getElementById('exit-mobile').value = ""; // Clear field
    }
    else {
        alert(data.message);
    }
}   