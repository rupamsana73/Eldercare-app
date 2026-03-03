console.log("Elderly Medicine Care App Loaded");

/* Bottom sheet open */
function openSheet() {
    const sheet = document.getElementById('sheet');
    if (sheet) sheet.classList.add('show');
}

/* Bottom sheet close */
function closeSheet() {
    const sheet = document.getElementById('sheet');
    if (sheet) sheet.classList.remove('show');
}

function openPopup(priority, name='', phone='') {
    document.getElementById('popupPriority').value = priority;
    document.getElementById('popupName').value = name;
    document.getElementById('popupPhone').value = phone;
    document.getElementById('popupBg').classList.add('show');
}

function closePopup() {
    document.getElementById('popupBg').classList.remove('show');
}

// Attach popup to edit buttons
document.querySelectorAll('.edit-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const priority = btn.dataset.priority;
        const name = btn.dataset.name || '';
        const phone = btn.dataset.phone || '';

        openPopup(priority, name, phone);
    });
});
function showToast() {
    const toast = document.getElementById('toast');
    if (!toast) return;

    toast.classList.add('show');

    setTimeout(() => {
        toast.classList.remove('show');
    }, 2500);
}



function startEmergencyCall(p1, p2 = '') {
    if (!p1) {
        alert("No emergency contact added");
        return;
    }

    window.location.href = "tel:" + p1;

    if (p2) {
        setTimeout(() => {
            window.location.href = "tel:" + p2;
        }, 20000);
    }
}


function callWithFallback(primary, secondary) {
    window.location.href = "tel:" + primary;

    setTimeout(() => {
        if (secondary) {
            window.location.href = "tel:" + secondary;
            setTimeout(() => sendSMS(primary, secondary), 2000);
        } else {
            sendSMS(primary);
        }
    }, 20000); // 20 sec fallback
}

function sendSMS(p1, p2 = null) {
    const msg = encodeURIComponent(
        "EMERGENCY! I need urgent help. Please contact me immediately."
    );

    if (p1) {
        window.location.href = `sms:${p1}?body=${msg}`;
    }

    if (p2) {
        setTimeout(() => {
            window.location.href = `sms:${p2}?body=${msg}`;
        }, 1000);
    }
}

function getLiveLocation(callback) {
    if (!navigator.geolocation) {
        alert("Location not supported");
        return;
    }

    navigator.geolocation.getCurrentPosition(
        position => {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;
            callback(lat, lng);
        },
        error => {
            alert("Please enable location access");
        },
        { enableHighAccuracy: true }
    );
}

function openGoogleMap(lat, lng) {
    const url = `https://www.google.com/maps?q=${lat},${lng}`;
    window.open(url, "_blank");
}


function sendEmergencySMSWithLocation(phone) {
    getLiveLocation((lat, lng) => {
        const mapLink = `https://maps.google.com/?q=${lat},${lng}`;
        const msg = encodeURIComponent(
            `EMERGENCY! I need help.\nMy location:\n${mapLink}`
        );
        window.location.href = `sms:${phone}?body=${msg}`;
    });
}


function sendLocationSMS(phone) {
    if (!phone) {
        alert("No emergency contact added");
        return;
    }

    if (!navigator.geolocation) {
        alert("Location not supported on this device");
        return;
    }

    navigator.geolocation.getCurrentPosition(
        position => {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;

            const mapLink = `https://www.google.com/maps?q=${lat},${lng}`;
            const msg = encodeURIComponent(
                "EMERGENCY! I need help.\nMy location:\n" + mapLink
            );

            window.location.href = `sms:${phone}?body=${msg}`;
        },
        error => {
            alert("Please allow location access");
        },
        { enableHighAccuracy: true }
    );
}





function toggleMenu() {
  const menu = document.getElementById("menuBox");
  if (!menu) return;

  menu.style.display =
    menu.style.display === "block" ? "none" : "block";
}

