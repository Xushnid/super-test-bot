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
userId = urlParams.get('userId'); // Botdan kelgan ID

document.addEventListener("DOMContentLoaded", () => {
    if (!testCode) {
        document.body.innerHTML = "<h3>Xatolik: Kod yo'q</h3>";
        return;
    }
    
    // Lokal xotirani tekshirish: Agar bu user bu testni tugatgan bo'lsa
    if (localStorage.getItem(`finished_${testCode}_${userId}`)) {
        document.body.innerHTML = "<h3 style='text-align:center; margin-top:50px; color:green'>Siz testni yakunlagansiz! ✅</h3><button onclick='tg.close()' class='primary-btn' style='margin:20px auto; display:block'>Chiqish</button>";
        return;
    }

    loadTest();
});

function loadTest() {
    // API ga user_id ni ham jo'natamiz
    fetch(`${API_URL}/api/get_test?code=${testCode}&userId=${userId}`)
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                let msg = "Test topilmadi!";
                if (data.error === "expired") msg = "Vaqt tugagan!";
                if (data.error === "submitted") msg = "Siz allaqachon topshirgansiz!";
                
                alert(msg);
                tg.close();
                return;
            }
            
            document.getElementById("test-title").innerText = data.name;
            remainingSeconds = data.remaining_seconds;
            
            questions = shuffleArray(data.questions).map(q => {
                let optionsObj = q.a.map((opt, i) => ({ text: opt, originalIndex: i }));
                return { q: q.q, options: shuffleArray(optionsObj), correctIndex: q.c };
            });

            document.getElementById("login-screen").classList.remove("hidden");
            startTimer();
        })
        .catch(err => alert("Server xatosi: " + err));
}

function startQuiz() {
    const name = document.getElementById("student_name").value;
    if (!name) { tg.showAlert("Ismingizni kiriting!"); return; }
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
    timerDisplay.style.cssText = "position:fixed; top:10px; right:10px; background:red; color:white; padding:5px 10px; border-radius:5px; font-weight:bold; z-index:1000";
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
    let score = 0;
    
    questions.forEach((item, index) => {
        const selectedLabel = document.querySelector(`input[name="q${index}"]:checked`)?.parentElement;
        const qBlock = document.getElementById(`qblock-${index}`);
        
        const allLabels = qBlock.querySelectorAll(".option-label");
        allLabels.forEach(lbl => {
            if (parseInt(lbl.dataset.origIndex) === item.correctIndex) {
                lbl.classList.add("correct-answer-show");
            }
            lbl.style.pointerEvents = "none";
        });

        if (selectedLabel) {
            if (parseInt(selectedLabel.dataset.origIndex) === item.correctIndex) {
                score++;
                selectedLabel.style.background = "#d4edda"; selectedLabel.style.borderColor = "#28a745";
            } else {
                selectedLabel.style.background = "#f8d7da"; selectedLabel.style.borderColor = "#dc3545";
            }
        }
    });

    // 1. Tugmani almashtiramiz
    const finishBtn = document.querySelector(".finish-btn");
    finishBtn.style.display = "none";

    // 2. Yangi tugma yaratamiz (Send Data uchun)
    const sendBtn = document.createElement("button");
    sendBtn.innerText = "📤 Natijani Yuborish va Chiqish";
    sendBtn.className = "primary-btn";
    sendBtn.style.backgroundColor = "#ff9800"; // Oranjevoy
    sendBtn.style.marginTop = "20px";
    sendBtn.onclick = () => submitResult(score);
    
    document.getElementById("quiz-screen").appendChild(sendBtn);

    // 3. Natijani tepada ko'rsatamiz
    const header = document.querySelector(".quiz-header");
    header.innerHTML = `<h3>Natija: ${score} / ${questions.length}</h3>`;
    window.scrollTo(0,0);
}

function submitResult(score) {
    // Lokal xotiraga yozib qo'yamiz (qayta kirmasligi uchun)
    if(testCode && userId) {
        localStorage.setItem(`finished_${testCode}_${userId}`, "true");
    }

    const data = {
        test_code: testCode,
        student_name: document.getElementById("student_name").value || "Noma'lum",
        score: score,
        total: questions.length
    };
    tg.sendData(JSON.stringify(data));
    // Ehtiyot shart tg.close() ni ham chaqiramiz
    setTimeout(() => tg.close(), 500);
}
