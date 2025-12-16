const tg = window.Telegram.WebApp;
tg.expand();

const API_URL = "https://super-test-bot.onrender.com"; 

let questions = [];
let testCode = "";
let userId = "";
let remainingSeconds = 0;
let timerInterval;

const urlParams = new URLSearchParams(window.location.search);
testCode = urlParams.get('code');
userId = urlParams.get('userId');

// ANTI-CHEAT: O'ng tugma va belgilashni taqiqlash
document.addEventListener('contextmenu', event => event.preventDefault());
document.addEventListener('keydown', event => {
    if (event.key == "F12" || (event.ctrlKey && event.key == "u") || (event.ctrlKey && event.key == "s")) {
        event.preventDefault();
    }
});

document.addEventListener("DOMContentLoaded", () => {
    if (!testCode) return document.body.innerHTML = "<h3>Xatolik: Kod yo'q</h3>";
    loadTest();
});

function loadTest() {
    fetch(`${API_URL}/api/get_test?code=${testCode}&userId=${userId}`)
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                let msg = "Xatolik!";
                if (data.error === "expired") msg = "Vaqt tugagan!";
                alert(msg);
                tg.close();
                return;
            }

            // RELOAD BO'LGANDA NATIJA KO'RSATISH
            if (data.status === "finished") {
                showResultScreen(data.score, data.total, data.name);
                return;
            }
            
            // TESTNI BOSHLASH
            document.getElementById("test-title").innerText = data.name;
            
            // Vaqtni tiklash (Lokal)
            const savedEndTime = localStorage.getItem(`end_${testCode}_${userId}`);
            const now = Math.floor(Date.now() / 1000);
            if (savedEndTime) {
                remainingSeconds = parseInt(savedEndTime) - now;
            } else {
                remainingSeconds = data.remaining_seconds;
                localStorage.setItem(`end_${testCode}_${userId}`, (now + remainingSeconds).toString());
            }

            questions = shuffleArray(data.questions).map(q => {
                let optionsObj = q.a.map((opt, i) => ({ text: opt, originalIndex: i }));
                return { q: q.q, options: shuffleArray(optionsObj), correctIndex: q.c };
            });

            document.getElementById("login-screen").classList.remove("hidden");
            startTimer();
        })
        .catch(err => alert("Tarmoq xatosi!"));
}

function startQuiz() {
    const name = document.getElementById("student_name").value;
    if (!name) { tg.showAlert("Ism kiriting!"); return; }
    document.getElementById("login-screen").classList.add("hidden");
    document.getElementById("quiz-screen").classList.remove("hidden");
    renderQuestions();
}

function renderQuestions() {
    const container = document.getElementById("questions-container");
    container.innerHTML = "";
    questions.forEach((item, index) => {
        let html = `
        <div class="question-block" id="qblock-${index}">
            <div class="question-text">${index + 1}. ${item.q}</div>
            <div class="options">`;
        item.options.forEach(opt => {
            html += `
            <label class="option-label" onclick="selectOption(this, 'q${index}')" data-orig-index="${opt.originalIndex}">
                <span class="option-circle"></span>
                <input type="radio" name="q${index}" value="${opt.originalIndex}">
                <span>${opt.text}</span>
            </label>`;
        });
        html += `</div></div>`;
        container.innerHTML += html;
    });
}

function selectOption(label, name) {
    document.querySelectorAll(`input[name="${name}"]`).forEach(inp => inp.parentElement.classList.remove("selected"));
    label.classList.add("selected");
    label.querySelector("input").checked = true;
}

function shuffleArray(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]];
    }
    return array;
}

function startTimer() {
    const timerDisplay = document.createElement("div");
    timerDisplay.className = "timer-float";
    timerDisplay.id = "timer-display";
    document.body.appendChild(timerDisplay);

    timerInterval = setInterval(() => {
        remainingSeconds--;
        if (remainingSeconds <= 0) {
            clearInterval(timerInterval);
            timerDisplay.innerText = "00:00";
            alert("Vaqt tugadi!");
            finishTest(true);
        } else {
            let m = Math.floor(remainingSeconds / 60);
            let s = remainingSeconds % 60;
            timerDisplay.innerText = `${m}:${s < 10 ? '0'+s : s}`;
        }
    }, 1000);
}

function finishTest() {
    clearInterval(timerInterval);
    document.getElementById("timer-display")?.remove();
    localStorage.removeItem(`end_${testCode}_${userId}`); // Xotirani tozalash

    let score = 0;
    questions.forEach((item, index) => {
        const selectedLabel = document.querySelector(`input[name="q${index}"]:checked`)?.parentElement;
        if (selectedLabel && parseInt(selectedLabel.dataset.origIndex) === item.correctIndex) {
            score++;
        }
    });

    submitResult(score); // Avtomatik yuborishni boshlaymiz
}

function submitResult(score) {
    // Interfeysni bloklash
    document.getElementById("quiz-screen").innerHTML = "<h3 style='text-align:center'>Natija yuborilmoqda...</h3>";

    fetch(`${API_URL}/api/submit_result`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            test_code: testCode,
            userId: userId,
            student_name: document.getElementById("student_name").value || "Noma'lum",
            score: score,
            total: questions.length
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === "ok") {
            showResultScreen(score, questions.length, document.getElementById("test-title").innerText);
        } else {
            alert("Xatolik bo'ldi. Qayta urinib ko'ring.");
            tg.close();
        }
    })
    .catch(() => tg.close());
}

// Yangi funksiya: Faqat natijani ko'rsatish
function showResultScreen(score, total, testName) {
    document.body.innerHTML = `
        <div class="container">
            <div class="card" style="text-align: center; padding: 40px 20px;">
                <h1 style="font-size: 50px; margin: 0;">🏁</h1>
                <h2>Test Yakunlandi!</h2>
                <p style="color: #666; margin-bottom: 20px;">${testName}</p>
                
                <div style="background: #f0f2f5; padding: 20px; border-radius: 12px; margin-bottom: 20px;">
                    <span style="display: block; font-size: 14px; color: #666;">Sizning natijangiz:</span>
                    <strong style="font-size: 32px; color: ${score > total/2 ? '#28a745' : '#dc3545'}">
                        ${score} / ${total}
                    </strong>
                </div>

                <button onclick="tg.close()" class="primary-btn" style="background: #333;">Chiqish</button>
            </div>
        </div>
    `;
}
