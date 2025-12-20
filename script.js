const tg = window.Telegram.WebApp;
tg.expand();

const API_URL = "https://super-test-bot.onrender.com"; 

let questions = []; // {q, options: [], correctIndex, userSelected}
let testCode = "";
let userId = "";
let remainingSeconds = 0;
let timerInterval;

const urlParams = new URLSearchParams(window.location.search);
testCode = urlParams.get('code');
userId = urlParams.get('userId');

// Emojilar (SVG formatda)
const SVGs = {
    sad: `<svg viewBox="0 0 512 512" fill="#ff4b4b"><path d="M256 512A256 256 0 1 0 256 0a256 256 0 1 0 0 512zM164.1 325.5C182 346.2 212.6 368 256 368s74-21.8 91.9-42.5c5.8-6.7 15.9-7.4 22.6-1.6s7.4 15.9 1.6 22.6C349.8 372.1 311.1 400 256 400s-93.8-27.9-116.1-53.5c-5.8-6.7-5.1-16.8 1.6-22.6s16.8-5.1 22.6 1.6zM144.4 208a32 32 0 1 1 64 0 32 32 0 1 1-64 0zm192-32a32 32 0 1 1 0 64 32 32 0 1 1 0-64z"/></svg>`,
    neutral: `<svg viewBox="0 0 512 512" fill="#cd853f"><path d="M256 512A256 256 0 1 0 256 0a256 256 0 1 0 0 512zM176 352h160c8.8 0 16 7.2 16 16s-7.2 16-16 16H176c-8.8 0-16-7.2-16-16s7.2-16 16-16zm-48-160a32 32 0 1 1 64 0 32 32 0 1 1-64 0zm272 32a32 32 0 1 1 0-64 32 32 0 1 1 0 64z"/></svg>`,
    smile: `<svg viewBox="0 0 512 512" fill="#f1c40f"><path d="M256 512A256 256 0 1 0 256 0a256 256 0 1 0 0 512zM164.1 325.5C182 346.2 212.6 368 256 368s74-21.8 91.9-42.5c5.8-6.7 15.9-7.4 22.6-1.6s7.4 15.9 1.6 22.6C349.8 372.1 311.1 400 256 400s-93.8-27.9-116.1-53.5c-5.8-6.7-5.1-16.8 1.6-22.6s16.8-5.1 22.6 1.6zM144.4 208a32 32 0 1 1 64 0 32 32 0 1 1-64 0zm192-32a32 32 0 1 1 0 64 32 32 0 1 1 0-64z" transform="rotate(180 256 256)"/></svg>`, // Smile is usually inverted sad curve, simplistic here
    happy: `<svg viewBox="0 0 512 512" fill="#2ecc71"><path d="M256 512A256 256 0 1 0 256 0a256 256 0 1 0 0 512zM388.1 312.5c-9.6-8.2-24.2-7.1-32.4 2.5C337.3 336.5 301.7 352 256 352s-81.3-15.5-99.7-37c-8.2-9.6-22.8-10.7-32.4-2.5s-10.7 22.8-2.5 32.4C147.2 375 197.6 400 256 400s108.8-25 134.6-55.1c8.2-9.6 7.1-24.2-2.5-32.4zM144.4 208a32 32 0 1 1 64 0 32 32 0 1 1-64 0zm192-32a32 32 0 1 1 0 64 32 32 0 1 1 0-64z"/></svg>`
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

            // RELOAD BO'LGANDA (Tayyor natija ko'rsatish)
            if (data.status === "finished") {
                renderResultScreen(data.score, data.total);
                return;
            }
            
            document.getElementById("test-title").innerText = data.name;
            
            // Vaqtni tiklash
            const savedEndTime = localStorage.getItem(`end_${testCode}_${userId}`);
            const now = Math.floor(Date.now() / 1000);
            remainingSeconds = savedEndTime ? parseInt(savedEndTime) - now : data.remaining_seconds;
            
            if (!savedEndTime) localStorage.setItem(`end_${testCode}_${userId}`, (now + remainingSeconds).toString());

            // Savollarni yuklash va userSelected maydonini qo'shish
            questions = shuffleArray(data.questions).map(q => {
                let optionsObj = q.a.map((opt, i) => ({ text: opt, originalIndex: i }));
                return { 
                    q: q.q, 
                    options: shuffleArray(optionsObj), 
                    correctIndex: q.c,
                    userSelected: null // Hali tanlanmagan
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
        
        item.options.forEach((opt, i) => {
            // value = hozirgi aralashgan indeksi
            // data-orig-index = asl to'g'ri javob indeksi
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

// Javob tanlanganda arrayga saqlab qo'yamiz (Review uchun kerak)
function selectOption(qIndex, originalIndex, labelElement) {
    questions[qIndex].userSelected = originalIndex;
    
    // Vizual o'zgarish
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

    // Serverga yuborish
    document.getElementById("quiz-screen").innerHTML = "<h3 style='text-align:center'>Natija hisoblanmoqda...</h3>";
    
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

// ---------------------------------------------------------
// YANGI: NATIJALAR OYNASI VA TAHLIL
// ---------------------------------------------------------

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

    // Logika: <60, 60-70, 71-89, 90-100
    if (percent < 60) {
        iconDiv.innerHTML = SVGs.sad;
        title.innerText = "Afsuski...";
        msg.innerText = "Siz o'ta olmadingiz.";
        title.style.color = "var(--color-fail)";
    } else if (percent <= 70) {
        iconDiv.innerHTML = SVGs.neutral;
        title.innerText = "Qoniqarli";
        msg.innerText = "Yomon emas, lekin yaxshiroq bo'lishi mumkin.";
        title.style.color = "var(--color-fair)";
    } else if (percent <= 89) {
        // Sariq smile uchun oddiyroq SVG (tepada sadning teskarisi qo'yilgandi, keling to'g'rilaymiz)
        // Shunchaki text bilan o'zgartirib qo'yamiz yoki chiroyli SVG
        iconDiv.innerHTML = `<svg viewBox="0 0 512 512" fill="#f1c40f"><path d="M256 512A256 256 0 1 0 256 0a256 256 0 1 0 0 512zM368.4 272c13.2 0 24-10.8 24-24s-10.8-24-24-24c-8.8 0-16 7.2-16 16s7.2 16 16 16zm-224 0c13.2 0 24-10.8 24-24s-10.8-24-24-24c-8.8 0-16 7.2-16 16s7.2 16 16 16zM177.6 364.5c20.3 17.9 47 27.5 78.4 27.5s58.1-9.6 78.4-27.5c6.7-5.9 7.4-16.1 1.5-22.8s-16.1-7.4-22.8-1.5c-14.2 12.5-33.1 19.8-57.1 19.8s-42.9-7.3-57.1-19.8c-6.7-5.9-16.9-5.2-22.8 1.5s-5.2 16.9 1.5 22.8z"/></svg>`;
        title.innerText = "Yaxshi!";
        msg.innerText = "Yaxshi natija, barakalla!";
        title.style.color = "var(--color-good)";
    } else {
        // 90-100% Mushak effekti
        iconDiv.innerHTML = SVGs.happy;
        iconDiv.classList.add("pump-effect"); // Animatsiya
        title.innerText = "A'lo!";
        msg.innerText = "Siz daho ekansiz! Tabriklaymiz!";
        title.style.color = "var(--color-excellent)";
    }
}

// Natijalarni ko'rish (Review)
function viewDetails() {
    document.getElementById("result-screen").classList.add("hidden");
    const reviewScreen = document.getElementById("review-screen");
    reviewScreen.classList.remove("hidden");
    const container = document.getElementById("review-container");
    container.innerHTML = "";

    questions.forEach((item, index) => {
        let html = `
        <div class="question-block">
            <div class="question-text">${index + 1}. ${item.q}</div>
            <div class="options">`;
        
        item.options.forEach(opt => {
            let className = "option-label";
            let statusIcon = "";

            // Agar bu variant TO'G'RI javob bo'lsa
            if (opt.originalIndex === item.correctIndex) {
                className += " review-correct";
                statusIcon = " ✅";
            }
            // Agar foydalanuvchi buni TANLAGAN bo'lsa
            if (opt.originalIndex === item.userSelected) {
                // Agar tanlagani noto'g'ri bo'lsa -> Qizil
                if (item.userSelected !== item.correctIndex) {
                    className += " review-wrong";
                    statusIcon = " ❌";
                }
            } else if (item.userSelected !== item.correctIndex && opt.originalIndex !== item.correctIndex) {
                // Tanlanmagan va noto'g'ri variantlar
                className += " review-missed";
            }

            html += `
            <div class="${className}" style="cursor: default;">
                <span class="option-circle" style="border:none"></span>
                <span>${opt.text} ${statusIcon}</span>
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
