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

// --- YANGI SVG EMOJILAR (ANIQ KO'RINADIGAN) ---
const SVGs = {
    // Qizil Hafa (60% dan kam)
    sad: `<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="50" fill="#FF4B4B"/><circle cx="32" cy="40" r="6" fill="white"/><circle cx="68" cy="40" r="6" fill="white"/><path d="M30 75 Q50 55 70 75" stroke="white" stroke-width="5" fill="none"/></svg>`,
    
    // Jigarrang Neutral (60-70%)
    neutral: `<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="50" fill="#CD853F"/><circle cx="32" cy="40" r="6" fill="white"/><circle cx="68" cy="40" r="6" fill="white"/><rect x="30" y="65" width="40" height="6" rx="3" fill="white"/></svg>`,
    
    // Sariq Yaxshi (71-89%)
    smile: `<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="50" fill="#F1C40F"/><circle cx="32" cy="40" r="6" fill="#333"/><circle cx="68" cy="40" r="6" fill="#333"/><path d="M30 65 Q50 85 70 65" stroke="#333" stroke-width="5" fill="none"/></svg>`,
    
    // Yashil A'lo (90-100%)
    happy: `<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="50" fill="#2ECC71"/><path d="M25 45 Q32 35 39 45" stroke="white" stroke-width="5" fill="none"/><path d="M61 45 Q68 35 75 45" stroke="white" stroke-width="5" fill="none"/><path d="M30 65 Q50 90 70 65" fill="white"/></svg>`
};

document.addEventListener('contextmenu', event => event.preventDefault());
document.addEventListener("DOMContentLoaded", () => {
    if (!testCode) return document.body.innerHTML = "<h3>Xatolik: Kod yo'q</h3>";
    loadTest();
});

