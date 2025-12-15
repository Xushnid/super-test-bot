const tg = window.Telegram.WebApp;
tg.expand();

// DIQQAT: Render.com dagi saytingiz manzilini shu yerga qo'ying!
// Oxirida / belgisini olib tashlang.
const API_URL = "https://super-test-bot.onrender.com"; 

let currentQuestions = [];
let currentTestName = "";

// 1. Sahifa ochilganda testlarni yuklaymiz
document.addEventListener("DOMContentLoaded", () => {
    fetch(`${API_URL}/api/tests`)
        .then(res => res.json())
        .then(tests => {
            document.getElementById("loader").classList.add("hidden");
            const container = document.getElementById("tests-container");
            const listScreen = document.getElementById("test-list-screen");
            
            if(tests.length === 0) {
                container.innerHTML = "<p>Hozircha aktiv testlar yo'q.</p>";
            } else {
                tests.forEach(test => {
                    const btn = document.createElement("button");
                    btn.className = "primary-btn";
                    btn.style.marginBottom = "10px";
                    btn.innerText = test.name;
                    btn.onclick = () => selectTest(test.id);
                    container.appendChild(btn);
                });
            }
            listScreen.classList.remove("hidden");
        })
        .catch(err => {
            document.getElementById("loader").innerHTML = "<p>Xatolik: Serverga ulanib bo'lmadi.</p>";
        });
});

// 2. Test tanlanganda savollarni yuklaymiz
function selectTest(id) {
    document.getElementById("test-list-screen").classList.add("hidden");
    document.getElementById("loader").classList.remove("hidden");
    
    fetch(`${API_URL}/api/test/${id}`)
        .then(res => res.json())
        .then(data => {
            currentQuestions = data.questions;
            currentTestName = data.name;
            
            document.getElementById("loader").classList.add("hidden");
            document.getElementById("selected-test-name").innerText = data.name;
            document.getElementById("login-screen").classList.remove("hidden");
        });
}

// 3. Testni boshlash (Login dan o'tish)
function startQuiz() {
    const name = document.getElementById("student_name").value;
    if(!name) { tg.showAlert("Ismingizni kiriting!"); return; }

    document.getElementById("login-screen").classList.add("hidden");
    document.getElementById("quiz-screen").classList.remove("hidden");
    
    renderQuestions();
}

// 4. Savollarni chizish
function renderQuestions() {
    const container = document.getElementById("questions-container");
    container.innerHTML = "";
    document.getElementById("q-count").innerText = `${currentQuestions.length} ta`;

    currentQuestions.forEach((item, index) => {
        let html = `
        <div class="question-block">
            <div class="question-text">${index + 1}. ${item.q}</div>
            <div class="options">`;
        
        item.a.forEach((opt, i) => {
            html += `
            <label class="option-label" onclick="selectOption(this, 'q${index}')">
                <span class="option-circle"></span>
                <input type="radio" name="q${index}" value="${i}">
                <span>${opt}</span>
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

// 5. Yakunlash
function finishTest() {
    let score = 0;
    currentQuestions.forEach((item, index) => {
        const checked = document.querySelector(`input[name="q${index}"]:checked`);
        if (checked && parseInt(checked.value) === item.c) score++;
    });

    const data = {
        test_name: currentTestName,
        student_name: document.getElementById("student_name").value,
        score: score,
        total: currentQuestions.length
    };
    
    tg.sendData(JSON.stringify(data));
}
