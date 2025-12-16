const tg = window.Telegram.WebApp;
tg.expand();

// DIQQAT: Render linkingizni qo'ying
const API_URL = "https://super-test-bot.onrender.com"; 

let questions = [];
let testCode = "";
let remainingSeconds = 0; // Serverdan keladi
let timerInterval;

const urlParams = new URLSearchParams(window.location.search);
testCode = urlParams.get('code');

document.addEventListener("DOMContentLoaded", () => {
    if (!testCode) {
        document.body.innerHTML = "<h3>Xatolik: Kod yo'q</h3>";
        return;
    }
    loadTest();
});

function loadTest() {
    fetch(`${API_URL}/api/get_test?code=${testCode}`)
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                alert(data.error === "Time expired" ? "Vaqt tugagan!" : "Test topilmadi!");
                tg.close();
                return;
            }
            
            document.getElementById("test-title").innerText = data.name;
            remainingSeconds = data.remaining_seconds;
            
            // Random savollar
            questions = shuffleArray(data.questions).map(q => {
                let optionsObj = q.a.map((opt, i) => ({ text: opt, originalIndex: i }));
                return {
                    q: q.q,
                    options: shuffleArray(optionsObj),
                    correctIndex: q.c
                };
            });

            document.getElementById("login-screen").classList.remove("hidden");
            startTimer(); // Taymerni darhol ishga tushiramiz (fondagi hisob)
        })
        .catch(err => alert("Xato: " + err));
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
    timerDisplay.style.cssText = "position:fixed; top:10px; right:10px; background:red; color:white; padding:5px 10px; border-radius:5px; font-weight:bold; z-index:1000";
    timerDisplay.id = "timer-display";
    document.body.appendChild(timerDisplay);

    timerInterval = setInterval(() => {
        remainingSeconds--;
        
        if (remainingSeconds <= 0) {
            clearInterval(timerInterval);
            timerDisplay.innerText = "00:00";
            alert("Vaqt tugadi!");
            finishTest();
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
                selectedLabel.style.background = "#d4edda";
                selectedLabel.style.borderColor = "#28a745";
            } else {
                selectedLabel.style.background = "#f8d7da";
                selectedLabel.style.borderColor = "#dc3545";
            }
        }
    });

    document.querySelector(".finish-btn").style.display = "none";
    const header = document.querySelector(".quiz-header");
    header.innerHTML = `<h3>Natija: ${score} / ${questions.length}</h3>`;
    window.scrollTo(0,0);

    const data = {
        test_code: testCode,
        student_name: document.getElementById("student_name").value || "Noma'lum",
        score: score,
        total: questions.length
    };
    tg.sendData(JSON.stringify(data));
}
