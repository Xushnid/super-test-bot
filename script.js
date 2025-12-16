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
                if (data.error === "submitted") msg = "Siz bu testni yechib bo'lgansiz!";
                alert(msg);
                tg.close();
                return;
            }
            
            document.getElementById("test-title").innerText = data.name;
            
            // ANTI-RELOAD TIZIMI
            // 1. Oldin saqlangan vaqt bormi?
            const savedEndTime = localStorage.getItem(`end_${testCode}_${userId}`);
            const now = Math.floor(Date.now() / 1000);
            
            if (savedEndTime) {
                // Agar bor bo'lsa, qolgan vaqtni hisoblaymiz
                remainingSeconds = parseInt(savedEndTime) - now;
            } else {
                // Yo'q bo'lsa, server vaqtini olib, xotiraga yozamiz
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

function finishTest(force = false) {
    clearInterval(timerInterval);
    document.getElementById("timer-display")?.remove();
    // Test tugadi, xotirani tozaylaymiz
    localStorage.removeItem(`end_${testCode}_${userId}`);

    let score = 0;
    questions.forEach((item, index) => {
        const selectedLabel = document.querySelector(`input[name="q${index}"]:checked`)?.parentElement;
        const qBlock = document.getElementById(`qblock-${index}`);
        const allLabels = qBlock.querySelectorAll(".option-label");
        
        allLabels.forEach(lbl => {
            if (parseInt(lbl.dataset.origIndex) === item.correctIndex) lbl.classList.add("correct-answer-show");
            lbl.style.pointerEvents = "none";
        });

        if (selectedLabel) {
            if (parseInt(selectedLabel.dataset.origIndex) === item.correctIndex) {
                score++;
                selectedLabel.classList.add("correct");
            } else {
                selectedLabel.classList.add("wrong");
            }
        }
    });

    document.querySelector(".finish-btn").style.display = "none";
    
    // YUBORISH TUGMASI (Katta va Aniq)
    const sendBtn = document.createElement("button");
    sendBtn.innerHTML = "📤 Natijani Yuborish va Chiqish";
    sendBtn.className = "primary-btn send-result-btn";
    sendBtn.onclick = () => submitResult(score);
    document.getElementById("quiz-screen").appendChild(sendBtn);

    document.querySelector(".quiz-header").innerHTML = `<h3>Natija: ${score} / ${questions.length}</h3>`;
    window.scrollTo(0,0);
}

function submitResult(score) {
    const btn = document.querySelector(".send-result-btn");
    btn.disabled = true;
    btn.innerText = "Yuborilmoqda...";

    // Serverga to'g'ridan-to'g'ri yuborish
    fetch(`${API_URL}/api/submit_result`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
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
            // Muvaffaqiyatli
            localStorage.setItem(`finished_${testCode}_${userId}`, "true");
            alert("Natija yuborildi! ✅");
            tg.close();
        } else {
            alert("Xatolik: " + (data.error || "Noma'lum xato"));
            btn.disabled = false;
            btn.innerText = "Qayta urinish";
        }
    })
    .catch(err => {
        alert("Internet xatosi! Qayta urining.");
        btn.disabled = false;
        btn.innerText = "Qayta urinish";
    });
}