function loadTest() {
    fetch(`${API_URL}/api/get_test?code=${testCode}&userId=${userId}`)
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                alert(data.error === "expired" ? "Vaqt tugagan!" : "Xatolik!");
                tg.close();
                return;
            }

            if (data.status === "finished") {
                renderResultScreen(data.score, data.total);
                return;
            }
            
            document.getElementById("test-title").innerText = data.name;
            
            const savedEndTime = localStorage.getItem(`end_${testCode}_${userId}`);
            const now = Math.floor(Date.now() / 1000);
            remainingSeconds = savedEndTime ? parseInt(savedEndTime) - now : data.remaining_seconds;
            
            if (!savedEndTime) localStorage.setItem(`end_${testCode}_${userId}`, (now + remainingSeconds).toString());

            // Savollarni yuklash
            questions = shuffleArray(data.questions).map(q => {
                let optionsObj = q.a.map((opt, i) => ({ text: opt, originalIndex: i }));
                return { 
                    q: q.q, 
                    options: shuffleArray(optionsObj), 
                    correctIndex: q.c,
                    userSelected: null 
                };
            });

            document.getElementById("login-screen").classList.remove("hidden");
            startTimer();
        })
        .catch(err => alert("Internet xatosi!"));
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
        <div class="question-block">
            <div class="question-text">${index + 1}. ${item.q}</div>
            <div class="options">`;
        
        item.options.forEach((opt) => {
            html += `
            <label class="option-label" onclick="selectOption(${index}, ${opt.originalIndex}, this)">
                <span class="option-circle"></span>
                <input type="radio" name="q${index}" value="${opt.originalIndex}">
                <span>${opt.text}</span>
            </label>`;
        });
        html += `</div></div>`;
        container.innerHTML += html;
    });

    const finishBtn = document.createElement("button");
    finishBtn.innerText = "Yakunlash";
    finishBtn.className = "primary-btn finish-btn";
    finishBtn.onclick = () => finishTest();
    container.appendChild(finishBtn);
}

function selectOption(qIndex, originalIndex, labelElement) {
    questions[qIndex].userSelected = originalIndex;
    const parent = labelElement.closest('.options');
    parent.querySelectorAll('.option-label').forEach(lbl => lbl.classList.remove('selected'));
    labelElement.classList.add('selected');
    labelElement.querySelector('input').checked = true;
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
            finishTest(true);
        } else {
            let m = Math.floor(remainingSeconds / 60);
            let s = remainingSeconds % 60;
            timerDisplay.innerText = `${m}:${s < 10 ? '0'+s : s}`;
        }
    }, 1000);
}

function finishTest(force = false) {
    clearInterval(timerInterval);
    document.getElementById("timer-display")?.remove();
    localStorage.removeItem(`end_${testCode}_${userId}`);

    let score = 0;
    questions.forEach(q => {
        if (q.userSelected === q.correctIndex) score++;
    });

    document.getElementById("quiz-screen").innerHTML = "<h3 style='text-align:center; margin-top:50px;'>Natija hisoblanmoqda...</h3>";
    
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
            renderResultScreen(score, questions.length);
        } else {
            alert("Xatolik!"); tg.close();
        }
    })
    .catch(() => tg.close());
}

// --- NATIJALAR KO'RSATISH ---
function renderResultScreen(score, total) {
    document.getElementById("login-screen").classList.add("hidden");
    document.getElementById("quiz-screen").classList.add("hidden");
    const resultScreen = document.getElementById("result-screen");
    resultScreen.classList.remove("hidden");

    const percent = Math.round((score / total) * 100);
    const iconDiv = document.getElementById("result-icon");
    const title = document.getElementById("result-title");
    const msg = document.getElementById("result-message");
    const scoreText = document.getElementById("result-score-text");
    const scoreNum = document.getElementById("result-score-number");

    scoreNum.innerText = `${score} / ${total}`;
    scoreText.innerText = `${percent}%`;

    // Emojini tanlash
    if (percent < 60) {
        iconDiv.innerHTML = SVGs.sad;
        title.innerText = "Afsuski...";
        msg.innerText = "Siz o'ta olmadingiz.";
        title.style.color = "#ff4b4b";
    } else if (percent <= 70) {
        iconDiv.innerHTML = SVGs.neutral;
        title.innerText = "Qoniqarli";
        msg.innerText = "Yomon emas, lekin yaxshiroq bo'lishi mumkin.";
        title.style.color = "#cd853f";
    } else if (percent <= 89) {
        iconDiv.innerHTML = SVGs.smile;
        title.innerText = "Yaxshi!";
        msg.innerText = "Yaxshi natija, barakalla!";
        title.style.color = "#f1c40f";
    } else {
        iconDiv.innerHTML = SVGs.happy;
        title.innerText = "A'lo!";
        msg.innerText = "Siz daho ekansiz! Tabriklaymiz!";
        title.style.color = "#2ecc71";
    }
}

// --- XATOLARNI TAHLIL QILISH (TO'G'IRLANGAN) ---
function viewDetails() {
    document.getElementById("result-screen").classList.add("hidden");
    const reviewScreen = document.getElementById("review-screen");
    reviewScreen.classList.remove("hidden");
    const container = document.getElementById("review-container");
    container.innerHTML = "";

    questions.forEach((item, index) => {
        // Savol matni
        let html = `
        <div class="question-block">
            <div class="question-text">${index + 1}. ${item.q}</div>
            <div class="options">`;
        
        item.options.forEach(opt => {
            let className = "review-item"; // Asosiy stil
            let icon = "";

            // Agar bu TO'G'RI javob bo'lsa
            if (opt.originalIndex === item.correctIndex) {
                className += " review-correct";
                icon = " ✅";
            }
            // Agar foydalanuvchi buni XATO tanlagan bo'lsa
            else if (opt.originalIndex === item.userSelected) {
                className += " review-wrong";
                icon = " ❌";
            }
            // Tanlanmagan va noto'g'ri variantlar
            else {
                className += " review-neutral";
            }

            html += `
            <div class="${className}">
                <span class="option-circle" style="border:none"></span>
                <span>${opt.text} ${icon}</span>
            </div>`;
        });
        
        html += `</div></div>`;
        container.innerHTML += html;
    });
}

function backToResult() {
    document.getElementById("review-screen").classList.add("hidden");
    document.getElementById("result-screen").classList.remove("hidden");
}