document.addEventListener("DOMContentLoaded", function () {

  const frequency = document.getElementById("frequency");
  const dailyBox = document.getElementById("dailyBox");
  const weeklyBox = document.getElementById("weeklyBox");
  const doseSelect = document.getElementById("dose_per_day");
  const dailyTimes = document.getElementById("dailyTimes");

  function clearDailyTimes() {
    dailyTimes.innerHTML = "";
  }

  function renderDailyTimes(count) {
    clearDailyTimes();

    for (let i = 1; i <= count; i++) {
      dailyTimes.innerHTML += `
        <div class="form-group">
          <label>Time ${i}</label>
          <input type="time" name="times[]" class="input" required>
        </div>
      `;
    }
  }

  function handleFrequencyChange() {
    const value = frequency.value;

    if (value === "daily") {
      dailyBox.style.display = "block";
      weeklyBox.style.display = "none";

      renderDailyTimes(parseInt(doseSelect.value || 1));

    } else {
      dailyBox.style.display = "none";
      weeklyBox.style.display = "block";
      clearDailyTimes();
    }
  }

  frequency.addEventListener("change", handleFrequencyChange);

  doseSelect.addEventListener("change", function () {
    if (frequency.value === "daily") {
      renderDailyTimes(parseInt(this.value));
    }
  });

  // INITIAL LOAD
  handleFrequencyChange();
});

  // 🔹 WEEKLY / CUSTOM DAYS HANDLE
  const dayChecks = document.querySelectorAll('#weeklyBox input[type="checkbox"]');
  const daysHidden = document.getElementById('days_of_week');

  function updateDays() {
    const selected = [];
    dayChecks.forEach(c => {
      if (c.checked) selected.push(c.value);
    });
    daysHidden.value = selected.join(',');
  }

  dayChecks.forEach(c => c.addEventListener('change', updateDays));


  document.addEventListener("DOMContentLoaded", () => {
  const toast = document.getElementById("toast");
  if (!toast) return;

  // show
  toast.classList.add("show");

  // auto hide after 2s
  setTimeout(() => {
    toast.classList.remove("show");
  }, 2000);
});


function openEditModal(btn){
  const id = btn.dataset.id;
  fetch(`/medicine/edit/${id}/`)
    .then(r => r.text())
    .then(html => {
      document.getElementById('edit-form-body').innerHTML = html;
      document.getElementById('editModal').style.display = 'flex';
      document.getElementById('editForm').action = `/medicine/edit/${id}/`;
    });
}

function closeEditModal(){
  document.getElementById('editModal').style.display = 'none';
}

document.addEventListener('submit', function(e){
  if(e.target.id === 'editForm'){
    e.preventDefault();
    fetch(e.target.action, { method:'POST', body:new FormData(e.target) })
      .then(r=>r.json())
      .then(d=>{
        if(d.success){
          closeEditModal();
          window.location.reload();
        }
      });
  }
});


function addTimeInput(){
  const box = document.querySelector('#editForm .form-group:last-of-type');
  if (!box) return;

  const input = document.createElement('input');
  input.type = 'time';
  input.name = 'times[]';
  input.className = 'input';
  box.appendChild(input);
}

function addEditTime(){
  const box = document.getElementById("edit-times-box");
  if (!box) return;

  const input = document.createElement("input");
  input.type = "time";
  input.name = "times[]";
  input.className = "input";

  box.appendChild(input);
}



function addEditTime(){
  const box = document.getElementById("edit-times-box");
  if (!box) return;

  const input = document.createElement("input");
  input.type = "time";
  input.name = "times[]";
  input.className = "input";

  box.appendChild(input);
}


function toggleStatus(btn){
  const medId = btn.dataset.id;
  const csrf = document.querySelector('#csrf-form input').value;

  fetch('/medicine/toggle/', {
    method: 'POST',
    headers: {
      'X-CSRFToken': csrf,
      'Content-Type': 'application/x-www-form-urlencoded'
    },
    body: `medicine_id=${medId}`
  })
  .then(r => r.json())
  .then(d => {
    if(d.success){
      btn.outerHTML = '<span class="status taken">✅ Taken</span>';
      showToast('Good job! Medicine taken');
    }
  });
}

function showToast(msg){
  let t = document.createElement('div');
  t.id = 'toast';
  t.innerText = msg;
  document.body.appendChild(t);
  setTimeout(()=>t.remove(), 2000);
}


function openFocusCard(card){
  const overlay = document.getElementById("focusOverlay");
  const box = document.getElementById("focusContent");

  // clone card content
  box.innerHTML = card.innerHTML;

  overlay.style.display = "flex";
  document.body.style.overflow = "hidden";
}

function closeFocus(){
  document.getElementById("focusOverlay").style.display = "none";
  document.body.style.overflow = "";
}


function openMedicineModal(medName, timesData) {
  document.getElementById("modalMedName").innerText = medName;

  const box = document.getElementById("modalTimes");
  box.innerHTML = "";

  timesData.forEach(item => {
    const row = document.createElement("div");
    row.className = "time-row " + (item.status || "");

    row.innerHTML = `
      <div>
        <strong>${item.time}</strong><br>
        <small>${item.status || "upcoming"}</small>
      </div>
      <div class="time-actions">
        <button class="btn-taken">Taken</button>
        <button class="btn-not">Not</button>
      </div>
    `;

    box.appendChild(row);
  });

  document.getElementById("medicineModal").classList.add("show");
}

function closeMedicineModal() {
  document.getElementById("medicineModal").classList.remove("show");
}



