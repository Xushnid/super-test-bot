const tg = window.Telegram.WebApp;
tg.expand();

// Render Serveringiz manzili (oxirida / bo'lmasin)
const API_URL = "https://super-test-bot.onrender.com"; 

let questions = [];
let testCode = "";
let endTimeStr = "";
let timerInterval;

// URL dan kodni olish (?code=12345)
const urlParams = new URLSearchParams(window.location.search);
testCode = urlParams.get('code');

// Boshlanishda
document.addEventListener("DOMContentLoaded", () => {
    if (!testCode) {
        document.body.innerHTML = "<h3 style='text-align:center; margin-top:50px;'>Xatolik: Test kodi yo'q</h3>";
        return;
    }
    loadTest();
});

function loadTest() {
    fetch(`${API_URL}/api/get_test?code=${testCode}`)
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                alert("Test topilmadi!");
                tg.close();
                return;
            }
            
            document.getElementById("test-title").innerText = data.name;
            endTimeStr = data.end_time;
            
            // Savollarni aralashtirish
            questions = shuffleArray(data.questions).map(q => {
                // Javoblarni ham aralashtirish, lekin to'g'ri javob indeksini yo'qotmaslik kerak
                // Buning uchun javob obyektini o'zgartiramiz: {text: "Javob", originalIndex: 0}
                let optionsObj = q.a.map((opt, i) => ({ text: opt, originalIndex: i }));
                let shuffledOptions = shuffleArray(optionsObj);
                
                return {
                    q: q.q,
                    options: shuffledOptions,
                    correctIndex: q.c // Bu original indeks
                };
            });

            document.getElementById("login-screen").classList.remove("hidden");
            startTimer();
        })
        .catch(err => {
            alert("Server xatosi: " + err);
        });
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
        
        item.options.forEach((opt, i) => {
            // value sifatida original indeksni emas, hozirgi aralashgan indeksni saqlaymiz
            // Lekin tekshirishda original kerak bo'ladi.
            // Oson yo'li: data attribute qo'shamiz
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

// Array aralashtirish (Fisher-Yates)
function shuffleArray(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]];
    }
    return array;
}

// Timer
function startTimer() {
    // Vaqt formatini parse qilish (YYYY-MM-DD HH:MM)
    // Oddiy taqqoslash uchun JS Date ga o'tkazamiz
    // Eslatma: Server vaqti va Client vaqti farq qilishi mumkin.
    // Idealda serverdan "qolgan vaqt" kelishi kerak. 
    // Hozir soddalik uchun telefondagi vaqtga ishonamiz.
    
    timerInterval = setInterval(() => {
        const now = new Date();
        const end = new Date(endTimeStr.replace(" ", "T")); // ISO formatga yaqinlashtirish
        
        const diff = end - now;
        if (diff <= 0) {
            clearInterval(timerInterval);
            alert("Vaqt tugadi! Natijalar yuborilmoqda.");
            finishTest(true); // Majburiy tugatish
        } else {
            // Ekranda vaqtni ko'rsatish (ixtiyoriy)
        }
    }, 1000);
}

function finishTest(force = false) {
    clearInterval(timerInterval);
    let score = 0;
    let detailsHTML = "";

    questions.forEach((item, index) => {
        const selectedLabel = document.querySelector(`input[name="q${index}"]:checked`)?.parentElement;
        const qBlock = document.getElementById(`qblock-${index}`);
        
        let isCorrect = false;
        
        // To'g'ri javobni topamiz (Vizual ko'rsatish uchun)
        const allLabels = qBlock.querySelectorAll(".option-label");
        let correctLabel;
        allLabels.forEach(lbl => {
            if (parseInt(lbl.dataset.origIndex) === item.correctIndex) {
                correctLabel = lbl;
            }
        });

        if (selectedLabel) {
            const selectedOrigIndex = parseInt(selectedLabel.dataset.origIndex);
            if (selectedOrigIndex === item.correctIndex) {
                score++;
                isCorrect = true;
                selectedLabel.style.background = "#d4edda"; // Yashil
                selectedLabel.style.borderColor = "#28a745";
            } else {
                selectedLabel.style.background = "#f8d7da"; // Qizil
                selectedLabel.style.borderColor = "#dc3545";
            }
        }
        
        // Har doim to'g'ri javobni ko'rsatib qo'yamiz (Yakunlanganda)
        if (correctLabel) {
            correctLabel.classList.add("correct-answer-show"); // CSS da yashil border beramiz
        }
        
        // Inputlarni o'chirib qo'yamiz
        allLabels.forEach(l => l.style.pointerEvents = "none");
    });

    // Tugmani yashiramiz
    document.querySelector(".finish-btn").style.display = "none";
    
    // Tepaga natijani chiqaramiz
    const header = document.querySelector(".quiz-header");
    header.innerHTML = `<h3>Natija: ${score} / ${questions.length}</h3>`;
    header.style.color = score > questions.length/2 ? "green" : "red";

    // Scroll to top
    window.scrollTo(0,0);

    // Botga yuborish
    const data = {
        test_code: testCode,
        student_name: document.getElementById("student_name").value,
        score: score,
        total: questions.length
    };
    tg.sendData(JSON.stringify(data));
}
